import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run_eval import keep_best_retry_score


class RetryScoringSelfTest(unittest.TestCase):
    def test_first_scored_attempt_is_recorded_even_when_zero(self):
        details = {"attempt": 1}

        score, attempt, final_details, reason = keep_best_retry_score(
            best_score=0,
            best_attempt=0,
            final_details={},
            fail_reason="Unknown",
            candidate_score=0,
            candidate_attempt=1,
            candidate_details=details,
            candidate_reason="Partial: geometry incorrect",
        )

        self.assertEqual(score, 0)
        self.assertEqual(attempt, 1)
        self.assertIs(final_details, details)
        self.assertEqual(reason, "Partial: geometry incorrect")

    def test_lower_later_score_does_not_replace_best(self):
        best_details = {"attempt": 1}
        candidate_details = {"attempt": 2}

        score, attempt, final_details, reason = keep_best_retry_score(
            best_score=0.5,
            best_attempt=1,
            final_details=best_details,
            fail_reason="Partial: connection incorrect",
            candidate_score=0.25,
            candidate_attempt=2,
            candidate_details=candidate_details,
            candidate_reason="Partial: supports incorrect",
        )

        self.assertEqual(score, 0.5)
        self.assertEqual(attempt, 1)
        self.assertIs(final_details, best_details)
        self.assertEqual(reason, "Partial: connection incorrect")

    def test_higher_later_score_replaces_best(self):
        best_details = {"attempt": 1}
        candidate_details = {"attempt": 2}

        score, attempt, final_details, reason = keep_best_retry_score(
            best_score=0.25,
            best_attempt=1,
            final_details=best_details,
            fail_reason="Partial: supports incorrect",
            candidate_score=0.75,
            candidate_attempt=2,
            candidate_details=candidate_details,
            candidate_reason="Partial: loads incorrect",
        )

        self.assertEqual(score, 0.75)
        self.assertEqual(attempt, 2)
        self.assertIs(final_details, candidate_details)
        self.assertEqual(reason, "Partial: loads incorrect")

    def test_equal_score_keeps_earlier_attempt(self):
        best_details = {"attempt": 1}
        candidate_details = {"attempt": 2}

        score, attempt, final_details, reason = keep_best_retry_score(
            best_score=0.5,
            best_attempt=1,
            final_details=best_details,
            fail_reason="Partial: connection incorrect",
            candidate_score=0.5,
            candidate_attempt=2,
            candidate_details=candidate_details,
            candidate_reason="Partial: connection incorrect again",
        )

        self.assertEqual(score, 0.5)
        self.assertEqual(attempt, 1)
        self.assertIs(final_details, best_details)
        self.assertEqual(reason, "Partial: connection incorrect")


if __name__ == "__main__":
    unittest.main(verbosity=2)
