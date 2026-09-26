"""Deterministic, format-preserving fake value generation.

Same original -> same fake (within a run and across runs, given the same seed).
Different originals never share a fake (collisions are resolved by re-hashing).
"""
import hashlib
import re

from . import lexicons as lx


def _h(*parts) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode("utf8")).digest()[:8], "big")


def match_case(original: str, fake: str) -> str:
    """Upper-case `fake` when `original` is written in ALL CAPS."""
    letters = [c for c in original if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return fake.upper()
    return fake


def luhn_check_digit(body: str) -> str:
    """The digit that makes `body` + digit pass the Luhn checksum (used to validate and to fake card numbers)."""
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch) * (2 if i % 2 == 0 else 1)
        total += d - 9 if d > 9 else d
    return str((10 - total % 10) % 10)


def _pour(original: str, digits: str) -> str:
    """Write `digits` into the digit positions of `original`, keeping every separator."""
    out, i = [], 0
    for ch in original:
        if ch.isdigit():
            out.append(digits[i])
            i += 1
        else:
            out.append(ch)
    return "".join(out)


class FakeFactory:
    """Makes fake values for every PII type; `fake_for(type, original)` is the entry point."""
    def __init__(self, seed: str = "pii-redactor"):
        self.seed = seed
        self._memo = {}    # (type, key) -> fake
        self._taken = {}   # (type, fake) -> key ; guarantees two originals never share a fake

    # -- core ---------------------------------------------------------------
    def _unique(self, type_, key, make):
        """make(n) returns the n-th candidate fake for `key`."""
        if (type_, key) in self._memo:
            return self._memo[(type_, key)]
        n = 0
        while True:
            fake = make(n)
            owner = self._taken.get((type_, fake.lower()))
            if owner is None or owner == key:
                break
            n += 1
        self._taken[(type_, fake.lower())] = key
        self._memo[(type_, key)] = fake
        return fake

    def fake_for(self, type_: str, original: str) -> str:
        """Fake value for `original`; the generator is the `_fake_<type>` method matching `type_`."""
        fn = getattr(self, f"_fake_{type_.lower()}", None)
        if fn is None:
            return f"[{type_}]"
        return fn(original)

    # -- tokens shared by person / company detectors --------------------------
    def _pooled(self, kind: str, key: str, pool):
        """Unique pool word for `key`: hash to a start position, then probe forward past words that
        are already taken. Digits are appended only if the whole pool is used up."""
        def make(n):
            start = _h(self.seed, kind, key) % len(pool)
            word = pool[(start + n) % len(pool)]
            return word if n < len(pool) else f"{word}{n // len(pool)}"
        return self._unique(kind, key, make)

    def name_token(self, token: str, role: str) -> str:
        """Fake for one word of a person's name. `role` is 'first' (given / middle) or 'last'."""
        return self._pooled(f"NAMETOK_{role}", token.lower(), lx.FAKE_LAST if role == "last" else lx.FAKE_FIRST)

    def brand_token(self, token: str) -> str:
        """Fake for the distinctive first word of a company name."""
        return self._pooled("BRAND", token.lower(), lx.FAKE_BRAND)

    def noun_token(self, text: str) -> str:
        """Fake for the rest of a company name after its brand word (Holdings, Labs, ...)."""
        return lx.FAKE_NOUN[_h(self.seed, "nn", text.lower()) % len(lx.FAKE_NOUN)]

    # -- per type ------------------------------------------------------------
    def _fake_email(self, original: str) -> str:
        key = original.lower()

        def make(n):
            first = lx.FAKE_FIRST[_h(self.seed, "ef", key, n) % len(lx.FAKE_FIRST)].lower()
            last = lx.FAKE_LAST[_h(self.seed, "el", key, n) % len(lx.FAKE_LAST)].lower()
            return f"{first}.{last}{'' if n < 50 else n}@example.com"
        return self._unique("EMAIL", key, make)

    def _fake_url(self, original: str) -> str:
        m = re.match(r"(?i)(https?://)?(www\.)?([^/\s]+)", original)
        scheme, www, host = (m.group(1) or ""), (m.group(2) or ""), m.group(3)
        key = host.lower().replace(" ", "")
        brand = self.brand_token(key.split(".")[0] or key).lower()
        return f"{scheme}{www}{brand}.example.com"

    def _fake_phone(self, original: str) -> str:
        digits = "".join(c for c in original if c.isdigit())
        keep = 0
        if original.lstrip().startswith("+"):
            keep = next((len(cc) for cc in ("91", "44", "61", "65", "81", "971", "1", "7") if digits.startswith(cc)),
                        min(2, len(digits)))
        elif digits.startswith("0"):
            keep = 1

        def make(n):
            return digits[:keep] + "".join(
                str((int(d) + 1 + _h(self.seed, "ph", digits, n, i) % 9) % 10)   # shift 1..9: never the same digit
                for i, d in enumerate(digits) if i >= keep)
        # The memo holds digits only, so the same number written differently keeps each occurrence's layout.
        return _pour(original, self._unique("PHONE", digits, make))

    def _fake_ssn(self, original: str) -> str:
        key = re.sub(r"\D", "", original)

        def make(n):
            h = _h(self.seed, "ssn", key, n)
            return f"{900 + h % 99:03d}{1 + (h >> 8) % 99:02d}{1 + (h >> 16) % 9999:04d}"      # 9xx is never issued
        return _pour(original, self._unique("SSN", key, make))

    def _fake_credit_card(self, original: str) -> str:
        key = re.sub(r"\D", "", original)

        def make(n):
            body = key[0] + "".join(str(_h(self.seed, "cc", key, n, i) % 10) for i in range(len(key) - 2))
            digits = body + luhn_check_digit(body)
            return digits if digits != key else make(n + 1000)
        return _pour(original, self._unique("CREDIT_CARD", key, make))

    def _fake_ip_address(self, original: str) -> str:
        key = original.lower()
        if ":" in original:
            return self._unique("IP", key, lambda n: f"2001:db8:ffff::{_h(self.seed, 'ip6', key, n) % 0xFFFE + 1:x}")
        nets = ("192.0.2", "198.51.100", "203.0.113")   # RFC 5737 documentation ranges

        def make(n):
            h = _h(self.seed, "ip4", key, n)
            return f"{nets[h % 3]}.{(h >> 8) % 254 + 1}"
        return self._unique("IP", key, make)

    def _fake_dob(self, original: str) -> str:
        """Shift the year by 1-3 and pick a new day / month, keeping the original layout
        ("25/12/1990", "1990-12-25", "25th December 1990", "Dec 25, 90" ...)."""
        h = _h(self.seed, "dob", original.lower())
        year_delta = [-3, -2, -1, 1, 2, 3][h % 6]
        day = 1 + (h >> 4) % 28
        # For numeric dates both fields are 1-12 so DD/MM and MM/DD layouts stay valid.
        small_a, small_b = 1 + (h >> 9) % 12, 1 + (h >> 14) % 12

        def new_year(old: str) -> str:
            value = int(old) + year_delta
            return f"{value % 100:02d}" if len(old) == 2 else str(value)

        numbers = list(re.finditer(r"\d+", original))
        month_word = re.search(r"[A-Za-z]{3,}", original)
        if month_word:
            # Textual month: 4-digit number is the year, the other number is the day.
            values = [new_year(n.group(0)) if len(n.group(0)) == 4 else str(day) for n in numbers]
        elif len(numbers[0].group(0)) == 4:                                  # year first: Y-M-D
            values = [new_year(numbers[0].group(0)), str(small_a), str(small_b)]
        else:                                                                # D/M/Y (year is last)
            values = [str(small_a), str(small_b), new_year(numbers[-1].group(0))]

        out, last = [], 0
        for number, value in zip(numbers, values):
            out.append(original[last:number.start()])
            out.append(value.zfill(len(number.group(0))) if len(number.group(0)) <= 2 else value)
            last = number.end()
        out.append(original[last:])
        result = "".join(out)

        if month_word:
            name = month_word.group(0)
            index = next((i for i, m in enumerate(lx.FAKE_MONTHS) if m.lower().startswith(name[:3].lower())), 0)
            new_name = lx.FAKE_MONTHS[(index + 1 + (h >> 20) % 10) % 12]      # always a different month
            result = result.replace(name, new_name if len(name) > 3 else new_name[:3], 1)
        return result

    def _fake_address(self, original: str) -> str:
        key = re.sub(r"\s+", " ", original.lower())
        zip6 = bool(re.search(r"\b\d{3}\s?\d{3}\b", original))
        ends_india = bool(re.search(r"India\W*$", original))

        def make(n):
            h = _h(self.seed, "addr", key, n)
            street = lx.FAKE_STREET[(h >> 10) % len(lx.FAKE_STREET)]
            city = lx.FAKE_CITY[(h >> 20) % len(lx.FAKE_CITY)]
            zipc = str(100000 + (h >> 30) % 899999) if zip6 else str(10000 + (h >> 30) % 89999)
            return f"{1 + h % 998} {street} Street, {city} {zipc}{', India' if ends_india else ''}"
        return self._unique("ADDRESS", key, make)
