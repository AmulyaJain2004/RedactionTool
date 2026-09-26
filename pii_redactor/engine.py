"""Orchestration: learn from the document, detect PII per paragraph, replace consistently."""
import re
from collections import Counter

from .detectors import Context, default_detectors
from .docx_io import DocxDocument
from .fakes import FakeFactory
from .spans import Span, resolve_overlaps

_URL_OR_EMAIL = re.compile(r"\S+@\S+|(?:https?://|www\.)\S+")


class Redactor:
    """Two passes over the document:

    1. *learn*   - build the vocabulary and let detectors collect names / companies,
    2. *redact*  - find spans in each paragraph, resolve overlaps, write fake values.
    """

    def __init__(self, detectors=None, seed: str = "pii-redactor"):
        self.detectors = detectors if detectors is not None else default_detectors()
        self.context = Context(fakes=FakeFactory(seed))
        self._by_type = {d.type: d for d in self.detectors}
        self.audit = Counter()          # (type, original, fake) -> occurrences

    # -- pass 1 ---------------------------------------------------------------
    def learn(self, texts):
        """Build the everyday-word vocabulary, then let each detector learn from every paragraph."""
        texts = list(texts)
        self.context.vocab = self._build_vocab(texts)
        for detector in self.detectors:
            detector.learn(texts, self.context)

    @staticmethod
    def _build_vocab(texts):
        """Lower-case words used in normal prose. Emails/URLs are removed first, otherwise
        'kushal@...' would make 'Kushal' look like an ordinary word."""
        vocab = set()
        for text in texts:
            vocab.update(re.findall(r"\b[a-z][a-z'’\-]+\b", _URL_OR_EMAIL.sub(" ", text)))
        return vocab

    # -- pass 2 ---------------------------------------------------------------
    def detect(self, text: str):
        """PII spans in one paragraph, overlaps resolved."""
        spans = [span for d in self.detectors for span in d.find(text, self.context)]
        return resolve_overlaps(spans)

    def replacement_for(self, span: Span) -> str:
        """Fake value for a span, produced by the detector that found it."""
        return self._by_type[span.type].replacement(span, self.context)

    def redact_text(self, text: str) -> str:
        """Convenience for tests: redact a plain string (call `learn` first for name/company rules)."""
        out, last = [], 0
        for span in self.detect(text):
            out.append(text[last:span.start])
            out.append(self.replacement_for(span))
            last = span.end
        out.append(text[last:])
        return "".join(out)

    def redact_docx(self, source_path, output_path):
        """Redact a .docx file. Returns the number of replaced spans."""
        document = DocxDocument(source_path)
        self.learn(p.text for p in document.paragraphs())     # learning works paragraph by paragraph

        replaced = 0
        for block in document.blocks():                       # detection works on table-cell blocks
            edits = []
            for span in self.detect(block.text):
                fake = self.replacement_for(span)
                self.audit[(span.type, span.text, fake)] += 1
                edits.append((span.start, span.end, fake))
            block.apply(edits)
            replaced += len(edits)

        document.scrub_metadata()
        document.save(output_path)
        return replaced
