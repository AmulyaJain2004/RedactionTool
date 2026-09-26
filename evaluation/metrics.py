"""Scoring: accuracy, precision, recall and F1, overall and per PII type.

The prospectus was reviewed by reading it next to the redactor's output. For every block the review gives three
lists of spans:

* confirmed - redacted by the tool and really PII                     (true positives)
* wrong     - redacted by the tool but not PII                        (false positives)
* missed    - PII that the tool did not redact                        (false negatives)

Two levels are scored from them:

* Span level  - precision, recall and F1 count spans.
* Token level - every whitespace-separated word is labelled "PII of type T" or not, once by the redactor
  (confirmed + wrong spans) and once by the review (confirmed + missed spans). Accuracy is the share of words
  labelled the same way. Most words are not PII, so accuracy is always high; precision and recall are the
  numbers that show how good the redactor is.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Confusion:
    """True / false positives and negatives, with the usual scores derived from them."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float:
        """Share of redactions that were correct (1.0 when nothing was redacted)."""
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        """Share of PII that was redacted (1.0 when there was no PII)."""
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall."""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def accuracy(self) -> float:
        """(TP + TN) / everything. Only meaningful when `tn` is filled in, i.e. at token level."""
        total = self.tp + self.fp + self.fn + self.tn
        return (self.tp + self.tn) / total if total else 1.0

    def add(self, other: "Confusion"):
        """Add another confusion matrix into this one."""
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        self.tn += other.tn


@dataclass(frozen=True)
class _Word:
    """A word's character range, so it can be compared with spans."""

    start: int
    end: int


def _overlap(a, b) -> bool:
    """True if two ranges (anything with .start / .end) share a character."""
    return a.start < b.end and b.start < a.end


@dataclass
class Scores:
    """Collects span-level and token-level counts over many blocks."""

    spans: dict = field(default_factory=lambda: defaultdict(Confusion))          # type -> span-level counts
    _tokens: dict = field(default_factory=lambda: defaultdict(Confusion))        # type -> token-level tp/fp/fn
    _any_type: Confusion = field(default_factory=Confusion)                      # token-level, types ignored
    token_total: int = 0
    wrong: list = field(default_factory=list)       # (type, text) of every wrongly redacted span
    missed: list = field(default_factory=list)      # (type, text) of every missed span

    def add_block(self, block_text, confirmed, wrong, missed):
        """Score one block. The three arguments are lists of Span (with .type, .text, .start, .end)."""
        for span in confirmed:
            self.spans[span.type].tp += 1
        for span in wrong:
            self.spans[span.type].fp += 1
            self.wrong.append((span.type, span.text))
        for span in missed:
            self.spans[span.type].fn += 1
            self.missed.append((span.type, span.text))
        self._score_tokens(block_text, redacted=confirmed + wrong, reviewed=confirmed + missed)

    def _score_tokens(self, block_text, redacted, reviewed):
        for match in re.finditer(r"\S+", block_text):
            word = _Word(match.start(), match.end())
            redacted_types = {s.type for s in redacted if _overlap(word, s)}
            reviewed_types = {s.type for s in reviewed if _overlap(word, s)}
            self.token_total += 1
            if redacted_types and reviewed_types:
                self._any_type.tp += 1
            elif redacted_types:
                self._any_type.fp += 1
            elif reviewed_types:
                self._any_type.fn += 1
            else:
                self._any_type.tn += 1
            for kind in redacted_types | reviewed_types:
                counts = self._tokens[kind]
                if kind in redacted_types and kind in reviewed_types:
                    counts.tp += 1
                elif kind in redacted_types:
                    counts.fp += 1
                else:
                    counts.fn += 1

    # -- summaries --------------------------------------------------------------------------------------
    def overall_spans(self) -> Confusion:
        """Span-level counts summed over all types (micro average)."""
        total = Confusion()
        for counts in self.spans.values():
            total.add(counts)
        return total

    def overall_tokens(self) -> Confusion:
        """Token-level counts where any PII type counts as PII."""
        return self._any_type

    def tokens_for(self, kind) -> Confusion:
        """Token-level counts for one type; every other word is a true negative for it."""
        counts = self._tokens.get(kind, Confusion())
        return Confusion(counts.tp, counts.fp, counts.fn, self.token_total - counts.tp - counts.fp - counts.fn)
