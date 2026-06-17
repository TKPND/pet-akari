import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_candidate_batch as batch


class Phase4CandidateBatchTests(unittest.TestCase):
    def test_expand_recipe_grid_is_deterministic_and_capped(self):
        candidates = batch.expand_recipe_grid(
            attention_recipes=["a1", "a2"],
            notification_recipes=["n1", "n2"],
            error_recipes=["e1", "e2"],
            max_candidates=5,
        )

        self.assertEqual([candidate.candidate_id for candidate in candidates], ["C001", "C002", "C003", "C004", "C005"])
        self.assertEqual(
            candidates[0].recipes,
            {"attention": "a1", "notification": "n1", "error": "e1"},
        )
        self.assertEqual(
            candidates[4].recipes,
            {"attention": "a2", "notification": "n1", "error": "e1"},
        )

    def test_parse_recipe_csv_rejects_unknown_values(self):
        with self.assertRaisesRegex(ValueError, "unknown attention recipe"):
            batch.parse_recipe_csv("attention", "raised-hand-only,nope")
