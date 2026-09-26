"""Detectors for identifiers that have a fixed shape: email, URL, SSN, card, IP, phone, date of birth."""
import ipaddress
import re

from .. import lexicons as lx
from ..fakes import luhn_check_digit
from ..spans import Span
from .base import Detector, RegexDetector

# A word such as "Order" / "Ticket" / "Invoice" right before a number says the number is a reference id,
# not PII. The assignment asks explicitly that such numbers stay untouched.
_REFERENCE_WORD = re.compile(
    r"(?i)\b(?:order|ticket|tracking|awb|invoice|ref(?:erence)?|case|txn|transaction|sku|serial|batch|"
    r"shipment|booking|receipt|id)\b\W{0,4}(?:no\.?|number|#|id)?\W{0,4}$")
_PHONE_CUE = re.compile(
    r"(?i)\b(?:tel(?:ephone)?|phone|mobile|mob|cell|call|contact|whatsapp|reach|dial|ph|fax)\b\W{0,12}$")
_VERSION_CUE = re.compile(r"(?i)(?:\bv|version|ver|release|build|firmware)\.?\s*$")


def follows_reference_word(text: str, start: int, window: int = 25) -> bool:
    """True if the text just before `start` ends with an order / ticket / invoice style label."""
    return bool(_REFERENCE_WORD.search(text[max(0, start - window):start]))


class EmailDetector(RegexDetector):
    """Email addresses (our own @example.com fakes are left alone)."""
    type, priority = "EMAIL", 10
    pattern = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")

    def validate(self, match, text):
        """Keep the hit unless it is a look-alike (a fake, a version string, an order number, ...)."""
        return not match.group(0).lower().endswith("@example.com")     # our own fake addresses: leave alone


class UrlDetector(RegexDetector):
    """Not on the assignment's list, but a company web address identifies the company we just renamed.
    Regulator / exchange / government sites are kept (see lexicons.URL_ALLOWLIST_SUFFIXES)."""

    type, priority = "URL", 20
    # The optional tail copes with addresses broken by a stray space, e.g. "www.kshinternational. com".
    pattern = re.compile(r"(?i)(?:https?://|www\.)[\w\-./~%?=&#:+]*[\w/](?:\.\s(?:com|in|org|net|co\.in)\b)?")

    def validate(self, match, text):
        """Skip URLs of regulators, exchanges and government bodies."""
        host = re.sub(r"(?i)^(https?://)?(www\.)?", "", match.group(0).replace(" ", "")).split("/")[0].lower()
        return not host.endswith(lx.URL_ALLOWLIST_SUFFIXES)


class SsnDetector(RegexDetector):
    """US Social Security Numbers: NNN-NN-NNNN, or 9 digits when 'SSN' / 'Social Security Number' precedes."""

    type, priority = "SSN", 30
    # Area 000, 666 and 9xx are never issued; group 00 and serial 0000 do not exist.
    _AREA, _GROUP, _SERIAL = r"(?!000|666|9\d\d)\d{3}", r"(?!00)\d{2}", r"(?!0000)\d{4}"
    pattern = re.compile(
        rf"(?<![\d-]){_AREA}-{_GROUP}-{_SERIAL}(?![\d-])"                                 # dashed form, no cue needed
        r"|(?i:(?<=ssn)|(?<=ssn:)|(?<=ssn #)|(?<=social security number)|(?<=social security number:))"
        rf"\s*{_AREA}[- ]?{_GROUP}[- ]?{_SERIAL}(?!\d)"                                   # cue + 9 digits
    )

    def make_span(self, match, text):
        """Trim the leading whitespace that the cue form of the pattern captures."""
        raw = match.group(0)
        lead = len(raw) - len(raw.lstrip())          # the cue form starts with whitespace
        return Span(match.start() + lead, match.end(), self.type, raw.strip(), self.priority)


class CreditCardDetector(RegexDetector):
    """13-19 digit numbers with one kind of separator that pass the Luhn checksum and start like a real card."""

    type, priority = "CREDIT_CARD", 35
    pattern = re.compile(r"(?<![\d.,\-])\d(?:[ \-]?\d){12,18}(?![\d\-]|[.,]\d)")

    def validate(self, match, text):
        """Accept only numbers that pass the Luhn checksum and are not labelled as an order / ticket id."""
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        separators = set(re.findall(r"[ \-]", raw))
        if not 13 <= len(digits) <= 19 or len(separators) > 1 or digits[0] not in "3456":
            return False
        if follows_reference_word(text, match.start()):
            return False                                        # "Order 4111111111111111"
        return luhn_check_digit(digits[:-1]) == digits[-1]   # Luhn keeps order numbers out


