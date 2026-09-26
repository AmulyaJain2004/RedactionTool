"""Physical / mailing address detection."""
import re

from .. import lexicons as lx
from ..spans import Span
from .base import Detector


def _company_end_regex() -> re.Pattern:
    """Matches the end of a company name (a legal suffix) so an address can start right after it."""
    words = lx.COMPANY_SUFFIXES + lx.COMPANY_WEAK_SUFFIXES
    forms = {form for w in words for form in (w, w.upper())}
    alternatives = "|".join(r"\s+".join(map(re.escape, f.split(" "))) for f in sorted(forms, key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})\W*")


class AddressDetector(Detector):
    """Find addresses in two ways, then walk left over address-looking tokens to find where each starts.

    * postal code:  "Tower 2, Baner, Pune - 411 045, Maharashtra, India"  /  "12 Main Street, Springfield, IL 62704"
    * state + India without a postal code, only when the text also holds a house / unit number:
      "Unit no. 1601, B- wing BKC, Mumbai Maharashtra India"
    """

    type, priority = "ADDRESS", 70

    # 6-digit Indian PIN: first digit 1-9, optional space in the middle, not part of a longer number.
    # 'l', 'I' and 'O' are accepted for 1 / 0 because the source text has OCR noise ("41l 005").
    pin = re.compile(r"(?<![0-9A-Za-z])[1-9][0-9lIO]{2}\s?[0-9lIO]{3}(?![0-9A-Za-z])")
    # Optional ", Maharashtra" and ", India" after the PIN belong to the address.
    tail = re.compile(rf"(?:\s*[,;]?\s*\(?(?:{lx.INDIAN_STATE_PATTERN})\)?)?(?:\s*[,;]?\s*India\b)?")
    # State (+ India) with no PIN.
    state_end = re.compile(rf"(?:{lx.INDIAN_STATE_PATTERN})[ ,]+India\b")
    us_address = re.compile(
        r"\b\d{1,5}\s+(?:[A-Z][A-Za-z.]*\s+){1,3}"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way)\b\.?"
        r"(?:,?\s+(?:Apt|Apartment|Suite|Ste|Unit|#)\s*\w+)?"
        r"(?:,\s*[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)?"
        r"(?:,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?"
    )
    po_box = re.compile(r"\bP\.?\s?O\.?\s+Box\s+\d+(?:,\s*[A-Z][A-Za-z ]+)?(?:,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?")
    # A company name that ends right before the address must stay out of the address span.
    company_end = _company_end_regex()

    MAX_ADDRESS_TOKENS = 40    # stop walking left after this many tokens
    MAX_LINE_TOKENS = 25       # an earlier line longer than this is prose, not an address line
    MAX_LOWERCASE_RUN = 2      # a landmark such as "opposite PYC basketball court" may hold lower-case words

    def find(self, text, ctx):
        """Yield US addresses, PO boxes and addresses anchored on a postal code or state."""
        for pattern in (self.us_address, self.po_box):
            for match in pattern.finditer(text):
                yield Span(match.start(), match.end(), self.type, match.group(0), self.priority)
        yield from self._find_by_postal_code(text)
        yield from self._find_by_state(text)

    # -- anchors -------------------------------------------------------------------
    def _find_by_postal_code(self, text):
        for match in self.pin.finditer(text):
            before_pin = text[:match.start()].rstrip(" ,–—-")
            # A PIN follows a place name ("Pune - 410 501"); "Registration number: 141032",
            # "pin 141032" or "Order 141032" are reference numbers and are skipped.
            if not before_pin or not (before_pin[-1].isalpha() or before_pin[-1] == ")"):
                continue
            previous_word = re.findall(r"[A-Za-z]+|\)", before_pin)[-1]
            if previous_word.lower() in lx.NOT_A_PLACE_BEFORE_PIN or previous_word[0].islower():
                continue
            if sum(ch.isdigit() for ch in match.group(0)) < 4:      # mostly letters: not a PIN
                continue
            start = self._left_edge(before_pin)
            if start is not None:
                end = self.tail.match(text, match.end()).end()
                yield Span(start, end, self.type, text[start:end], self.priority)

    def _find_by_state(self, text):
        for match in self.state_end.finditer(text):
            if self.pin.search(text, max(0, match.start() - 12), match.start()):
                continue                                             # already handled through its PIN
            before = text[:match.start()].rstrip(" ,–—-")
            start = self._left_edge(before)
            if start is None or not any(ch.isdigit() for ch in text[start:match.start()]):
                continue                                             # "located in Maharashtra, India" is not an address
            yield Span(start, match.end(), self.type, text[start:match.end()], self.priority)

    # -- walking left from the anchor ------------------------------------------------
    def _left_edge(self, before_anchor: str):
        """Index where the address starts, or None if too few address-like tokens precede the anchor."""
        # The address cannot begin before a label colon/semicolon or the end of a company name.
        floor = max(before_anchor.rfind(":") + 1, before_anchor.rfind(";") + 1)
        for company in self.company_end.finditer(before_anchor):
            line_start = before_anchor.rfind("\n", 0, company.start()) + 1
            # "MUFG Intime India Private Limited, C-101 ..." -> the company ends before the address starts.
            # "Opposite Harshal Hall, above ALDER Limited ..." -> the company is part of the address.
            if not self._has_address_words(before_anchor[line_start:company.start()]):
                floor = max(floor, company.end())

        lines = self._tokens_by_line(before_anchor, floor)
        accepted = []                                   # (position, token), collected right-to-left
        lowercase_run = 0
        for line_number in range(len(lines) - 1, -1, -1):
            line = lines[line_number]
            if not line:
                continue
            # Only continue onto an earlier line if that line itself looks like address text
            # ("REGISTERED OFFICE" above the address must not be swallowed).
            if accepted and not self._line_is_addressy(line):
                break
            for position, token in reversed(line):
                kind = self._classify(token)
                if kind == "stop" or len(accepted) >= self.MAX_ADDRESS_TOKENS:
                    return self._finish(accepted)
                lowercase_run = lowercase_run + 1 if kind == "lowercase" else 0
                if lowercase_run > self.MAX_LOWERCASE_RUN:
                    return self._finish(accepted)
                accepted.append((position, token))
        return self._finish(accepted)

    @staticmethod
    def _tokens_by_line(text: str, floor: int):
        """[[(position, token), ...], ...] for text[floor:], one list per line."""
        lines, offset = [], 0
        for line in text.split("\n"):
            found = [(offset + m.start(), m.group(0)) for m in re.finditer(r"\S+", line)]
            tokens = [(position, token) for position, token in found if position >= floor]
            lines.append(tokens)
            offset += len(line) + 1
        return lines

    @staticmethod
    def _finish(accepted):
        """Trim leading lower-case prose ("... situated 11/3, ..." -> "11/3, ...") and return the start."""
        tokens = list(reversed(accepted))
        while tokens and tokens[0][1][0].islower():
            tokens.pop(0)
        return tokens[0][0] if len(tokens) >= 2 else None

    @staticmethod
    def _classify(token: str) -> str:
        """'yes' = looks like address text, 'lowercase' = unknown lower-case word, 'stop' = not an address."""
        bare = token.strip(".,()-–—").lower()
        if bare in lx.ADDRESS_LEAD_INS or bare in lx.ADDRESS_STOP_WORDS:
            return "stop"          # "... located at 11/3": the address starts after "at"
        if (any(ch.isdigit() for ch in token) or token[0].isupper() or bare in lx.ADDRESS_WORDS
                or bare in lx.ADDRESS_CONNECTORS or bare in ("", "-") or not token[0].isalnum()):
            return "yes"
        return "lowercase" if token[0].islower() else "stop"

    @staticmethod
    def _has_address_words(text: str) -> bool:
        """True if `text` has a digit, a comma inside it, or a word such as 'Floor' / 'Road' / 'Opposite'.
        A comma on the very last word is ignored: it belongs to a name such as "Kirtane & Pandit, LLP"."""
        tokens = text.split()
        return any(any(ch.isdigit() for ch in t) or t.strip(".,").lower() in lx.ADDRESS_WORDS
                   or (t.endswith(",") and i < len(tokens) - 1) for i, t in enumerate(tokens))

    def _line_is_addressy(self, line) -> bool:
        """An earlier line may join the address only if it is short and contains address words."""
        return len(line) <= self.MAX_LINE_TOKENS and self._has_address_words(" ".join(t for _, t in line))
