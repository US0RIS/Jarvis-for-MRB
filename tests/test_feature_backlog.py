from __future__ import annotations

import unittest
from jarvis_mrb import feature_backlog


class FeatureBacklogTests(unittest.TestCase):
    def test_real_future_md_remains_full_scope_and_unverified(self):
        inv=feature_backlog.load()
        self.assertGreaterEqual(inv["total"],300)
        self.assertEqual(inv["total"],len(inv["items"]))
        self.assertEqual(len(set(x["id"] for x in inv["items"])),inv["total"])
        self.assertTrue(all(x["status"]=="not_verified_from_future_md" for x in inv["items"]))

    def test_stable_identity_independent_of_line_numbers(self):
        before="""## One
- **Reality Diff.** Compare states.
## Two
- **AirPods integration.** Audio.
"""
        after="""## One
Extra explanatory text.
- **Reality Diff.** Compare states.
## Two
- **AirPods integration.** Audio.
"""
        ids1=[x["id"] for x in feature_backlog.inventory(before)["items"]]
        ids2=[x["id"] for x in feature_backlog.inventory(after)["items"]]
        self.assertEqual(ids1,ids2)

    def test_same_name_in_separate_sections_is_not_collapsed(self):
        inv=feature_backlog.inventory("## A\n- **Awareness.**\n## B\n- **Awareness.**")
        self.assertEqual(inv["total"],2)
        self.assertNotEqual(inv["items"][0]["id"],inv["items"][1]["id"])

    def test_duplicate_entry_is_reported_and_not_marked_complete(self):
        inv=feature_backlog.inventory("## A\n- **Awareness.**\n- **Awareness.**")
        self.assertEqual(inv["total"],1)
        self.assertEqual(len(inv["duplicates"]),1)
        self.assertEqual(inv["items"][0]["status"],"not_verified_from_future_md")

    def test_github_projects_separate_from_direct_features(self):
        inv=feature_backlog.inventory(
            "## Open-source capability mining — GitHub survey 2026\n"
            "- **Some/repository — camera ingestion.** Investigate.\n"
            "## Real product features\n- **Remember a belief.** Implement."
        )
        self.assertEqual(inv["counts"],{"repository_candidate":1,"feature_idea":1})


if __name__=="__main__":
    unittest.main()