class IpDetector(RegexDetector):
    """IPv4 (each octet 0-255, no leading zeros) and IPv6 (verified with the ipaddress module)."""

    type, priority = "IP_ADDRESS", 40
    _octet = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    pattern = re.compile(
        rf"(?<![\d.])(?:{_octet}\.){{3}}{_octet}(?!\d|\.\d)"                # 192.168.0.1 (not 1.2.3.4.5)
        r"|(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])"  # IPv6 candidates
    )

    # Documentation ranges (RFC 5737 / RFC 3849) are what the fake generator emits; do not redact them again.
    _fake_prefixes = ("192.0.2.", "198.51.100.", "203.0.113.", "2001:db8:ffff:")

    def validate(self, match, text):
        """Reject our own fake ranges and version strings; check IPv6 candidates with the ipaddress module."""
        raw = match.group(0)
        if raw.lower().startswith(self._fake_prefixes):
            return False
        if ":" not in raw:
            return not _VERSION_CUE.search(text[max(0, match.start() - 12):match.start()])    # "version 2.3.4.5"
        try:
            ipaddress.IPv6Address(raw)      # rejects clock times such as 10:30:45
            return True
        except ValueError:
            return False


class PhoneDetector(RegexDetector):
    """International (+CC ...), STD (022-1234567), Indian mobile and US formats.
    A bare run of digits is a phone number only after a phone cue ("Mobile", "Call", ...) or when it is grouped
    ("98765 43210"), and never after an order / ticket label, so reference numbers stay untouched."""

    type, priority = "PHONE", 50
    pattern = re.compile(
        r"(?<![\w+])\(?\+\s?\d{1,3}\)?(?:[\s.\-]?\(?\d{1,5}\)?){2,5}(?!\d)"                    # +91 22 4009 4400
        r"|(?<=:)\s*0\d{2,4}[\s\-]\d{6,8}(?!\d)"                                               # Telephone:022-68052182
        r"|(?<![\w.,\-])0\d{2,4}[\s\-]\d{6,8}(?!\w)(?![.,]\d)"                              # 022-68052182
        r"|(?<![\w.,\-])0\d{2,4}[\s\-]\d{3,4}[\s\-]\d{4}(?!\w)(?![.,]\d)"                # 022-2367 1980
        r"|(?<![\w.,\-])(?P<bare>(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5})(?!\w)(?![.,]\d)"  # 98765 43210
        r"|(?<![\w.,\-])(?:\+?1[\s.\-]?)?\(?[2-9]\d{2}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\w)(?![.,]\d)"  # (555) 123-4567
    )

    def validate(self, match, text):
        """Reject numbers of the wrong length, labelled reference numbers, and unexplained bare mobile numbers."""
        if not 8 <= len(re.sub(r"\D", "", match.group(0))) <= 15:
            return False
        if follows_reference_word(text, match.start()):
            return False                                        # "Order 98765 43210"
        if match.group("bare") is not None:                     # a plain mobile-number shape needs a reason
            grouped = re.search(r"[\s\-]", match.group("bare").lstrip("+"))
            return bool(grouped or _PHONE_CUE.search(text[max(0, match.start() - 30):match.start()]))
        return True

    def make_span(self, match, text):
        """Trim surrounding whitespace and trailing punctuation from the number."""
        raw = match.group(0)
        start = match.start() + (len(raw) - len(raw.lstrip()))
        return Span(start, match.end(), self.type, raw.strip().rstrip(" .,-"), self.priority)


class DobDetector(Detector):
    """A date counts as a date of birth only when a birth cue ("DOB", "born on", ...) is next to it.
    Other dates (deal dates, filing dates) are left alone."""

    type, priority = "DOB", 60
    _month = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
    date = re.compile(
        r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"                               # 25/12/1990
        r"|\b\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}\b"                                # 1990-12-25
        rf"|\b\d{{1,2}}(?:st|nd|rd|th)?[\s,\-]+{_month}[\s,\-]+\d{{4}}\b"      # 25th December 1990
        rf"|\b{_month}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b"              # December 25, 1990
    )
    # The cue may stand a few words before the date ("date of birth of Rahul Iyer to 12/03/1985"),
    # but not across a sentence end; "[A-Z]\." lets an initial such as "E." pass.
    cue_before = re.compile(
        r"(?i)(?:date\s+of\s+birth|birth\s*date|birthday|\bd\.?\s?o\.?\s?b\.?|\bborn(?:\s+on)?)"
        r"(?:[A-Z]\.|[^.;\n]){0,45}$")
    cue_after = re.compile(r"(?i)^\W{0,3}(?:\(?\s*(?:d\.?o\.?b\.?|date\s+of\s+birth|birth\s*date)\s*\)?)")

    def find(self, text, ctx):
        """Yield dates that sit next to a birth cue."""
        for match in self.date.finditer(text):
            before = text[max(0, match.start() - 60):match.start()]
            after = text[match.end():match.end() + 25]
            if self.cue_before.search(before) or self.cue_after.match(after):
                yield Span(match.start(), match.end(), self.type, match.group(0), self.priority)
