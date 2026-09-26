"""The scorer must itself be correct, otherwise every reported number is meaningless."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evaluation.metrics import Confusion, Scores
from evaluation.run_evaluation import review_block
from pii_redactor.spans import Span


class ConfusionMath(unittest.TestCase):
    def test_precision_recall_f1(self):
        c = Confusion(tp=8, fp=2, fn=8)
        self.assertAlmostEqual(c.precision, 0.8)
        self.assertAlmostEqual(c.recall, 0.5)
        self.assertAlmostEqual(c.f1, 2 * 0.8 * 0.5 / 1.3)

    def test_empty_cases(self):
        self.assertEqual(Confusion().precision, 1.0)         # redacted nothing: no false alarms
        self.assertEqual(Confusion().recall, 1.0)            # no PII: nothing missed
        self.assertEqual(Confusion(fp=1).precision, 0.0)

    def test_accuracy_counts_true_negatives(self):
        self.assertAlmostEqual(Confusion(tp=1, tn=98, fp=1).accuracy, 0.99)


TEXT = "Mail jo@x.com or Rohan Dey today"           # 6 words
EMAIL = Span(5, 13, "EMAIL", "jo@x.com")
NAME = Span(17, 26, "PERSON", "Rohan Dey")


class Scoring(unittest.TestCase):
    def test_everything_correct(self):
        scores = Scores()
        scores.add_block(TEXT, confirmed=[EMAIL, NAME], wrong=[], missed=[])
        overall = scores.overall_spans()
        self.assertEqual((overall.precision, overall.recall, overall.f1), (1.0, 1.0, 1.0))
        self.assertEqual(scores.overall_tokens().accuracy, 1.0)

    def test_wrong_and_missed_spans(self):
        scores = Scores()
        # The tool redacted the email correctly and "today" wrongly, and missed the name.
        scores.add_block(TEXT, confirmed=[EMAIL], wrong=[Span(27, 32, "PERSON", "today")], missed=[NAME])
        person = scores.spans["PERSON"]
        self.assertEqual((person.tp, person.fp, person.fn), (0, 1, 1))
        self.assertEqual(scores.spans["EMAIL"].tp, 1)
        self.assertEqual(scores.wrong, [("PERSON", "today")])
        self.assertEqual(scores.missed, [("PERSON", "Rohan Dey")])

    def test_token_accuracy_overall_and_per_type(self):
        scores = Scores()
        # Words: Mail | jo@x.com | or | Rohan | Dey | today. The tool redacted only "Rohan" (a partial name).
        scores.add_block(TEXT, confirmed=[EMAIL], wrong=[Span(17, 22, "PERSON", "Rohan")], missed=[NAME])
        overall = scores.overall_tokens()
        self.assertEqual((overall.tp, overall.fp, overall.fn, overall.tn), (2, 0, 1, 3))   # Rohan hit, Dey missed
        self.assertAlmostEqual(overall.accuracy, 5 / 6)
        person = scores.tokens_for("PERSON")
        self.assertEqual((person.tp, person.fp, person.fn, person.tn), (1, 0, 1, 4))
        self.assertAlmostEqual(person.accuracy, 5 / 6)
        self.assertEqual(scores.tokens_for("EMAIL").accuracy, 1.0)


class ReviewBlock(unittest.TestCase):
    """review_block turns the redactor's spans plus the review corrections into the three lists."""

    def pattern(self, text):
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(text) + r"(?![A-Za-z0-9])")

    def test_missed_text_is_found_wherever_it_is_not_covered(self):
        text = "Trilegal advised; see Trilegal House, Mumbai"
        redacted = [Span(22, 43, "ADDRESS", "Trilegal House, Mumbai")]           # covers the second occurrence
        confirmed, wrong, missed = review_block(text, redacted, set(), [("COMPANY", self.pattern("Trilegal"))])
        self.assertEqual(len(confirmed), 1)
        self.assertEqual([(s.start, s.end) for s in missed], [(0, 8)])

    def test_redaction_listed_as_wrong_is_moved_out_of_confirmed(self):
        redacted = [Span(0, 4, "PERSON", "Mark"), Span(10, 14, "PERSON", "Ravi")]
        confirmed, wrong, _ = review_block("Mark said Ravi", redacted, {("PERSON", "mark")}, [])
        self.assertEqual([s.text for s in confirmed], ["Ravi"])
        self.assertEqual([s.text for s in wrong], ["Mark"])


if __name__ == "__main__":
    unittest.main()
