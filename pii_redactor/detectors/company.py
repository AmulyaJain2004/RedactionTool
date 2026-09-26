"""Company-name detection: legal-suffix rule plus learned short forms."""
import re

from .. import lexicons as lx
from ..fakes import match_case
from ..spans import Span
from .base import NO_MATCH, Detector

# Words allowed between capitalised words inside a name ("Kirtane & Pandit LLP").
_JOINERS = ("of", "and", "for", "&")
_COMPANY_TOKEN = r"(?:[A-Z][A-Za-z0-9&'’.\-]*|\d+|\([A-Z][A-Za-z]+\))"


def _suffix_regex(suffixes) -> str:
    """Regex alternatives for a list of suffix words, in Title Case and UPPER CASE only,
    so a lower-case 'limited' in ordinary prose never matches. Longest suffix first."""
    forms = []
    for suffix in sorted(suffixes, key=len, reverse=True):
        for variant in dict.fromkeys((suffix, suffix.upper())):
            pattern = r"\s+".join(re.escape(word) for word in variant.split(" "))
            if suffix == "Co.":                       # "Co. LLP" is one suffix, handled by "LLP"
                pattern += r"(?!\s+(?:LLP|LTD|Ltd|Limited|LIMITED))"
            forms.append(pattern)
    return "|".join(forms)


STRONG_SUFFIX = _suffix_regex(lx.COMPANY_SUFFIXES)        # also used by the person detector
_WEAK = _suffix_regex(lx.COMPANY_WEAK_SUFFIXES)
# "Hindalco Industries Limited" = weak + strong; "Kushal Electricals" = weak alone; the weak-alone
# form must not be followed by "and <Name>" (then a longer name is continuing).
_SUFFIX = rf"(?:(?:{_WEAK})\s+)?(?:{STRONG_SUFFIX})|(?:{_WEAK})(?!\s+(?:and|of|for|&)\s+[A-Z])"
_STRONG_RE = re.compile(rf"(?:{STRONG_SUFFIX})$")
# Regulators / exchanges / government bodies are not redacted; whole words only ("nse" != "licensed").
_PUBLIC_BODY_RE = re.compile(r"\b(?:%s)\b" % "|".join(map(re.escape, lx.ORG_ALLOWLIST_KEYWORDS)), re.IGNORECASE)


def split_glued(word: str):
    """Split words the source glued together: 'NuvamaWealth' -> ['Nuvama', 'Wealth']."""
    return re.findall(r"[A-Z][a-z]+|[A-Z]+(?![a-z])|[a-z]+|\d+", word) or [word]


