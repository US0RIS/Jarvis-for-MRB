from __future__ import annotations

import os
import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from jarvis_mrb import event_bus
from jarvis_mrb import world_armor_push as push

TOKEN = "cd" * 32


class ProactiveClosedAppDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "push.sqlite3"
        flags = patch.dict(os.environ, {"JARVIS_PUSH_ENABLED": "1"}, clear=False)
        flags.start()
        self.addCleanup(flags.stop)
        store = patch.object(push, "PUSH_STORE", self.db)
        store.start()
        self.addCleanup(store.stop)
        worker = patch.object(push, "start_worker", return_value=True)
        worker.start()
        self.addCleanup(worker.stop)
        publish = patch.object(event_bus.companion_events, "publish")
        self.publish = publish.start()
        self.addCleanup(publish.stop)
        record = patch.object(event_bus, "_record_proactive_occurrence")
        record.start()
        self.addCleanup(record.stop)
        push.register_device(TOKEN)

    def _rows(self) -> list[tuple[str, str, str]]:
        with closing(sqlite3.connect(self.db)) as conn:
            return conn.execute("SELECT priority,title,body FROM push_outbox ORDER BY created_at").fetchall()

    def test_warning_interventions_are_queued_once_and_info_never(self) -> None:
        message = "Agency needs your approval to continue Outdoor shoot: turn on Desk Lamp."
        event_bus.emit_proactive("Routine calendar sync finished.", severity="info")
        event_bus.emit_proactive(message, severity="warning")
        event_bus.emit_proactive(message, severity="warning")  # duplicate evidence/retry
        rows = self._rows()
        self.assertEqual(rows, [("warning", "Jarvis", message)])
        self.assertEqual(self.publish.call_count, 3)  # foreground channel still sees everything

    def test_disabled_push_keeps_foreground_alert(self) -> None:
        with patch.dict(os.environ, {"JARVIS_PUSH_ENABLED": "0", "JARVIS_WORLD_ARMOR_PUSH_ENABLED": "0"}):
            event_bus.emit_proactive("Something material changed.", severity="warning")
        self.assertEqual(self._rows(), [])
        self.publish.assert_called_once()

    def test_transport_failure_never_suppresses_alert(self) -> None:
        with patch.object(push, "enqueue_alert", side_effect=RuntimeError("disk full")):
            event_bus.emit_proactive("Something material changed.", severity="warning")
        self.publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
