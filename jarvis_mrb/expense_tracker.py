from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis_mrb.visual_history import query_recent

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "expenses.sqlite3"
CSV_PATH = APP_DIR / "expenses.csv"


def _connect() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            merchant TEXT,
            transaction_date TEXT,
            currency TEXT,
            subtotal REAL,
            tax REAL,
            tip REAL,
            total REAL,
            items_json TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(value[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError("The vision model could not produce structured receipt data.")


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _mirror_expense(
    expense_id: int,
    *,
    captured_at: str,
    merchant: str,
    transaction_date: str,
    currency: str,
    subtotal: float | None,
    tax: float | None,
    tip: float | None,
    total: float | None,
    items: list[Any],
) -> None:
    try:
        from jarvis_mrb.world_model import SELF_ID, ensure_entity, record_event

        expense_entity = ensure_entity(
            "transaction",
            f"Expense {expense_id}: {merchant or 'unknown merchant'}",
            external_namespace="expense",
            external_id=str(expense_id),
            attributes={
                "transaction_date": transaction_date,
                "currency": currency,
                "total": total,
            },
            confidence=0.95,
        )
        participants: list[tuple[str, str, float]] = [
            (SELF_ID, "payer", 1.0),
            (expense_entity, "transaction", 1.0),
        ]
        if merchant:
            merchant_entity = ensure_entity("organization", merchant, confidence=0.9)
            participants.append((merchant_entity, "merchant", 0.9))
        record_event(
            "finance.expense",
            f"Expense at {merchant or 'unknown merchant'}" + (f": {currency} {total:.2f}" if total is not None else ""),
            source_kind="expense_tracker",
            source_ref=f"expense:{expense_id}",
            occurred_at=transaction_date or captured_at,
            payload={
                "expense_id": int(expense_id),
                "captured_at": captured_at,
                "transaction_date": transaction_date,
                "merchant": merchant,
                "currency": currency,
                "subtotal": subtotal,
                "tax": tax,
                "tip": tip,
                "total": total,
                "items": items[:80],
            },
            evidence="Explicit user-requested receipt capture; values are limited to what the vision extractor reported as visible.",
            confidence=0.9,
            participants=participants,
        )
    except Exception:
        pass


def capture_recent_receipt() -> str:
    prompt = """Inspect the clearest recent frame containing a paper receipt or digital invoice.
Extract only what is visibly supported. Return one JSON object and no Markdown:
{"merchant":"","date":"YYYY-MM-DD or empty","currency":"USD or visible currency code or empty","subtotal":null,"tax":null,"tip":null,"total":null,"items":[{"description":"","quantity":null,"amount":null}]}
Do not guess missing totals, dates, merchants, or line items. If this is not clearly a receipt or invoice, return {"error":"no clear receipt"}."""
    result_text = query_recent(prompt, seconds=20, max_frames=5)
    data = _extract_json(result_text)
    if data.get("error"):
        raise ValueError(str(data.get("error")))
    merchant = " ".join(str(data.get("merchant") or "").split())[:180]
    transaction_date = str(data.get("date") or "").strip()[:32]
    currency = str(data.get("currency") or "").strip().upper()[:8]
    subtotal = _number(data.get("subtotal"))
    tax = _number(data.get("tax"))
    tip = _number(data.get("tip"))
    total = _number(data.get("total"))
    items = data.get("items") if isinstance(data.get("items"), list) else []
    captured_at = datetime.now().astimezone().isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            """INSERT INTO expenses(captured_at,merchant,transaction_date,currency,subtotal,tax,tip,total,items_json,raw_json)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                captured_at,
                merchant,
                transaction_date,
                currency,
                subtotal,
                tax,
                tip,
                total,
                json.dumps(items, ensure_ascii=False),
                json.dumps(data, ensure_ascii=False),
            ),
        )
        expense_id = int(cursor.lastrowid)
        conn.commit()
    export_csv()
    _mirror_expense(
        expense_id,
        captured_at=captured_at,
        merchant=merchant,
        transaction_date=transaction_date,
        currency=currency,
        subtotal=subtotal,
        tax=tax,
        tip=tip,
        total=total,
        items=items,
    )
    amount = f" {currency} {total:.2f}" if total is not None else " with no confidently readable total"
    merchant_label = merchant or "an unidentified merchant"
    return f"Logged expense {expense_id} from {merchant_label}{amount}."


def list_recent(limit: int = 10) -> str:
    safe = max(1, min(int(limit), 50))
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT ?", (safe,)).fetchall()
    if not rows:
        return "No receipt expenses have been logged yet."
    rendered: list[str] = []
    for row in rows:
        total = row["total"]
        currency = str(row["currency"] or "")
        amount = f"{currency} {float(total):.2f}" if total is not None else "total unread"
        date = str(row["transaction_date"] or row["captured_at"][:10])
        rendered.append(f"#{row['id']} {date}, {row['merchant'] or 'unknown merchant'}, {amount}")
    return "Recent expenses: " + "; ".join(rendered) + "."


def export_csv() -> Path:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM expenses ORDER BY id ASC").fetchall()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "captured_at", "transaction_date", "merchant", "currency", "subtotal", "tax", "tip", "total", "items_json"])
        for row in rows:
            writer.writerow([
                row["id"], row["captured_at"], row["transaction_date"], row["merchant"], row["currency"],
                row["subtotal"], row["tax"], row["tip"], row["total"], row["items_json"],
            ])
    return CSV_PATH


def export_message() -> str:
    path = export_csv()
    return f"Expense CSV is current at {path}."
