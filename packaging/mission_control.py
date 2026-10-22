"""Horus Mission Control — a native, source-backed Windows companion.

The iPhone/AirPods remain the primary voice surface. This is a desktop
conversation, awareness and administration client for the existing private
FastAPI backend. No displayed watch, alert, memory or connection is invented.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QSettings, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient, QTextOption
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from jarvis_mrb.inference import DEFAULT_MODELS, configure_inference, inference_status
from jarvis_mrb.remote_setup import configure_remote_access
from jarvis_mrb.server_config import load_server_config
from desktop_setup_state import derive_setup_state


PALETTE = {
    "bg": "#0A1018", "rail": "#0D1721", "panel": "#131E2A", "raised": "#192634",
    "border": "#29384A", "text": "#F1F6FA", "muted": "#91A3B3",
    "accent": "#73E2D5", "dim": "#16463F", "warn": "#F4B77E",
}
QSS = """
QWidget { background: transparent; color: #22313E; font-family: "Segoe UI", "Arial"; font-size: 13px; }
QMainWindow, QWidget#root { background: #F5F7F8; }
QFrame#rail { background: #192934; border-right: 1px solid #25404A; }
QFrame#rail QLabel { color: #F2F6F8; }
QFrame#rail QLabel#eyebrow { color: #9BCFC9; }
QFrame#rail QLabel#muted { color: #A9BDC8; }
QFrame#panel, QFrame#metric, QFrame#messageAssistant { background: white; border: 1px solid #DEE6E9; border-radius: 13px; }
QFrame#metric { background: #FFFFFF; border-radius: 11px; }
QFrame#messageUser { background: #EAF4F3; border: 1px solid #C9E0DC; border-radius: 13px; }
QFrame#divider { background: #E1E8EC; min-height: 1px; max-height: 1px; }
QLabel#eyebrow { color: #247F79; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#heading { color: #182C38; font-size: 26px; font-weight: 700; }
QLabel#subtitle { color: #657989; font-size: 13px; }
QLabel#muted { color: #697C8A; }
QLabel#bigValue { color: #1C2D39; font-size: 25px; font-weight: 700; }
QLabel#panelTitle { color: #20323F; font-size: 15px; font-weight: 650; }
QLabel#statusOnline { color: #237A62; font-size: 11px; font-weight: 700; }
QLabel#statusOffline { color: #AA7144; font-size: 11px; font-weight: 700; }
QLabel#stepComplete { color: #237A62; font-size: 12px; font-weight: 650; }
QLabel#stepPending { color: #9B6936; font-size: 12px; }
QLabel#stepHead { color: #20323F; font-size: 16px; font-weight: 700; }
QPushButton { background: #FFFFFF; border: 1px solid #CCD9DE; border-radius: 9px;
              padding: 10px 15px; color: #233747; font-weight: 600; }
QPushButton:hover { background: #E9F0F2; border-color: #9CABB4; }
QPushButton:pressed { background: #D6E5E9; }
QPushButton:disabled { color: #9BA8B0; background: #F0F3F5; border-color: #E0E8EB; }
QPushButton#primary { background: #246B72; color: white; border: 1px solid #246B72; }
QPushButton#primary:hover { background: #195B61; }
QPushButton#primary:disabled { background: #8EA9AB; color: #F0F5F5; }
QPushButton#nav { background: transparent; border: 0; border-radius: 9px; text-align: left;
                  color: #B9C7CF; padding: 13px 15px; font-size: 14px; }
QPushButton#nav:hover { color: white; background: #263C48; }
QPushButton#nav[active="true"] { background: #314B55; color: white; }
QLineEdit, QPlainTextEdit, QComboBox { background: white; border: 1px solid #CAD7DD;
                                      border-radius: 9px; padding: 10px 12px; color: #22313E; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #36877F; }
QLineEdit:disabled { color: #8C9BA4; background: #F1F5F6; }
QComboBox QAbstractItemView { background: white; color: #22313E; selection-background-color: #C5E5E1; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: 0; }
QScrollBar:vertical { background: #F0F3F5; width: 9px; border: 0; }
QScrollBar::handle:vertical { background: #B4C6CC; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QCheckBox { color: #20323F; spacing: 10px; }
QCheckBox::indicator { width: 17px; height: 17px; }
"""


def label(text: str, *, style: str = "", wrap: bool = True) -> QLabel:
    widget = QLabel(str(text))
    if style:
        widget.setObjectName(style)
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return widget


def panel() -> QFrame:
    frame = QFrame()
    frame.setObjectName("panel")
    return frame


def column(parent: QWidget | None = None, *, gap: int = 12, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(*margins)
    lay.setSpacing(gap)
    return lay


def line() -> QFrame:
    f = QFrame()
    f.setObjectName("divider")
    f.setFixedHeight(1)
    return f


def action(text: str, *, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if primary:
        b.setObjectName("primary")
    return b


def section_title(parent: QVBoxLayout, eyebrow: str, heading: str, subtitle: str) -> None:
    parent.addWidget(label(eyebrow.upper(), style="eyebrow"))
    parent.addWidget(label(heading, style="heading"))
    parent.addWidget(label(subtitle, style="subtitle"))
    parent.addSpacing(10)


class HorusMark(QWidget):
    """Crisp vector brand icon, no image assets or embedded browser."""
    def __init__(self, diameter: int = 48, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        size = min(self.width(), self.height())
        c = self.rect().center()
        gradient = QRadialGradient(c, size * 0.5)
        gradient.setColorAt(0.0, QColor("#1A5E61"))
        gradient.setColorAt(0.8, QColor("#142936"))
        gradient.setColorAt(1, QColor("#11212C"))
        p.setBrush(gradient)
        p.setPen(QPen(QColor("#3D7C7D"), 1.3))
        p.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#80E7DC"), max(1.2, size / 35)))
        p.drawEllipse(self.rect().adjusted(int(size*.19), int(size*.19),
                                            -int(size*.19), -int(size*.19)))
        p.setPen(QPen(QColor("#A5FFF2"), max(1.0, size / 27)))
        p.drawArc(self.rect().adjusted(int(size*.1), int(size*.28),
                                           -int(size*.1), -int(size*.28)), 22 * 16, 135 * 16)
        p.setBrush(QColor("#B6FFF7"))
        p.setPen(Qt.NoPen)
        r = max(2, int(size * .07))
        p.drawEllipse(c, r, r)
        p.end()


class JobSignals(QObject):
    done = Signal(str, object, str)


class Job(QRunnable):
    def __init__(self, name: str, callback: Callable[[], Any]):
        super().__init__()
        self.name = name
        self.callback = callback
        self.signals = JobSignals()

    def run(self) -> None:
        try:
            result = self.callback()
            self.signals.done.emit(self.name, result, "")
        except Exception as exc:
            self.signals.done.emit(self.name, None, str(exc)[:450])


def _server_url(path: str) -> str:
    from jarvis_mrb.server_config import load_server_config
    cfg = load_server_config()
    return f"http://127.0.0.1:{cfg.port}/{path.lstrip('/')}"


def request(path: str, *, method: str = "GET", body: dict | None = None,
            timeout: float = 5) -> dict[str, Any]:
    cfg = load_server_config()
    headers = {"Accept": "application/json"}
    data = None
    if cfg.api_token:
        headers["Authorization"] = "Bearer " + cfg.api_token
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(_server_url(path), headers=headers,
                                 data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            detail = str(payload.get("detail", ""))[:150]
        except Exception:
            pass
        raise RuntimeError(f"Horus returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Horus backend is unreachable on this PC.") from exc
    return result if isinstance(result, dict) else {}


def snapshot() -> dict[str, Any]:
    """Read-only, source-backed dashboard. A failed endpoint stays unknown."""
    results: dict[str, Any] = {"online": False, "health": {}, "errors": {}}
    try:
        health = request("health", timeout=4)
    except Exception as exc:
        results["errors"]["health"] = str(exc)
        return results
    results["online"] = health.get("status") == "ok"
    results["health"] = health
    if not results["online"]:
        return results
    for name, path in (
        ("watches", "proactive/watches"),
        ("ledger", "proactive/ledger?limit=8"),
        ("memory", "memory/objects"),
        ("phone", "desktop/phone-status"),
        ("state", "state"),
    ):
        try:
            results[name] = request(path, timeout=3)
        except Exception as exc:
            results["errors"][name] = str(exc)
    return results


def local_ipv4() -> str:
    try:
        candidates = sorted({
            item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
            if not item[4][0].startswith(("127.", "169.254."))
        })
        if candidates:
            return candidates[0]
    except OSError:
        pass
    return "YOUR_PC_PRIVATE_IP"


def lan_url() -> str:
    return f"http://{local_ipv4()}:{load_server_config().port}"


def restart_owned_backend(start_backend: Callable[[], bool]) -> bool:
    """Stop ONLY this installed exe's --service child, never arbitrary services."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Restart from the terminal in a developer source checkout.")
    import psutil
    own_exe = os.path.normcase(os.path.abspath(sys.executable))
    found = False
    for proc in psutil.process_iter(("pid", "exe", "cmdline")):
        try:
            if proc.pid == os.getpid():
                continue
            exe = os.path.normcase(os.path.abspath(proc.info.get("exe") or ""))
            args = proc.info.get("cmdline") or []
            if exe == own_exe and "--service" in args[1:]:
                found = True
                proc.terminate()
                proc.wait(timeout=7)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            raise RuntimeError("Could not safely restart the Horus backend; close its service and relaunch.")
    if not found:
        # A different program owns the port: never terminate an unrecognized process.
        try:
            request("health", timeout=1)
        except Exception:
            pass
        else:
            raise RuntimeError("The active server was not started by this Horus installation.")
    return start_backend()


class Composer(QPlainTextEdit):
    submitted = Signal()
    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
            event.modifiers() & Qt.ShiftModifier
        ):
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class Metric(QFrame):
    def __init__(self, heading: str, value: str, footnote: str):
        super().__init__()
        self.setObjectName("metric")
        lay = column(self, gap=8, margins=(20, 18, 20, 18))
        lay.addWidget(label(heading.upper(), style="eyebrow"))
        self.value = label(value, style="bigValue")
        lay.addWidget(self.value)
        self.footnote = label(footnote, style="muted")
        lay.addWidget(self.footnote)


class MissionControlWindow(QMainWindow):
    def __init__(self, *, start_backend: Callable[[], bool],
                 backend_running: Callable[[], bool], testing: bool = False):
        super().__init__()
        self.start_backend = start_backend
        self.backend_running = backend_running
        self.testing = testing
        self.pool = QThreadPool.globalInstance()
        self._jobs: dict[str, Job] = {}
        self.settings = QSettings("Horus", "MissionControl")
        self.session = str(self.settings.value("conversationSession") or "")
        if not self.session or self.session == "default":
            self.session = "horus-desktop-" + uuid.uuid4().hex
            if not testing:
                self.settings.setValue("conversationSession", self.session)
        self._latest_snapshot: dict[str, Any] = {}
        self.setWindowTitle("Horus — Desktop")
        self.resize(1250, 830)
        self.setMinimumSize(990, 680)
        self.setStyleSheet(QSS)
        self._building = True
        self._build()
        self._building = False
        if not testing:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(30000)
            QTimer.singleShot(350, self.refresh)

    def task(self, name: str, fn: Callable[[], Any],
             callback: Callable[[Any, str], None]) -> None:
        if name in self._jobs:
            return
        job = Job(name, fn)
        self._jobs[name] = job

        def finished(_name: str, result: Any, error: str) -> None:
            self._jobs.pop(name, None)
            callback(result, error)

        job.signals.done.connect(finished)
        self.pool.start(job)

    def notice(self, message: str) -> None:
        self.footer.setText(message[:400])

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(208)
        outer.addWidget(rail)
        rl = column(rail, gap=7, margins=(18, 23, 18, 18))
        identity = QHBoxLayout()
        identity.setSpacing(13)
        identity.addWidget(HorusMark(33))
        wordmark = column(gap=0)
        brand = label("HORUS", wrap=False)
        brand.setFont(QFont("Segoe UI", 17, QFont.Bold))
        wordmark.addWidget(brand)
        wordmark.addWidget(label("DESKTOP", style="eyebrow"))
        identity.addLayout(wordmark, 1)
        rl.addLayout(identity)
        rl.addSpacing(30)
        rl.addWidget(label("WORKSPACE", style="eyebrow"))
        self.nav_buttons: list[QPushButton] = []
        for index, name in enumerate(("Overview", "Get set up", "Conversation", "Activity", "Settings")):
            button = action(f"   {name}")
            button.setObjectName("nav")
            button.setProperty("active", "false")
            button.setMinimumHeight(49)
            button.clicked.connect(lambda _checked=False, i=index: self.navigate(i))
            self.nav_buttons.append(button)
            rl.addWidget(button)
        rl.addStretch(1)
        rl.addWidget(line())
        rl.addSpacing(8)
        rl.addWidget(label("PHONE + AIRPODS", style="eyebrow"))
        rl.addWidget(label("Configure on desktop. Use Horus privately from your iPhone and earbuds.", style="muted"))
        rl.addSpacing(12)
        rl.addWidget(label("v0.15  •  PRIVATE BACKEND", style="eyebrow"))

        workspace = QWidget()
        outer.addWidget(workspace, 1)
        wl = column(workspace, gap=0, margins=(32, 22, 32, 14))
        top = QHBoxLayout()
        top.addWidget(label("HORUS  /  LOCAL DESKTOP", style="eyebrow", wrap=False))
        top.addStretch(1)
        self.connect_state = label("●  CHECKING ENGINE", style="statusOffline")
        top.addWidget(self.connect_state)
        self.engine_button = action("START ENGINE")
        self.engine_button.clicked.connect(self._engine_action)
        top.addSpacing(17)
        top.addWidget(self.engine_button)
        wl.addLayout(top)
        wl.addSpacing(16)
        self.pages = QStackedWidget()
        wl.addWidget(self.pages, 1)
        self._home()
        self._setup()
        self._conversation()
        self._awareness()
        self._settings_page()
        wl.addSpacing(12)
        wl.addWidget(line())
        self.footer = label("Nothing is simulated. Status comes from your local Horus backend.",
                            style="muted")
        wl.addWidget(self.footer)
        self.navigate(1 if not self.settings.value("onboardingSeen", False, type=bool) else 0)

    def navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for n, button in enumerate(self.nav_buttons):
            button.setProperty("active", "true" if n == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 0 and not self.testing:
            self.settings.setValue("onboardingSeen", True)
        if index in (0, 1, 3):
            self.refresh()

    def _home(self) -> None:
        """First-class operational overview; never imply unobserved activity."""
        page = QWidget()
        lay = column(page, gap=14)
        section_title(lay, "Overview", "Your Horus workspace",
                      "One place to see what is ready, what needs setup, and what actually happened.")

        intro = panel()
        il = column(intro, gap=10, margins=(23, 20, 23, 20))
        self.home_title = label("Checking your setup…", style="stepHead")
        il.addWidget(self.home_title)
        self.home_explain = label(
            "The desktop configures Horus. Your iPhone and AirPods are the daily interface.",
            style="muted")
        il.addWidget(self.home_explain)
        buttons = QHBoxLayout()
        self.home_next = action("CONTINUE SETUP  →", primary=True)
        self.home_next.clicked.connect(lambda: self.navigate(1))
        buttons.addWidget(self.home_next)
        converse = action("OPEN CONVERSATION")
        converse.clicked.connect(lambda: self.navigate(2))
        buttons.addWidget(converse)
        buttons.addStretch(1)
        il.addLayout(buttons)
        self.home_progress = label("Setup status not checked.", style="muted")
        il.addWidget(self.home_progress)
        lay.addWidget(intro)

        overview = QHBoxLayout()
        overview.setSpacing(11)
        self.home_engine = Metric("Backend", "—", "Awaiting actual health check")
        self.home_model = Metric("AI configuration", "—", "Checking saved provider")
        self.home_phone = Metric("iPhone", "—", "No authenticated setup request")
        self.home_airpods = Metric("AirPods", "—", "Physical audio test is separate")
        for tile in (self.home_engine, self.home_model, self.home_phone, self.home_airpods):
            overview.addWidget(tile, 1)
        lay.addLayout(overview)

        details = QHBoxLayout()
        details.setSpacing(12)
        left = panel()
        ll = column(left, gap=12, margins=(23, 20, 23, 20))
        ll.addWidget(label("ACTIVE CAPABILITIES", style="eyebrow"))
        ll.addWidget(label("What Horus can actually see", style="panelTitle"))
        self.home_watch_text = label("Watches: not yet checked", style="muted")
        self.home_memory_text = label("Object memory: not yet checked", style="muted")
        self.home_monitor_text = label("Monitor: not yet checked", style="muted")
        ll.addWidget(self.home_watch_text)
        ll.addWidget(self.home_memory_text)
        ll.addWidget(self.home_monitor_text)
        ll.addStretch(1)
        activity = action("VIEW ACTIVITY  →")
        activity.clicked.connect(lambda: self.navigate(3))
        ll.addWidget(activity, alignment=Qt.AlignLeft)
        details.addWidget(left, 1)

        right = panel()
        rl = column(right, gap=12, margins=(23, 20, 23, 20))
        rl.addWidget(label("LATEST RECORDED SIGNAL", style="eyebrow"))
        rl.addWidget(label("Evidence, not decoration", style="panelTitle"))
        self.home_last_signal = label(
            "No signal loaded. Alerts appear only if the backend actually recorded one.",
            style="muted")
        rl.addWidget(self.home_last_signal)
        rl.addStretch(1)
        rl.addWidget(label(
            "A watch being registered is not evidence it has checked a source. "
            "APNs accepting a notification does not prove your phone received it.",
            style="muted"))
        details.addWidget(right, 1)
        lay.addLayout(details, 1)
        self.pages.addWidget(page)

    def _setup_card(self, number: int, title: str, description: str) -> QVBoxLayout:
        frame = panel()
        lay = column(frame, gap=9, margins=(20, 16, 20, 17))
        head = QHBoxLayout()
        heading = label(f"{number:02d}   {title}", style="stepHead")
        head.addWidget(heading, 1)
        status = label("NOT CHECKED", style="stepPending")
        head.addWidget(status)
        self.setup_states.append(status)
        lay.addLayout(head)
        lay.addWidget(label(description, style="muted"))
        self.setup_layout.addWidget(frame)
        return lay

    def _setup(self) -> None:
        """Runbook with real actions, honest evidence, and a manual audio check."""
        page = QWidget()
        lay = column(page, gap=10)
        section_title(lay, "First-run setup", "Connect your iPhone and AirPods",
                      "Follow these steps. Every check distinguishes configuration from a verified result.")
        self.setup_progress = label("Checking setup progress…", style="panelTitle")
        lay.addWidget(self.setup_progress)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.setup_layout = column(body, gap=11, margins=(2, 4, 7, 15))
        self.setup_states: list[QLabel] = []

        engine = self._setup_card(
            1, "Start the Horus engine",
            "Runs on this Windows PC. An online backend proves the server answered a health check—not that audio works.")
        row = QHBoxLayout()
        e = action("START ENGINE", primary=True)
        e.clicked.connect(self._start_engine)
        row.addWidget(e)
        self.setup_restart = action("RESTART OWNED ENGINE")
        self.setup_restart.clicked.connect(self._restart_engine)
        row.addWidget(self.setup_restart)
        row.addStretch(1)
        engine.addLayout(row)

        model = self._setup_card(
            2, "Choose the AI model",
            "Configure OpenAI, Anthropic, OpenRouter, or local Ollama. A saved key is configuration; test a real answer afterward.")
        row = QHBoxLayout()
        configure = action("CONFIGURE AI  →", primary=True)
        configure.clicked.connect(lambda: self.navigate(4))
        row.addWidget(configure)
        trial = action("TEST IN CONVERSATION")
        trial.clicked.connect(lambda: self._prompt_from_setup())
        row.addWidget(trial)
        row.addStretch(1)
        model.addLayout(row)

        lan = self._setup_card(
            3, "Connect the PC to your private network",
            "Required for the iPhone. Only enable on a trusted network; LAN HTTP is not encrypted.")
        self.lan_state = label("Not configured", style="muted")
        lan.addWidget(self.lan_state)
        self.lan_field = QLineEdit()
        self.lan_field.setPlaceholderText("PC address will appear here when LAN is enabled")
        self.lan_field.setReadOnly(True)
        lan.addWidget(self.lan_field)
        row = QHBoxLayout()
        b = action("ENABLE LAN", primary=True)
        b.clicked.connect(self._enable_lan)
        row.addWidget(b)
        self.copy_url = action("COPY ADDRESS")
        self.copy_url.clicked.connect(lambda: self._copy(self.lan_field.text(), secret=False))
        row.addWidget(self.copy_url)
        self.copy_secret = action("COPY PRIVATE TOKEN")
        self.copy_secret.clicked.connect(self._copy_token)
        row.addWidget(self.copy_secret)
        row.addStretch(1)
        lan.addLayout(row)
        lan.addWidget(label(
            "After enabling, restart the engine above. Never forward port 8765 to the public internet. "
            "The copied API token is a credential.",
            style="muted"))

        iphone = self._setup_card(
            4, "Install Horus on your iPhone and verify it",
            "Use your Mac and Xcode to install the iOS app. On the phone enter the LAN URL and token above, "
            "then tap 'Verify iPhone connection to Horus' in iPhone Horus Settings.")
        row = QHBoxLayout()
        guide = action("IPHONE INSTALL GUIDE  ↗")
        guide.clicked.connect(lambda: webbrowser.open(
            "https://github.com/US0RIS/Jarvis-for-MRB/blob/main/ios/README.md"))
        row.addWidget(guide)
        check = action("CHECK PHONE RECEIPT")
        check.clicked.connect(self.refresh)
        row.addWidget(check)
        row.addStretch(1)
        iphone.addLayout(row)
        self.phone_receipt_description = label(
            "Not checked. Authentication from the phone app is different from a browser health request.",
            style="muted")
        iphone.addWidget(self.phone_receipt_description)

        airpods = self._setup_card(
            5, "Verify AirPods audio on the actual iPhone",
            "Connect AirPods in iPhone Bluetooth settings. In Horus turn on 'Speak Jarvis responses' and "
            "'Prefer Bluetooth microphone'. Use Push to Talk, ask Horus to remember an item, "
            "then ask where it is. Check audio stays private when the AirPods disconnect.")
        self.audio_checkbox = QCheckBox(
            "I personally completed the spoken AirPods test on my iPhone")
        self.audio_checkbox.setChecked(
            self.settings.value("airpodsTested", False, type=bool))
        self.audio_checkbox.toggled.connect(self._confirm_audio_test)
        airpods.addWidget(self.audio_checkbox)
        airpods.addWidget(label(
            "This is your confirmation, not device telemetry. The Windows app cannot detect an AirPods audio route.",
            style="muted"))

        self.setup_layout.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        end = QHBoxLayout()
        end.addWidget(label("No background microphone, camera, or wearables are required.", style="muted"))
        end.addStretch(1)
        finish = action("OPEN OVERVIEW  →", primary=True)
        finish.clicked.connect(lambda: self.navigate(0))
        end.addWidget(finish)
        lay.addLayout(end)
        self.pages.addWidget(page)
        self._sync_lan()
        self._apply_setup_state()

    def _prompt_from_setup(self) -> None:
        self.navigate(2)
        self._prompt("Explain what Horus can do in one short sentence.")

    def _confirm_audio_test(self, confirmed: bool) -> None:
        if not self.testing:
            self.settings.setValue("airpodsTested", bool(confirmed))
        self._apply_setup_state()

    def _apply_setup_state(self) -> None:
        """One accurate state model shared by Home and guided setup."""
        try:
            config = load_server_config()
            inference = self._read_inference()
            setup = derive_setup_state(
                self._latest_snapshot, inference, config.bind_host,
                bool(config.api_token), self.audio_checkbox.isChecked())
        except Exception as exc:
            self.home_title.setText("Setup status unavailable")
            self.home_explain.setText(str(exc)[:190])
            return
        statuses = [
            "ONLINE" if setup.engine_online else "NOT RUNNING",
            "CONFIGURED" if setup.provider_configured else "NEEDS CONFIGURATION",
            "LAN ACTIVE" if setup.lan_ready else "NOT REACHABLE FROM PHONE",
            "APP VERIFIED" if setup.phone_recent else "NOT VERIFIED RECENTLY",
            "YOU CONFIRMED" if setup.audio_user_confirmed else "NOT TESTED",
        ]
        for lbl, status, completed in zip(self.setup_states, statuses, setup.checks):
            lbl.setText(status)
            lbl.setObjectName("stepComplete" if completed else "stepPending")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
        self.setup_progress.setText(f"{setup.completed} of 5 setup checks complete")
        if setup.completed == 5:
            self.home_title.setText("Horus is configured for your workflow.")
            self.home_explain.setText(
                "The last iPhone check-in was authenticated. AirPods audio was confirmed by you, not remotely measured.")
            self.home_next.setText("REVIEW SETUP")
        else:
            names = ("start the Windows engine", "configure an AI model",
                     "enable and restart private LAN access", "verify the iPhone app",
                     "test speech through AirPods")
            next_name = names[setup.next_step or 0]
            self.home_title.setText("One step at a time. Get Horus usable.")
            self.home_explain.setText(f"Next: {next_name}. Your desktop is the setup and control surface.")
            self.home_next.setText("CONTINUE SETUP  →")
        self.home_progress.setText(
            f"{setup.completed}/5 verified or user-confirmed checks. A selected model still needs a real answer test.")
        self.home_engine.value.setText("ONLINE" if setup.engine_online else "OFFLINE")
        self.home_engine.footnote.setText("Actual health check" if setup.engine_online else "Start the engine")
        self.home_model.value.setText(setup.provider.upper() if setup.provider_configured else "NOT READY")
        self.home_model.footnote.setText(
            (setup.model or "Choose a model")[:35] if setup.provider_configured else "Add provider credentials")
        self.home_phone.value.setText("VERIFIED" if setup.phone_recent else "UNKNOWN")
        self.home_phone.footnote.setText(
            "Authenticated app request ≤5 min" if setup.phone_recent else "No recent authenticated receipt")
        self.home_airpods.value.setText("USER TESTED" if setup.audio_user_confirmed else "NOT TESTED")
        self.home_airpods.footnote.setText(
            "Self-confirmed, not remotely measured" if setup.audio_user_confirmed else "Requires physical audio check")
        self.phone_receipt_description.setText(
            "An authenticated iPhone app request reached this backend in the last five minutes. "
            "This does not verify Bluetooth audio." if setup.phone_recent else
            "No recent authenticated app check-in. Open Horus Settings on your iPhone and tap Verify iPhone connection.")
        if not setup.lan_ready and setup.engine_online and config.api_token and config.bind_host == "0.0.0.0":
            self.lan_state.setText(
                "LAN was saved, but the running engine is not yet listening on it. Restart the owned engine.")
        self.setup_restart.setEnabled("engine" not in self._jobs)

    def _conversation(self) -> None:
        page = QWidget()
        lay = column(page, gap=12)
        section_title(lay, "01  /  Conversation", "Talk to Horus",
                      "Ask, investigate, remember and act through the actual assistant.")
        intro = panel()
        intro_lay = QHBoxLayout(intro)
        intro_lay.setContentsMargins(22, 15, 20, 15)
        intro_lay.addWidget(HorusMark(48))
        msg = column(gap=4)
        msg.addWidget(label("Ready to assist", style="panelTitle"))
        msg.addWidget(label("AI answers use your selected provider. Real actions still require their normal approvals.",
                            style="muted"))
        intro_lay.addLayout(msg, 1)
        lay.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.chat_scroll = scroll
        container = QWidget()
        self.chat_layout = column(container, gap=14, margins=(6, 18, 6, 18))
        self.empty_conversation = QWidget()
        intro_empty = column(self.empty_conversation, gap=15)
        intro_empty.addStretch(1)
        orb_line = QHBoxLayout()
        orb_line.addStretch(1)
        orb_line.addWidget(HorusMark(102))
        orb_line.addStretch(1)
        intro_empty.addLayout(orb_line)
        lead = label("Intelligence at your command")
        lead.setFont(QFont("Segoe UI", 19, QFont.DemiBold))
        lead.setAlignment(Qt.AlignCenter)
        intro_empty.addWidget(lead)
        sub = label("Your conversation begins here. All replies come from your real Horus engine.",
                    style="muted")
        sub.setAlignment(Qt.AlignCenter)
        intro_empty.addWidget(sub)
        intro_empty.addSpacing(10)
        quicks = QHBoxLayout()
        quicks.addStretch(1)
        for example in ("What are you watching?", "Where are my keys?", "Give me a briefing"):
            b = action(example)
            b.clicked.connect(lambda _c=False, text=example: self._prompt(text))
            quicks.addWidget(b)
        quicks.addStretch(1)
        intro_empty.addLayout(quicks)
        intro_empty.addStretch(1)
        self.chat_layout.addWidget(self.empty_conversation)
        self.chat_layout.addStretch(1)
        scroll.setWidget(container)
        lay.addWidget(scroll, 1)

        compose = panel()
        cl = QHBoxLayout(compose)
        cl.setContentsMargins(15, 12, 12, 12)
        cl.setSpacing(12)
        self.composer = Composer()
        self.composer.setPlaceholderText("Message Horus...  (Enter to send · Shift+Enter for a new line)")
        self.composer.setMaximumHeight(83)
        self.composer.setMinimumHeight(64)
        self.composer.submitted.connect(self.send)
        cl.addWidget(self.composer, 1)
        self.send_button = action("SEND  ↗", primary=True)
        self.send_button.setMinimumHeight(49)
        self.send_button.clicked.connect(self.send)
        cl.addWidget(self.send_button)
        lay.addWidget(compose)
        self.pages.addWidget(page)

    def _bubble(self, role: str, content: str) -> None:
        self.empty_conversation.hide()
        row = QHBoxLayout()
        is_user = role == "YOU"
        if is_user:
            row.addStretch(1)
        frame = QFrame()
        frame.setObjectName("messageUser" if is_user else "messageAssistant")
        frame.setMaximumWidth(790)
        msg_lay = column(frame, gap=6, margins=(17, 13, 17, 13))
        msg_lay.addWidget(label(role, style="eyebrow"))
        body = label(content)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setMinimumWidth(160)
        msg_lay.addWidget(body)
        row.addWidget(frame, 0 if is_user else 1)
        if not is_user:
            row.addStretch(1)
        widget = QWidget()
        widget.setLayout(row)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, widget)
        QTimer.singleShot(60, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()))

    def _prompt(self, text: str) -> None:
        self.composer.setPlainText(text)
        self.send()

    def send(self) -> None:
        message = self.composer.toPlainText().strip()
        if not message or "chat" in self._jobs:
            return
        self.composer.clear()
        self._bubble("YOU", message)
        self.send_button.setEnabled(False)
        self.notice("Horus is reasoning and may execute permitted tools…")
        def go() -> dict[str, Any]:
            if not self.backend_running() and not self.start_backend():
                raise RuntimeError("The Horus backend could not start. Check port 8765.")
            return request("command", method="POST", timeout=180,
                           body={"text": message, "session_id": self.session,
                                 "context": {"channel": "text"}})
        self.task("chat", go, self._chat_finished)

    def _chat_finished(self, answer: Any, error: str) -> None:
        self.send_button.setEnabled(True)
        if error:
            self._bubble("HORUS · CONNECTION ERROR", error)
            self.notice("Command failed. Check the server or AI provider in Settings.")
        else:
            self._bubble("HORUS", str(answer.get("message") or "No response."))
            self.notice("Ready. Responses are generated by your connected Horus backend.")
            if not answer.get("ok", True):
                self.notice("Horus reported an unsuccessful command; review the reply.")
        self.refresh()

    def _awareness(self) -> None:
        page = QWidget()
        lay = column(page, gap=14)
        head = QHBoxLayout()
        header = column(gap=4)
        section_title(header, "02  /  Awareness", "What's happening",
                      "Only real saved memories, registered watches and recorded signals.")
        head.addLayout(header, 1)
        refresh = action("↻  REFRESH")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh, alignment=Qt.AlignTop)
        lay.addLayout(head)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.tile_engine = Metric("Engine", "—", "Waiting for backend")
        self.tile_watches = Metric("Active watches", "—", "No observation yet")
        self.tile_memory = Metric("Object memory", "—", "User-reported locations")
        self.tile_provider = Metric("AI provider", "—", "Not yet inspected")
        for tile in (self.tile_engine, self.tile_watches, self.tile_memory, self.tile_provider):
            metrics.addWidget(tile, 1)
        lay.addLayout(metrics)

        self.runner_text = label("Runner status not yet checked.", style="muted")
        lay.addWidget(self.runner_text)
        section = panel()
        sl = column(section, gap=12, margins=(24, 21, 24, 24))
        sl.addWidget(label("RECENT ATTENTION", style="eyebrow"))
        sl.addWidget(label("Signals, not theater", style="panelTitle"))
        sl.addWidget(label("Alerts and briefings are shown exactly as your backend recorded them.",
                           style="muted"))
        sl.addWidget(line())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(260)
        box = QWidget()
        self.activity_layout = column(box, gap=9)
        self.activity_layout.addWidget(label("No recorded signals loaded yet.", style="muted"))
        self.activity_layout.addStretch(1)
        scroll.setWidget(box)
        sl.addWidget(scroll, 1)
        lay.addWidget(section, 1)
        self.pages.addWidget(page)

    def _control(self) -> None:
        page = QWidget()
        lay = column(page, gap=16)
        section_title(lay, "03  /  Control", "Systems & devices",
                      "Operate the real backend and connect your iPhone over a trusted network.")
        backend = panel()
        bl = column(backend, gap=12, margins=(24, 22, 24, 22))
        bl.addWidget(label("LOCAL ENGINE", style="eyebrow"))
        self.engine_detail = label("Backend has not been checked.", style="panelTitle")
        bl.addWidget(self.engine_detail)
        btns = QHBoxLayout()
        start = action("START ENGINE", primary=True)
        start.clicked.connect(self._start_engine)
        btns.addWidget(start)
        restart = action("RESTART OWNED ENGINE")
        restart.clicked.connect(self._restart_engine)
        btns.addWidget(restart)
        btns.addStretch(1)
        bl.addLayout(btns)
        lay.addWidget(backend)
        phone = panel()
        pl = column(phone, gap=11, margins=(24, 22, 24, 22))
        pl.addWidget(label("IPHONE / AIRPODS BRIDGE", style="eyebrow"))
        pl.addWidget(label("Private phone connection", style="panelTitle"))
        self.lan_state = label("LAN access is not configured.", style="muted")
        pl.addWidget(self.lan_state)
        self.lan_field = QLineEdit()
        self.lan_field.setReadOnly(True)
        self.lan_field.setPlaceholderText("Not configured")
        pl.addWidget(self.lan_field)
        buttons = QHBoxLayout()
        configure = action("ENABLE PRIVATE LAN", primary=True)
        configure.clicked.connect(self._enable_lan)
        buttons.addWidget(configure)
        self.copy_url = action("COPY ADDRESS")
        self.copy_url.clicked.connect(lambda: self._copy(self.lan_field.text(), secret=False))
        buttons.addWidget(self.copy_url)
        self.copy_secret = action("COPY API TOKEN")
        self.copy_secret.clicked.connect(self._copy_token)
        buttons.addWidget(self.copy_secret)
        buttons.addStretch(1)
        pl.addLayout(buttons)
        pl.addWidget(label("Never forward port 8765 to the internet. LAN HTTP is unencrypted. "
                           "Copy the address and secret token into Horus Settings on your iPhone.",
                           style="muted"))
        lay.addWidget(phone)
        callless = panel()
        c = column(callless, gap=11, margins=(24, 20, 24, 20))
        c.addWidget(label("CALLLESS  /  PROTOTYPE", style="eyebrow"))
        c.addWidget(label("Browser-to-browser conversations", style="panelTitle"))
        c.addWidget(label("Opens the self-hosted browser client. A shared HTTPS hub is required for remote use; "
                          "native iPhone calling is not shipped.", style="muted"))
        b = action("OPEN CALLLESS ↗")
        b.clicked.connect(self._open_callless)
        c.addWidget(b, alignment=Qt.AlignLeft)
        lay.addWidget(callless)
        lay.addStretch(1)
        self.pages.addWidget(page)
        self._sync_lan()

    def _settings_page(self) -> None:
        page = QWidget()
        lay = column(page, gap=15)
        section_title(lay, "04  /  Configuration", "Settings",
                      "Select the real inference engine. Hosted prompts go to the provider you choose.")
        p = panel()
        f = column(p, gap=14, margins=(26, 23, 26, 24))
        f.addWidget(label("MODEL & INFERENCE", style="eyebrow"))
        f.addWidget(label("Connection to intelligence", style="panelTitle"))
        state = self._read_inference()
        provider_row = QHBoxLayout()
        provider_row.addWidget(label("Provider", style="muted"))
        self.provider = QComboBox()
        for name in ("ollama", "openai", "anthropic", "openrouter"):
            self.provider.addItem(name.title() if name != "ollama" else "Local Ollama", name)
        self.provider.setCurrentIndex(max(0, self.provider.findData(state["provider"])))
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.provider.setMinimumWidth(300)
        provider_row.addWidget(self.provider)
        f.addLayout(provider_row)
        self.model = QLineEdit(state["model"])
        self.model.setPlaceholderText("Provider-supported model identifier")
        f.addWidget(label("Model ID", style="muted"))
        f.addWidget(self.model)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("Only needed when using a new hosted provider key")
        self.api_key.setEnabled(self.provider.currentData() != "ollama")
        f.addWidget(label("API key", style="muted"))
        f.addWidget(self.api_key)
        f.addWidget(label("Keys are stored in Windows Credential Manager, never in the Horus settings JSON. "
                          "Use the OpenAI, Anthropic or OpenRouter API, or install Ollama separately.",
                          style="muted"))
        save = action("SAVE INFERENCE SETTINGS", primary=True)
        save.clicked.connect(self._save_inference)
        f.addWidget(save, alignment=Qt.AlignLeft)
        self.model_notice = label(
            f"Current: {state['provider']} / {state['model']}" +
            ("  ·  API key configured" if state.get("key_configured") else ""),
            style="muted")
        f.addWidget(self.model_notice)
        lay.addWidget(p)
        about = panel()
        ab = column(about, gap=9, margins=(26, 22, 26, 22))
        ab.addWidget(label("PRIVACY / DELIVERY", style="eyebrow"))
        ab.addWidget(label("Local by design. Honest about what is live.", style="panelTitle"))
        ab.addWidget(label("The iPhone is a separately installed Xcode build. Real AirPods routing "
                           "has not yet passed physical-device acceptance. Callless remains a prototype. "
                           "Monitoring and device status never come from demo data.", style="muted"))
        lay.addWidget(about)
        lay.addStretch(1)
        self.pages.addWidget(page)

    def _read_inference(self) -> dict[str, Any]:
        try:
            return inference_status()
        except Exception:
            return {"provider": "ollama", "model": "qwen3:8b", "key_configured": False}

    def _provider_changed(self, _index: int) -> None:
        if self._building:
            return
        kind = self.provider.currentData()
        self.model.setText(DEFAULT_MODELS.get(kind, "qwen3:8b"))
        self.api_key.clear()
        self.api_key.setEnabled(kind != "ollama")

    def _save_inference(self) -> None:
        provider = str(self.provider.currentData())
        model = self.model.text().strip()
        key = self.api_key.text().strip()
        self.api_key.clear()   # do not leave secrets visible in the UI
        self.model_notice.setText("Saving configuration…")
        self.task("save_inference",
                  lambda: configure_inference(provider, model, key if key else None),
                  self._save_finished)

    def _save_finished(self, result: Any, error: str) -> None:
        if error:
            self.model_notice.setText("Not saved: " + error)
            self.notice("Model configuration failed; see Settings.")
            return
        self.model_notice.setText(
            f"Saved: {result['provider']} / {result['model']}" +
            ("  ·  Key ready" if result.get("key_configured") else "  ·  No hosted key"))
        self.notice("Inference settings saved. Your next request uses the selected provider.")
        self.refresh()

    def _sync_lan(self) -> None:
        cfg = load_server_config()
        configured = cfg.bind_host not in {"localhost", "127.0.0.1", "::1"} and bool(cfg.api_token)
        self.lan_state.setText(
            "Private LAN configured. Phone access requires the running backend to use this bind setting."
            if configured else "Not enabled. Horus currently permits localhost connections only.")
        self.lan_field.setText(lan_url() if configured else "")
        self.copy_url.setEnabled(configured)
        self.copy_secret.setEnabled(configured)

    def _enable_lan(self) -> None:
        answer = QMessageBox.question(
            self, "Enable LAN access?",
            "This binds the Horus admin API to your PC's network interfaces.\n"
            "Use only a trusted private network. HTTP traffic is not encrypted.\n"
            "Never forward port 8765 to the public internet.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            configure_remote_access()
            self._sync_lan()
            self.notice("LAN enabled. Restart the backend to apply the new bind settings.")
        except Exception as exc:
            QMessageBox.warning(self, "LAN setup failed", str(exc)[:300])

    def _copy(self, value: str, *, secret: bool) -> None:
        if not value:
            return
        QApplication.clipboard().setText(value)
        self.notice("API token copied: treat your clipboard as sensitive." if secret
                    else "Private LAN address copied. Paste it into iPhone Horus Settings.")

    def _copy_token(self) -> None:
        cfg = load_server_config()
        if cfg.api_token and cfg.bind_host not in {"127.0.0.1", "localhost", "::1"}:
            self._copy(cfg.api_token, secret=True)

    def _engine_action(self) -> None:
        if self.connect_state.objectName() == "statusOnline":
            self.navigate(2)
        else:
            self._start_engine()

    def _start_engine(self) -> None:
        self.engine_button.setEnabled(False)
        self.notice("Starting Horus backend…")
        self.task("engine", self.start_backend, self._engine_started)

    def _restart_engine(self) -> None:
        confirm = QMessageBox.question(
            self, "Restart Horus engine?",
            "An active model response or automation step could be interrupted. Restart now?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if confirm != QMessageBox.Yes:
            return
        self.engine_button.setEnabled(False)
        self.notice("Restarting the installed Horus background service…")
        self.task("engine", lambda: restart_owned_backend(self.start_backend), self._engine_started)

    def _engine_started(self, ok: Any, error: str) -> None:
        self.engine_button.setEnabled(True)
        if error or not ok:
            self.notice("Backend unavailable: " + (error or "Startup failed."))
        else:
            self.notice("Horus engine is listening locally.")
        self.refresh()

    def _open_callless(self) -> None:
        def ready() -> bool:
            return self.backend_running() or self.start_backend()
        def done(ok: Any, error: str) -> None:
            if error or not ok:
                self.notice("Unable to start Callless: " + (error or "backend unavailable"))
            else:
                webbrowser.open(_server_url("callless/"))
                self.notice("Opened Callless prototype in your browser.")
        self.task("callless", ready, done)

    def refresh(self) -> None:
        if self.testing:
            return
        self.task("snapshot", snapshot, self._snapshot_finished)

    def _snapshot_finished(self, data: Any, error: str) -> None:
        online = bool(data and data.get("online")) and not error
        self.connect_state.setText("●  ENGINE ONLINE" if online else "●  ENGINE OFFLINE")
        self.connect_state.setObjectName("statusOnline" if online else "statusOffline")
        self.connect_state.style().unpolish(self.connect_state)
        self.connect_state.style().polish(self.connect_state)
        self.engine_button.setText("MANAGE ENGINE" if online else "START ENGINE")
        self.engine_button.setEnabled("engine" not in self._jobs)
        self.engine_detail.setText("Running on this PC" if online else "Stopped or unreachable")
        if not online:
            for item in (self.tile_engine, self.tile_watches, self.tile_memory, self.tile_provider):
                item.value.setText("—")
                item.footnote.setText("Unavailable — start engine")
            self.runner_text.setText("No monitoring state: backend is offline.")
            self._render_activity([])
            return
        health = data.get("health") or {}
        self.tile_engine.value.setText("ONLINE")
        self.tile_engine.footnote.setText("Local server active")
        infer = health.get("inference") or {}
        self.tile_provider.value.setText(str(infer.get("provider") or "—").upper())
        self.tile_provider.footnote.setText(str(infer.get("model") or "Not configured")[:46])
        if isinstance(data.get("watches"), dict):
            watches = data["watches"].get("watches") or []
            active = sum(1 for watch in watches if watch.get("state") == "active")
            self.tile_watches.value.setText(str(active))
            self.tile_watches.footnote.setText(f"{len(watches)} registered")
            runner = data["watches"].get("runner") or {}
            self.runner_text.setText("Watch checker: " + str(runner.get("status") or
                health.get("external_watches") or "state unknown") +
                "  ·  Registration does not guarantee a check occurred.")
        else:
            self.tile_watches.value.setText("—")
            self.tile_watches.footnote.setText("Watch status unavailable")
            self.runner_text.setText("Could not read the watch runner state.")
        memory = data.get("memory")
        if isinstance(memory, dict):
            self.tile_memory.value.setText(str((memory.get("status") or {}).get("objects", "—")))
            self.tile_memory.footnote.setText("User-reported, not observed")
        else:
            self.tile_memory.value.setText("—")
            self.tile_memory.footnote.setText("Memory status unavailable")
        ledger = data.get("ledger")
        self._render_activity(ledger.get("items", []) if isinstance(ledger, dict) else [])

    def _render_activity(self, items: list[Any]) -> None:
        while self.activity_layout.count() > 1:
            item = self.activity_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not items:
            self.activity_layout.insertWidget(0, label(
                "No recorded signals to show. Horus won't invent activity.", style="muted"))
            return
        for entry in items[:8]:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("title") or entry.get("kind") or "Recorded event")[:130]
            detail = str(entry.get("decision") or "recorded")
            source = str(entry.get("source_url") or entry.get("source") or "")
            stamp = str(entry.get("created_at") or "")
            excerpt = "  •  ".join(x for x in (detail, stamp[:16], source[:65]) if x)
            row = QFrame()
            row.setObjectName("metric")
            r = column(row, gap=3, margins=(14, 10, 14, 10))
            r.addWidget(label(name, style="panelTitle"))
            r.addWidget(label(excerpt or "Source metadata unavailable.", style="muted"))
            self.activity_layout.insertWidget(self.activity_layout.count() - 1, row)


def start_qt(start_backend: Callable[[], bool],
             backend_running: Callable[[], bool], *, self_test: bool = False) -> int:
    if self_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Horus Mission Control")
    app.setOrganizationName("Horus")
    window = MissionControlWindow(start_backend=start_backend,
                                  backend_running=backend_running,
                                  testing=self_test)
    window.show()
    if self_test:
        app.processEvents()
        for index in range(4):
            window.navigate(index)
            app.processEvents()
        assert window.pages.count() == 4
        assert window.nav_buttons[0].text().strip() == "Conversation"
        window.close()
        return 0
    return app.exec()
