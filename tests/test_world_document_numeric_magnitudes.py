from __future__ import annotations

import unittest

from jarvis_mrb.world_document_versions import _changed_passages, _numbers


class WorldDocumentNumericMagnitudeTests(unittest.TestCase):
    def test_currency_magnitude_is_preserved_as_one_numeric_value(self) -> None:
        self.assertEqual(
            _numbers("The working capital target shall be $8 million at Closing."),
            ["$8 million"],
        )
        self.assertEqual(
            _numbers("The purchase price is USD 1.25 billion."),
            ["USD 1.25 billion"],
        )

    def test_currency_magnitude_change_keeps_old_and_new_material_values(self) -> None:
        old = "The working capital target shall be $8 million at Closing."
        new = "The working capital target shall be $13 million at Closing."
        changes = _changed_passages(old, new)
        self.assertTrue(changes)
        headline = next(item for item in changes if item["numeric_change"])
        self.assertIn("$8 million", headline["old_numbers"])
        self.assertIn("$13 million", headline["new_numbers"])


if __name__ == "__main__":
    unittest.main()