class CompanyDetector(Detector):
    """Finds "<name> Limited / Private Limited / LLP / Trust ...", then also the short forms
    of those names (without the suffix, and a brand word such as "KSH") so they get the same fake."""

    type, priority = "COMPANY", 80
    # Up to 8 capitalised words (lazy), an optional comma ("Kirtane & Pandit, LLP"), then a legal suffix.
    pattern = re.compile(
        rf"(?P<name>{_COMPANY_TOKEN}(?:\s+(?:(?:of|and|for|&)\s+)?{_COMPANY_TOKEN}){{0,7}}?(?:\s+&)?),?\s+"
        rf"(?P<suffix>{_SUFFIX})(?![A-Za-z])"
    )

    # -- parsing a suffix match -------------------------------------------------
    def _parse(self, match, ctx):
        """Decide whether a regex match is a company to redact.
        Returns (start_index, name_words), or None for public bodies, glossary phrases and other look-alikes."""
        name, suffix = match.group("name"), match.group("suffix")
        if self._is_public_body(name + suffix):                            # checked before trimming
            return None
        words = [(m.start(), m.group(0)) for m in re.finditer(r"\S+", name)]
        words = self._drop_unrelated_lines(name, words)
        words = self._strip_leading_non_name(words, ctx)
        stem = [w for _, w in words]
        if not stem or not self._looks_like_company(stem, suffix, ctx):
            return None
        return match.start("name") + words[0][0], stem

    @staticmethod
    def _drop_unrelated_lines(name, words):
        """A name may be wrapped over several paragraphs ("KSH" / "Distriparks" / "Private Limited"), but a
        multi-word line before the last one is unrelated text: drop it and everything before it."""
        line_of = [name.count("\n", 0, position) for position, _ in words]
        words_on_line = {line: line_of.count(line) for line in set(line_of)}
        last_line = line_of[-1]
        cut = max((i + 1 for i, line in enumerate(line_of) if line < last_line and words_on_line[line] > 1), default=0)
        return words[cut:]

    @staticmethod
    def _strip_leading_non_name(words, ctx):
        """Drop leading words such as "Our", "Company", "Bid", a CIN, or ordinary vocabulary ("Offer Escrow ...")."""
        lead = 0
        while lead < len(words):
            word = words[lead][1].strip(".,&").lower()
            remaining_real = [w for _, w in words[lead + 1:] if w.lower() not in _JOINERS]
            is_identifier = re.fullmatch(r"(?=.*\d)[A-Z0-9]{8,}", words[lead][1]) is not None
            if is_identifier or word in lx.COMPANY_LEAD_STOP or (word in ctx.vocab and len(remaining_real) >= 3):
                lead += 1
            else:
                break
        return words[lead:]

    def _looks_like_company(self, stem, suffix, ctx) -> bool:
        real = [w for w in stem if w.lower() not in _JOINERS]
        if not real or stem[0].lower() in _JOINERS:
            return False
        # Needs at least one word that is not ordinary vocabulary, or two+ capitalised words.
        distinctive = any(w.strip(".,").lower() not in ctx.vocab and w.lower() not in lx.COMPANY_LEAD_STOP
                          for w in real)
        if not distinctive and len(real) < 2:
            return False
        if all(w.strip(".,()").lower() in lx.STATES_AND_PLACES for w in real):
            return False               # "India Limited" is the tail of "... Corporation of India Limited"
        if not _STRONG_RE.search(suffix) and not distinctive:
            return False                                     # a weak suffix ("Motors") needs a distinctive name
        return not self._is_public_body(" ".join(stem + [suffix]))

    @staticmethod
    def _is_public_body(name: str) -> bool:
        """Regulators, exchanges, depositories, ... are public bodies and are not redacted."""
        return bool(_PUBLIC_BODY_RE.search(re.sub(r"\s+", " ", name)))

    @staticmethod
    def _stem_tokens(words):
        """Words of a company stem as clean tokens (joiners dropped, glued words split)."""
        tokens = []
        for word in words:
            if word.lower() not in _JOINERS:
                tokens += split_glued(word.strip(".,"))
        return tokens

    # -- learning ----------------------------------------------------------------
    def learn(self, texts, ctx):
        """Learn company short forms and group brands from the whole document."""
        person_tokens = {t.lower() for tokens in ctx.persons.values() for t in tokens}
        stems_by_brand = {}                     # first word (lower) -> distinct stems that start with it
        shouted = set()                         # first words written ALL CAPS in some company name
        for text in texts:
            for match in self.pattern.finditer(text):
                if not _STRONG_RE.search(match.group("suffix")):
                    continue                    # "Kushal Electricals" must not turn "Kushal" into a company alias
                parsed = self._parse(match, ctx)
                tokens = self._stem_tokens(parsed[1]) if parsed else []
                if not tokens or tokens[0].lower() in person_tokens:
                    continue
                stem_key = " ".join(t.lower() for t in tokens)
                if len(tokens) >= 2 or self._is_distinctive_word(tokens[0], ctx, min_length=4):
                    ctx.company_stems[stem_key] = tuple(tokens)
                stems_by_brand.setdefault(tokens[0].lower(), set()).add(stem_key)
                if len(tokens[0]) >= 3 and tokens[0].isupper():
                    shouted.add(tokens[0].lower())
        self._learn_brands(stems_by_brand, shouted, ctx)
        ctx.alias_regex = None

    @staticmethod
    def _is_distinctive_word(word, ctx, min_length) -> bool:
        lower = word.lower()
        return len(word) >= min_length and lower not in ctx.vocab and lower not in lx.STATES_AND_PLACES

    @staticmethod
    def _learn_brands(stems_by_brand, shouted, ctx):
        """A first word shared by several companies is a group brand ("KSH ...", "Waterloo ...").
        A distinctive first word of a single company ("Nuvama", "Hindalco") is used as its short name too."""
        for brand, stems in stems_by_brand.items():
            if brand in lx.COMPANY_LEAD_STOP or brand in lx.STATES_AND_PLACES or brand in lx.GENERIC_CAPITALISED:
                continue
            if len(brand) < 3 or (len(stems) < 2 and len(brand) < 5):
                continue
            if brand not in ctx.vocab:
                ctx.brands.add(brand)
            elif brand in shouted:
                ctx.caps_brands.add(brand.upper())      # "CARE" yes, the verb "care" no

    # -- matching ------------------------------------------------------------------
    @staticmethod
    def _alias_matcher(ctx):
        """Regex for short forms: learned stems and brand words, longest first."""
        if ctx.alias_regex is None:
            aliases = {tuple(t.lower() for t in stem) for stem in ctx.company_stems.values()}
            aliases |= {(brand,) for brand in ctx.brands}
            parts = []
            if aliases:
                ordered = sorted(aliases, key=lambda a: (-len(a), -sum(map(len, a))))
                parts.append("(?i:%s)" % "|".join(r"\s*".join(re.escape(t) for t in alias) for alias in ordered))
            if ctx.caps_brands:                                   # case-sensitive: only the ALL-CAPS form
                parts.append("|".join(map(re.escape, sorted(ctx.caps_brands))))
            if not parts:
                ctx.alias_regex = NO_MATCH
            else:
                ctx.alias_regex = re.compile(r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(parts))
        return ctx.alias_regex

    def find(self, text, ctx):
        """Yield full names with a legal suffix, then their short forms."""
        for match in self.pattern.finditer(text):                       # full names with a legal suffix
            parsed = self._parse(match, ctx)
            if parsed:
                start = parsed[0]
                yield Span(start, match.end(), self.type, text[start:match.end()], self.priority)
        for match in self._alias_matcher(ctx).finditer(text):           # short forms (slightly lower priority)
            yield Span(match.start(), match.end(), self.type, match.group(0), self.priority + 1)

    # -- fake value ------------------------------------------------------------------
    def replacement(self, span, ctx):
        """Fake = <fake brand> [<fake noun>] [+ original suffix]. The brand depends only on the first
        word, so "KSH", "KSH International" and "KSH Infra Park" share one fake brand."""
        full = self.pattern.fullmatch(span.text)
        suffix, stem_text = (full.group("suffix"), full.group("name")) if full else ("", span.text)
        tokens = self._stem_tokens(stem_text.split())
        if not tokens:
            return "Example Holdings"
        fake_stem = ctx.fakes.brand_token(tokens[0])
        if len(tokens) > 1:
            fake_stem += " " + ctx.fakes.noun_token(" ".join(tokens[1:]))
        fake_stem = match_case(stem_text, fake_stem)
        return f"{fake_stem} {suffix}".strip()
