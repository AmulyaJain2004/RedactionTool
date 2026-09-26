"""Building blocks shared by every detector.

A *detector* looks at one paragraph of text and yields `Span`s (character ranges that are PII).
Detectors may also *learn* from the whole document first (e.g. collect person names) and know
how to build the fake replacement for a span they found.
"""
import re
from dataclasses import dataclass, field

from ..fakes import FakeFactory
from ..spans import Span


NO_MATCH = re.compile(r"(?!x)x")     # a regex that never matches, for "nothing learned yet"


@dataclass
class Context:
    """Document-wide knowledge shared between detectors during one run."""

    fakes: FakeFactory
    # Lower-case words that appear in ordinary prose in this document ("offer", "shares", ...).
    # A Capitalised word that is also in this set is probably not a proper name.
    vocab: set = field(default_factory=set)
    # Learned people: letters-only lower-case key -> original name tokens, e.g.
    # "kushalsubbayyahegde" -> ("Kushal", "Subbayya", "Hegde").
    persons: dict = field(default_factory=dict)
    # Learned company stems (name without legal suffix): "ksh international" -> ("KSH", "International").
    company_stems: dict = field(default_factory=dict)
    # Brand words shared by several group companies (e.g. "ksh", "waterloo").
    brands: set = field(default_factory=set)
    # ALL-CAPS brand words that are also ordinary words when lower-case ("CARE"); matched case-sensitively.
    caps_brands: set = field(default_factory=set)
    # Compiled-regex caches, reset whenever the learned data changes.
    person_regex: object = None
    alias_regex: object = None


class Detector:
    """Base class. Subclasses set `type` / `priority` and implement `find`."""

    type = "?"        # PII type label, also selects the fake generator `FakeFactory._fake_<type>`
    priority = 100    # when two spans overlap the lower number wins

    def learn(self, texts, ctx: Context):
        """Optional first pass over every paragraph, used to build gazetteers."""

    def find(self, text: str, ctx: Context):
        """Yield a `Span` for each PII value found in `text`."""
        raise NotImplementedError

    def replacement(self, span: Span, ctx: Context) -> str:
        """Fake value for `span`. Override when the fake needs document context."""
        return ctx.fakes.fake_for(self.type, span.text)


class RegexDetector(Detector):
    """Detector driven by one compiled `pattern`, with an optional `validate` filter."""

    pattern: "re.Pattern" = None

    def validate(self, match: "re.Match", text: str) -> bool:
        """Reject regex hits that are not really PII (checksums, context checks, ...)."""
        return True

    def make_span(self, match: "re.Match", text: str) -> Span:
        """Turn a regex hit into a Span. Override to trim the matched range."""
        return Span(match.start(), match.end(), self.type, match.group(0), self.priority)

    def find(self, text, ctx):
        """Yield a Span for every regex hit that passes `validate`."""
        for match in self.pattern.finditer(text):
            if self.validate(match, text):
                yield self.make_span(match, text)
