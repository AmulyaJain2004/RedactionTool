"""Score the redactor on the prospectus and write evaluation/results.json.

    python evaluation/run_evaluation.py

The redactor runs on every block of the prospectus. The review corrections (evaluation/data/review_corrections.json)
say which redactions were wrong and which PII was missed; everything else the redactor did counts as correct.
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation import CORRECTIONS_JSON, PROSPECTUS_DOCX, RESULTS_JSON    # noqa: E402
from evaluation.metrics import Scores                                       # noqa: E402
from pii_redactor import Redactor                                            # noqa: E402
from pii_redactor.docx_io import DocxDocument                                # noqa: E402
from pii_redactor.spans import Span                                          # noqa: E402


def load_corrections():
    """(wrong, missed): a set of (type, lower-case text) redactions judged wrong, and (type, regex) for missed PII."""
    with open(CORRECTIONS_JSON, encoding="utf8") as handle:
        data = json.load(handle)
    wrong = {(item["type"], item["text"].lower()) for item in data["wrongly_redacted"]}
    missed = [(item["type"], re.compile(r"(?<![A-Za-z0-9])" + r"\s+".join(map(re.escape, item["text"].split()))
                                        + r"(?![A-Za-z0-9])")) for item in data["missed"]]
    return wrong, missed


def review_block(text, redacted, wrong_set, missed_patterns):
    """Split the redactor's spans for one block into (confirmed, wrong) and find the missed spans.

    A missed span is an occurrence of a corrections text that no redaction already covers."""
    wrong = [s for s in redacted if (s.type, s.text.lower()) in wrong_set]
    confirmed = [s for s in redacted if s not in wrong]
    missed = []
    for kind, pattern in missed_patterns:
        for match in pattern.finditer(text):
            if not any(match.start() < s.end and s.start < match.end() for s in redacted):
                missed.append(Span(match.start(), match.end(), kind, match.group(0)))
    return confirmed, wrong, missed


def _row(confusion):
    """A Confusion as a plain dict for the JSON file."""
    return {"tp": confusion.tp, "fp": confusion.fp, "fn": confusion.fn, "precision": confusion.precision,
            "recall": confusion.recall, "f1": confusion.f1}


def evaluate():
    """Run the redactor over every block of the prospectus and score it with the review corrections."""
    document = DocxDocument(PROSPECTUS_DOCX)
    blocks = [block.text for block in document.blocks()]
    redactor = Redactor()
    redactor.learn(paragraph.text for paragraph in document.paragraphs())
    wrong_set, missed_patterns = load_corrections()

    scores = Scores()
    for text in blocks:
        confirmed, wrong, missed = review_block(text, redactor.detect(text), wrong_set, missed_patterns)
        scores.add_block(text, confirmed, wrong, missed)

    by_type = {}
    for kind in sorted(scores.spans):
        counts = scores.spans[kind]
        by_type[kind] = {**_row(counts), "reviewed": counts.tp + counts.fn,
                         "token_accuracy": scores.tokens_for(kind).accuracy}
    spans, tokens = scores.overall_spans(), scores.overall_tokens()
    return {
        "blocks": len(blocks),
        "characters": sum(len(t) for t in blocks),
        "tokens": scores.token_total,
        "reviewed_spans": spans.tp + spans.fn,
        "overall": {**_row(spans), "token_accuracy": tokens.accuracy, "token_precision": tokens.precision,
                    "token_recall": tokens.recall},
        "by_type": by_type,
        "wrongly_redacted": [{"type": kind, "text": text, "count": n}
                             for (kind, text), n in Counter(scores.wrong).most_common()],
        "missed": [{"type": kind, "text": text, "count": n}
                   for (kind, text), n in Counter(scores.missed).most_common()],
    }


def print_summary(results):
    """Print the overall scores and the per-type table."""
    o = results["overall"]
    print(f"{results['blocks']} blocks, {results['tokens']:,} words, {results['reviewed_spans']} PII spans")
    print(f"Accuracy {o['token_accuracy']:.4f} | Precision {o['precision']:.3f} | "
          f"Recall {o['recall']:.3f} | F1 {o['f1']:.3f}")
    print(f"{'type':10s} {'PII':>5s} {'TP':>5s} {'FP':>4s} {'FN':>4s} "
          f"{'prec':>6s} {'recall':>6s} {'F1':>6s} {'acc':>7s}")
    for kind, x in results["by_type"].items():
        print(f"{kind:10s} {x['reviewed']:5d} {x['tp']:5d} {x['fp']:4d} {x['fn']:4d} {x['precision']:6.3f} "
              f"{x['recall']:6.3f} {x['f1']:6.3f} {x['token_accuracy']:7.4f}")


if __name__ == "__main__":
    output = evaluate()
    with open(RESULTS_JSON, "w", encoding="utf8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=1)
    print_summary(output)
