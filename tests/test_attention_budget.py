from __future__ import annotations

from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch

from jarvis_mrb import attention_budget, event_bus


class AttentionBudgetTests(unittest.TestCase):
    def setUp(self):
        attention_budget._reset_for_test()
        self.now=datetime.now(timezone.utc)

    def tearDown(self):
        attention_budget._reset_for_test()

    def test_disabled_default_does_not_change_legacy_proactive_delivery(self):
        with patch.dict("os.environ",{"JARVIS_ATTENTION_BUDGET_ENABLED":"0"}):
            for _ in range(15):
                self.assertTrue(attention_budget.may_deliver("info",now=self.now))
            self.assertEqual(attention_budget.status(now=self.now)["low_priority_suppressed_since_process_start"],0)

    def test_low_priority_budget_resets_after_one_hour(self):
        with patch.dict("os.environ",{"JARVIS_ATTENTION_BUDGET_ENABLED":"1"}):
            for _ in range(3):
                self.assertTrue(attention_budget.may_deliver("info",now=self.now))
            self.assertFalse(attention_budget.may_deliver("info",now=self.now))
            self.assertTrue(attention_budget.may_deliver("info",now=self.now+timedelta(hours=1,seconds=1)))
            self.assertEqual(attention_budget.status(now=self.now+timedelta(hours=1,seconds=1))["info_used_last_hour"],1)

    def test_urgent_and_warnings_always_bypass_budget(self):
        with patch.dict("os.environ",{"JARVIS_ATTENTION_BUDGET_ENABLED":"1"}):
            for _ in range(12): attention_budget.may_deliver("low",now=self.now)
            for priority in ("warning","urgent","critical","unknown"):
                for _ in range(20):
                    self.assertTrue(attention_budget.may_deliver(priority,now=self.now))

    def test_suppressed_info_never_records_false_delivery_occurrence(self):
        with (
            patch.dict("os.environ",{"JARVIS_ATTENTION_BUDGET_ENABLED":"1"}),
            patch.object(event_bus.companion_events,"publish") as publish,
            patch.object(event_bus,"_record_proactive_occurrence") as record,
        ):
            for _ in range(4):
                event_bus.emit_proactive("A repeated low-value reminder",severity="info")
            self.assertEqual(publish.call_count,3)
            self.assertEqual(record.call_count,3)
            event_bus.emit_proactive("Urgent factual alert",severity="urgent")
            self.assertEqual(publish.call_count,4)
            self.assertEqual(record.call_count,4)

    def test_invalid_naive_time_rejected(self):
        with patch.dict("os.environ",{"JARVIS_ATTENTION_BUDGET_ENABLED":"1"}),self.assertRaises(ValueError):
            attention_budget.may_deliver("info",now=datetime(2026,10,12))


if __name__=="__main__":
    unittest.main()
