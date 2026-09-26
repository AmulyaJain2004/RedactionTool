from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """A character range [start, end) of a paragraph that holds one piece of PII."""
    start: int
    end: int
    type: str
    text: str
    priority: int = 100  # lower number wins when spans overlap

    def overlaps(self, other: "Span") -> bool:
        """True if the two ranges share at least one character."""
        return self.start < other.end and other.start < self.end


def resolve_overlaps(spans):
    """Keep a non-overlapping subset: best priority first, then longest, then leftmost."""
    chosen = []
    for s in sorted(spans, key=lambda s: (s.priority, -(s.end - s.start), s.start)):
        if not any(s.overlaps(c) for c in chosen):
            chosen.append(s)
    return sorted(chosen, key=lambda s: s.start)
