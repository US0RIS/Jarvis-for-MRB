from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import httpx

from jarvis_mrb.planner_model import QUALITY_MODEL
from jarvis_mrb.sandbox import run_python
from jarvis_mrb.tool_repair import queue_repair

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
TOOLS_DIR = APP_DIR / "custom_tools"
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

_MAX_URL_CHARS = 8000
_MAX_REQUEST_BODY_BYTES = 65536
_MAX_RESPONSE_BYTES = 1048576
_SECRET_NAME_RE = re.compile(
    r"(?:^|[-_])(auth|authorization|token|secret|api[-_]?key|password|passwd|credential|cookie|signature)(?:$|[-_])",
    flags=re.IGNORECASE,
)


def _safe_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9_.-]+", "_", name.strip().lower()).strip("_.-")
    if not value:
        raise ValueError("Custom tool needs a name.")
    return value[:80]


def _path(name: str) -> Path:
    return TOOLS_DIR / f"{_safe_name(name)}.json"


def list_tools() -> list[dict[str, Any]]:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []
    for path in sorted(TOOLS_DIR.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            result.append({
                "name": item.get("name"),
                "description": item.get("description"),
                "allowed_hosts": item.get("allowed_hosts"),
                "risk": item.get("risk"),
                "enabled": bool(item.get("enabled", False)),
            })
    return result


def get_tool(name: str) -> dict[str, Any]:
    path = _path(name)
    if not path.exists():
        raise ValueError(f"Custom tool {name!r} does not exist.")
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Custom tool {name!r} is unreadable: {exc}") from exc
    if not isinstance(item, dict):
        raise ValueError(f"Custom tool {name!r} is invalid.")
    return item


def set_enabled(name: str, enabled: bool) -> dict[str, Any]:
    item = get_tool(name)
    item["enabled"] = bool(enabled)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    return item


def _extract_code(text: str) -> str:
    value = text.strip()
    match = re.search(r"```(?:python)?\s*(.*?)```", value, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return value


def synthesize(
    *,
    name: str,
    description: str,
    api_spec: str,
    allowed_hosts: list[str],
    risk: str = "read",
) -> dict[str, Any]:
    tool_name = _safe_name(name)
    hosts = _normalize_allowed_hosts(allowed_hosts)
    if not hosts:
        raise ValueError("A custom API tool must declare at least one allowed HTTPS host.")
    if risk not in {"read", "external_write"}:
        raise ValueError("Custom API tool risk must be read or external_write.")

    system = """Write a small Python 3.12 request-planning adapter for a personal assistant.
The script cannot access the network. It reads JSON arguments from /work/input.json if present, otherwise {}.
It MUST print exactly one JSON object with keys: method, url, headers, body.
- method must be GET for read-only tools; POST/PUT/PATCH/DELETE are allowed only when the supplied risk says external_write.
- url must be an HTTPS URL on one of the explicitly allowed hosts.
- headers must contain only non-secret static headers. Never hard-code API keys or credentials.
- body may be null, a JSON object, or a string.
Do not execute requests. Do not access files other than /work/input.json. Do not spawn processes. Do not use eval/exec.
Return Python source only."""
    user = (
        f"Tool name: {tool_name}\nDescription: {description}\nRisk: {risk}\n"
        f"Allowed hosts: {', '.join(hosts)}\nAPI specification:\n{api_spec[:12000]}"
    )
    payload = {
        "model": QUALITY_MODEL,
        "stream": False,
        "think": False,
        "keep_alive": "0",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=2.0)) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ValueError(f"Could not synthesize custom tool: {exc}") from exc

    code = _extract_code(str((data.get("message") or {}).get("content") or ""))
    if not code:
        raise ValueError("The synthesis model returned no Python source.")

    test = run_python(code, stdin_json={"_jarvis_test": True}, timeout_seconds=6)
    if not test.ok:
        raise ValueError(f"Generated tool failed sandbox validation: {test.message}")
    try:
        plan = json.loads(test.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ValueError("Generated tool did not emit a JSON request plan during validation.") from exc
    _validate_plan(plan, hosts=hosts, risk=risk)

    item = {
        "name": tool_name,
        "description": description.strip()[:1000],
        "api_spec": api_spec.strip()[:16000],
        "allowed_hosts": hosts,
        "risk": risk,
        "enabled": False,
        "code": code,
    }
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    _path(tool_name).write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    return item


def _canonical_host(value: str) -> str:
    raw = str(value or "").strip().rstrip(".")
    if not raw:
        raise ValueError("Allowed host is empty.")
    if "://" in raw or "/" in raw or "@" in raw:
        raise ValueError("Allowed hosts must be bare hostnames, not URLs or credentials.")
    try:
        canonical = raw.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(f"Allowed host {raw!r} is not a valid hostname.") from exc
    if not canonical or len(canonical) > 253:
        raise ValueError("Allowed host is invalid.")
    return canonical


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    candidate = str(host or "").strip().strip("[]")
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def _is_public_ip(address: str) -> bool:
    try:
        return bool(ipaddress.ip_address(str(address).split("%", 1)[0]).is_global)
    except ValueError:
        return False


def _normalize_allowed_hosts(values: list[str]) -> list[str]:
    hosts: set[str] = set()
    for value in values:
        host = _canonical_host(str(value))
        literal = _literal_ip(host)
        if literal is not None and not literal.is_global:
            raise ValueError(
                f"Custom tool allowed host {host!r} is not a public Internet address."
            )
        hosts.add(host)
    return sorted(hosts)


def _contains_secret_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SECRET_NAME_RE.search(str(key)):
                return True
            if _contains_secret_field(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_secret_field(item) for item in value)
    return False


def _resolve_public_addresses(host: str, port: int) -> list[str]:
    literal = _literal_ip(host)
    if literal is not None:
        if not literal.is_global:
            raise ValueError(
                f"Custom API destination {host!r} is not a public Internet address."
            )
        return [str(literal)]

    try:
        rows = socket.getaddrinfo(
            host,
            int(port),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(f"Custom API destination {host!r} could not be resolved: {exc}") from exc

    addresses: list[str] = []
    for row in rows:
        address = str(row[4][0]).split("%", 1)[0]
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise ValueError(f"Custom API destination {host!r} resolved to no addresses.")

    blocked = [address for address in addresses if not _is_public_ip(address)]
    if blocked:
        raise ValueError(
            "Custom API destination resolved to non-public address(es): "
            + ", ".join(blocked[:8])
        )
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a prevalidated IP while verifying TLS for the allowed hostname."""

    def __init__(
        self,
        host: str,
        *,
        port: int,
        resolved_ip: str,
        timeout: float,
    ) -> None:
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._resolved_ip = str(resolved_ip)

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._resolved_ip, self.port),
            self.timeout,
        )
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=self.host,
        )


def _request_pinned_https(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any,
) -> tuple[int, str, str]:
    parsed = urlparse(url)
    host = _canonical_host(parsed.hostname or "")
    try:
        port = int(parsed.port or 443)
    except ValueError as exc:
        raise ValueError("Custom API URL contains an invalid port.") from exc
    if port < 1 or port > 65535:
        raise ValueError("Custom API URL contains an invalid port.")

    addresses = _resolve_public_addresses(host, port)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query

    outbound_headers = dict(headers)
    payload: bytes | str | None
    if isinstance(body, (dict, list)):
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_REQUEST_BODY_BYTES:
            raise ValueError("Custom API request body is too large.")
        payload = encoded
        if not any(key.lower() == "content-type" for key in outbound_headers):
            outbound_headers["Content-Type"] = "application/json"
    elif isinstance(body, str):
        encoded = body.encode("utf-8")
        if len(encoded) > _MAX_REQUEST_BODY_BYTES:
            raise ValueError("Custom API request body is too large.")
        payload = encoded
    elif body is None:
        payload = None
    else:
        raise ValueError("Custom API request body must be null, a JSON object/list, or a string.")

    last_error: Exception | None = None
    for address in addresses:
        connection = _PinnedHTTPSConnection(
            host,
            port=port,
            resolved_ip=address,
            timeout=20.0,
        )
        try:
            connection.request(
                method,
                target,
                body=payload,
                headers=outbound_headers,
            )
            response = connection.getresponse()
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raw = raw[:_MAX_RESPONSE_BYTES]
            content_type = str(response.getheader("content-type") or "")
            charset = "utf-8"
            match = re.search(r"charset=([^;\s]+)", content_type, flags=re.IGNORECASE)
            if match:
                charset = match.group(1).strip('\"\'')
            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            return int(response.status), content_type, text
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            try:
                connection.close()
            except Exception:
                pass
    raise ValueError(f"Custom API request failed: {last_error}")


def _validate_plan(plan: Any, *, hosts: list[str], risk: str) -> tuple[str, str, dict[str, str], Any]:
    if not isinstance(plan, dict):
        raise ValueError("Custom tool did not return a JSON object.")
    method = str(plan.get("method") or "GET").upper()
    allowed_methods = {"GET"} if risk == "read" else {"GET", "POST", "PUT", "PATCH", "DELETE"}
    if method not in allowed_methods:
        raise ValueError(f"Custom tool attempted disallowed HTTP method {method}.")
    url = str(plan.get("url") or "").strip()
    if not url or len(url) > _MAX_URL_CHARS:
        raise ValueError("Custom tool attempted an empty or oversized URL.")
    parsed = urlparse(url)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Custom tool URLs cannot embed credentials.")
    if parsed.fragment:
        raise ValueError("Custom tool URLs cannot contain fragments.")
    host = _canonical_host(parsed.hostname or "")
    canonical_hosts = _normalize_allowed_hosts(hosts)
    if parsed.scheme != "https" or host not in canonical_hosts:
        raise ValueError("Custom tool attempted a URL outside its allowed HTTPS hosts.")
    try:
        port = int(parsed.port or 443)
    except ValueError as exc:
        raise ValueError("Custom tool URL contains an invalid port.") from exc
    if port < 1 or port > 65535:
        raise ValueError("Custom tool URL contains an invalid port.")

    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        if _SECRET_NAME_RE.search(str(key)):
            raise ValueError("Custom tool URLs cannot embed authentication secrets.")

    headers_raw = plan.get("headers") or {}
    if not isinstance(headers_raw, dict):
        raise ValueError("Custom tool headers must be an object.")
    headers: dict[str, str] = {}
    for key, value in headers_raw.items():
        k = str(key).strip()
        v = str(value).strip()
        if not k or len(k) > 120 or len(v) > 1000:
            continue
        if _SECRET_NAME_RE.search(k):
            raise ValueError("Custom tool adapters cannot embed authentication secrets.")
        headers[k] = v

    body = plan.get("body")
    if _contains_secret_field(body):
        raise ValueError("Custom tool request bodies cannot embed authentication secrets.")
    if body is not None and not isinstance(body, (dict, list, str)):
        raise ValueError("Custom tool request body has an unsupported type.")
    try:
        encoded_body = (
            json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            if not isinstance(body, str)
            else body.encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Custom tool request body is not serializable.") from exc
    if len(encoded_body) > _MAX_REQUEST_BODY_BYTES:
        raise ValueError("Custom API request body is too large.")
    return method, url, headers, body


def run(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    item = get_tool(name)
    tool_name = str(item.get("name") or name)
    if not item.get("enabled"):
        raise ValueError(f"Custom tool {name!r} is disabled. Enable it explicitly before use.")
    code = str(item.get("code") or "")
    result = run_python(code, stdin_json=arguments, timeout_seconds=8)
    if not result.ok:
        queue_repair(tool_name, result.message)
        raise ValueError(result.message + " A sandbox-validated repair will be queued for your approval if Jarvis can produce one.")
    try:
        plan = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        queue_repair(tool_name, "Adapter did not emit a valid JSON request plan.")
        raise ValueError("Custom tool did not emit a valid request plan. A repair proposal has been requested.") from exc

    hosts = [str(value) for value in item.get("allowed_hosts") or []]
    risk = str(item.get("risk") or "read")
    try:
        method, url, headers, body = _validate_plan(plan, hosts=hosts, risk=risk)
    except ValueError as exc:
        queue_repair(tool_name, str(exc))
        raise
    try:
        status_code, content_type, response_text = _request_pinned_https(
            method,
            url,
            headers,
            body,
        )
    except ValueError:
        # DNS/network/TLS failures are usually transient and must not cause Jarvis
        # to rewrite a structurally valid adapter automatically.
        raise

    if status_code in {400, 404, 405, 410, 415, 422}:
        queue_repair(
            tool_name,
            f"API returned HTTP {status_code}. Response excerpt: {response_text[:1200]}",
        )

    if "json" in content_type.lower():
        try:
            payload: Any = json.loads(response_text)
        except ValueError:
            payload = response_text[:12000]
    else:
        payload = response_text[:12000]
    return {
        "status_code": status_code,
        "content_type": content_type,
        "body": payload,
    }
