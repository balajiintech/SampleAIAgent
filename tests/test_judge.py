"""Swim-rule checks. These tests do not open Amazon."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.judge import judge_text


class JudgeTests(unittest.TestCase):
    def test_ip68_swim_pass(self) -> None:
        text = (
            "OpenSwim bone conduction headphones. "
            "IP68 waterproof for swimming and underwater use."
        )
        judgment = judge_text(text)
        self.assertTrue(judgment.swim_usable)
        self.assertEqual(judgment.status, "pass")
        self.assertIn("IP68", judgment.evidence)

    def test_sweat_only_reject(self) -> None:
        text = "Bone conduction headphones. IPX5 sweat and rain resistant for workouts."
        judgment = judge_text(text)
        self.assertFalse(judgment.swim_usable)
        self.assertEqual(judgment.status, "reject")
        self.assertIn("sweat", judgment.reason)

    def test_not_for_swimming_reject(self) -> None:
        text = (
            "Bone conduction headset. IP68 waterproof. "
            "Not for swimming. Water resistant for sweat."
        )
        judgment = judge_text(text)
        self.assertFalse(judgment.swim_usable)
        self.assertEqual(judgment.reason, "page says not for swimming")

    def test_explicit_ban_ignores_model(self) -> None:
        text = "Bone conduction headset. IP68. Not for swimming."
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("src.judge.openai_compatible_yes_no", return_value=True) as model:
                judgment = judge_text(text, allow_model=True)
        self.assertFalse(judgment.swim_usable)
        model.assert_not_called()

    def test_five_atm_passes_without_the_word_swimming(self) -> None:
        text = "Bone conductor headset rated 5 ATM for the pool."
        judgment = judge_text(text)
        self.assertTrue(judgment.swim_usable)
        self.assertEqual(judgment.reason, "swim-grade waterproof rating")

    def test_swim_words_without_rating_stay_unranked_without_a_key(self) -> None:
        text = "Bone conduction headphones for swimming. Waterproof design."
        judgment = judge_text(text)
        self.assertFalse(judgment.swim_usable)
        self.assertIn("unclear", judgment.reason)

    def test_borderline_model_yes_passes(self) -> None:
        text = "Bone conduction headphones for swimming. Waterproof design."
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("src.judge.openai_compatible_yes_no", return_value=True):
                judgment = judge_text(text, allow_model=True)
        self.assertTrue(judgment.swim_usable)
        self.assertEqual(judgment.reason, "model confirmed swim use on an unclear rating")

    def test_borderline_model_no_rejects(self) -> None:
        text = "Bone conduction headphones for swimming. Waterproof design."
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("src.judge.openai_compatible_yes_no", return_value=False):
                judgment = judge_text(text, allow_model=True)
        self.assertFalse(judgment.swim_usable)
        self.assertEqual(judgment.reason, "model judged the listing not usable while swimming")


if __name__ == "__main__":
    unittest.main()
