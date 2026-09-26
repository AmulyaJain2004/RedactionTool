"""Person-name detection without a statistical NER model.

Names are *learned* from three kinds of evidence, then *matched* everywhere in the document:
  1. a paragraph that is just a list of names ("Lokesh Shah/ Soumavo Sarkar"),
  2. a context cue before the name ("Contact Person: ...", "being ...", "Promoter, ..."),
  3. a common given name followed by a capitalised word ("Rohit Kushal Hegde").
A candidate token is rejected if it is also an everyday word in this document ("Offer", "Shares")
or a place name.
"""
import re

from .. import lexicons as lx
from ..fakes import match_case
from ..spans import Span
from .base import NO_MATCH, Detector
from .company import STRONG_SUFFIX

# Title-case ("Rahul", "Anne-Marie", "O'Brien") or, after a cue only, ALL CAPS ("RAHUL IYER").
_TITLE_TOKEN = r"(?:[A-Z][a-z]{1,}(?:[\-'’][A-Z]?[a-z]+)*|[A-Z](?:[a-z])*(?:['’\-][A-Z][a-z]+)+)"
_CAPS_TOKEN = r"[A-Z]{2,}(?:['’\-][A-Z]{2,})*"
_NAME_TOKEN = rf"(?:{_TITLE_TOKEN}|{_CAPS_TOKEN})"
_DOTTED_INITIAL = r"[A-Z]\."          # "K."
_TITLE_TOKEN_RE = re.compile(rf"^{_TITLE_TOKEN}$")
_NAME_TOKEN_RE = re.compile(rf"^{_NAME_TOKEN}$")
_DOTTED_INITIAL_RE = re.compile(rf"^{_DOTTED_INITIAL}$")
_INITIALS_RE = re.compile(r"^[A-Z]{1,3}\.?$")            # "S.", "DM": what a middle name or first name shrinks to
_SEPARATOR_RE = re.compile(r"\s*(?:/|,|\band\b)\s*")     # between names in a list
# Capitalised words that look like names but never are.
_NOT_NAMES = frozenset("mr ms mrs dr shri smt sri note table page sr no our the this that".split())


def _key(tokens) -> str:
    """Letters-only lower-case key, so 'Kushal Hegde', 'KUSHAL  HEGDE' and 'KushalHegde' coincide."""
    return re.sub(r"[^a-z]", "", "".join(tokens).lower())


class PersonDetector(Detector):
    """Finds people by learning names from context and matching them everywhere."""
    type, priority = "PERSON", 90

    # 2-4 words: title-case names, and for label cues also ALL-CAPS ones.
    _name = rf"(?:{_TITLE_TOKEN}|{_DOTTED_INITIAL})(?:\s+(?:{_TITLE_TOKEN}|{_DOTTED_INITIAL})){{1,3}}"
    _name_any_case = rf"(?:{_NAME_TOKEN}|{_DOTTED_INITIAL})(?:\s+(?:{_NAME_TOKEN}|{_DOTTED_INITIAL})){{1,3}}"
    # One name or a list of names ("Eric Bacha/ Sachin Gawade/ Pravin Teli").
    _name_list_any_case = rf"{_name_any_case}(?:{_SEPARATOR_RE.pattern}{_name_any_case})*"

    # Words that usually come right before a person in running text ("... by Kushal Subbayya Hegde").
    cue_pattern = re.compile(
        r"(?:\b(?:being|namely|by|to|from|for|of|with|reach|invoiced|contact)\s+"
        r"|(?:Director|Officer|Promoter|Secretary|Chairman|Manager|Partner|Trustee)\s*[,:]?\s+)"
        rf"(?P<name>{_name_list_any_case})"
    )
    # Field labels of a ticket / form ("Customer: MASON ANDERSON"). Here ALL CAPS names are accepted too.
    label_pattern = re.compile(
        r"(?:Contact\s+Person|Name|Customer|Client|User|Agent|Reporter|Requester|Requested\s+by|Assignee|Owner|"
        r"Cardholder|Employee|Patient|Attn|Attention|Dear|From|Sender|Recipient)\s*[:\-]\s*"
        rf"(?P<name>{_name_list_any_case})"
    )
    # A line that starts with a name and a colon ("Rashi Patil: reported a billing issue"). Form labels such as
    # "Registered Office:" are rejected through lexicons.NON_NAME_WORDS.
    line_start_pattern = re.compile(rf"(?m)^(?P<name>{_name})\s*:")
    # "Sangeeta Ramprasad Rai, her spouse, her children ..." (family listings)
    relative_pattern = re.compile(rf"(?P<name>{_name}),\s*(?:her|his)\s+(?:spouse|children|wife|husband)")
    # A name directly followed by "Limited", "LLP", ... is a company, not a person ("Care Analytics Limited").
    company_follows = re.compile(rf"[ \t]+(?:{STRONG_SUFFIX})(?![A-Za-z])")
    company_word = re.compile(rf"\b(?:{STRONG_SUFFIX})(?![A-Za-z])")
    huf_pattern = re.compile(rf"(?P<name>{_name})\s+HUF\b")       # "Karunakar Hegde HUF"
    given_name_pattern = re.compile(
        rf"\b(?P<name>(?:{'|'.join(sorted(n.capitalize() for n in lx.FIRST_NAMES))})(?:\s+{_TITLE_TOKEN}){{1,2}})\b"
    )

    # -- learning -------------------------------------------------------------
    def learn(self, texts, ctx):
        """Collect every name the evidence supports, plus initials-style variants of them."""
        texts = list(texts)
        for text in texts:
            for tokens in self._candidate_names(text, ctx):
                self._register(tokens, ctx)
        self._learn_initials(texts, ctx)
        ctx.person_regex = None          # force the matcher to be rebuilt with the new names

    @staticmethod
    def _learn_initials(texts, ctx):
        """People written as initials + a surname we already know: "DM Shetty", "S. A. Shetty"."""
        surnames = {tokens[-1] for tokens in ctx.persons.values()
                    if len(tokens) >= 2 and not _INITIALS_RE.match(tokens[-1])}
        if not surnames:
            return
        surname_alternatives = "|".join(map(re.escape, sorted(surnames)))
        pattern = re.compile(rf"\b((?:[A-Z]\.?){{1,3}})\s+({surname_alternatives})\b")
        for text in texts:
            for match in pattern.finditer(text):
                if re.search(r"\b[A-Z][a-z]+\s$", text[:match.start()]):
                    continue                                          # "Arjun B. Mehta": B. is a middle initial
                initials = re.sub(r"\s", "", match.group(1))
                ctx.persons[_key((initials, match.group(2)))] = (initials, match.group(2))

    @staticmethod
    def _register(tokens, ctx):
        ctx.persons[_key(tokens)] = tuple(tokens)
        # "Kushal Subbayya Hegde" is also written "Kushal Hegde": register the short form too.
        if len(tokens) >= 3 and not _DOTTED_INITIAL_RE.match(tokens[0]):
            short = (tokens[0], tokens[-1])
            ctx.persons.setdefault(_key(short), short)

    def _candidate_names(self, text, ctx):
        """Yield token lists that look like person names."""
        yield from self._names_from_list_paragraph(text, ctx)
        yield from self._names_from_patterns(text, ctx)

    def _names_from_list_paragraph(self, text, ctx):
        """The whole paragraph is a list of names, optionally followed by footnote marks (* ^ &)."""
        plain = re.sub(r"[\*\^&#\d()\s]+$", "", text.strip())
        if not plain or len(plain) >= 120:
            return
        segments = [segment for segment in _SEPARATOR_RE.split(plain) if segment.strip()]
        token_lists = [re.sub(r"[\*\^&#\d]+$", "", segment).split() for segment in segments]
        if token_lists and all(2 <= len(t) <= 4 and self._is_person(t, ctx) for t in token_lists):
            yield from token_lists

    def _names_from_patterns(self, text, ctx):
        """Cue phrases (also name lists), "<Name> HUF", family listings, given-name + surname."""
        # (pattern, shortest ALL-CAPS word accepted; 0 = title case only). After a field label any ALL-CAPS name
        # is fine; after a preposition ("by SEBI ICDR") words of 4 letters or fewer are treated as acronyms.
        patterns = ((self.cue_pattern, 5), (self.label_pattern, 2), (self.line_start_pattern, 0), (self.huf_pattern, 0),
                    (self.relative_pattern, 0), (self.given_name_pattern, 0))
        for pattern, caps_min in patterns:
            for match in pattern.finditer(text):
                if self.company_word.search(match.group("name")) or self.company_follows.match(text, match.end("name")):
                    continue                                         # part of a company name
                for part in _SEPARATOR_RE.split(match.group("name")):
                    tokens = part.split()
                    while len(tokens) >= 2 and not self._is_person(tokens, ctx, caps_min):
                        tokens = tokens[:-1]                         # trim trailing non-name words
                    if len(tokens) >= 2:
                        yield tokens

    @staticmethod
    def _is_person(tokens, ctx, caps_min=0) -> bool:
        """Do these tokens look like a person's name?

        Title-case words qualify. ALL-CAPS words qualify only if `caps_min` > 0 and every word of the name is
        ALL CAPS with at least `caps_min` letters ("KABIR HADDAD", but not "Shanti Gopalkrishnan SEBI")."""
        words = [t for t in tokens if not _DOTTED_INITIAL_RE.match(t)]
        if not words:
            return False
        all_title = all(_TITLE_TOKEN_RE.match(t) for t in words)
        all_caps = caps_min > 0 and all(_NAME_TOKEN_RE.match(t) and t.isupper() and len(t) >= caps_min for t in words)
        return (len(tokens) >= 2 and len(words) >= 2
                and (all_title or all_caps)
                and all(_DOTTED_INITIAL_RE.match(t) or _NAME_TOKEN_RE.match(t) for t in tokens)
                and all(w.lower() not in ctx.vocab and w.lower() not in lx.STATES_AND_PLACES
                        and w.lower() not in _NOT_NAMES and w.lower() not in lx.NON_NAME_WORDS for w in words))

    # -- matching -------------------------------------------------------------
    @staticmethod
    def _matcher(ctx):
        """One regex over every learned name, longest first, tolerant of case and missing spaces."""
        if ctx.person_regex is None:
            if not ctx.persons:
                ctx.person_regex = NO_MATCH
            else:
                names = sorted(ctx.persons.values(), key=lambda t: (-len(t), -sum(map(len, t))))
                body = "|".join(r"\s*".join(re.escape(tok) for tok in tokens) for tokens in names)
                # "Rajesh Branch" (a family branch named after a known person): the given name alone.
                given = sorted({tokens[0] for tokens in names if not _INITIALS_RE.match(tokens[0])})
                branch = "|".join(re.escape(g) for g in given)
                body += rf"|(?:{branch})(?=\s+Branch\b)" if given else ""
                ctx.person_regex = re.compile(rf"(?<![A-Za-z])(?:{body})(?![A-Za-z])", re.IGNORECASE)
        return ctx.person_regex

    def find(self, text, ctx):
        """Yield a span for every occurrence of a learned name."""
        for match in self._matcher(ctx).finditer(text):
            yield Span(match.start(), match.end(), self.type, match.group(0), self.priority)

    def replacement(self, span, ctx):
        """Fake each name token separately so every mention of a person (and every shared
        surname) maps to the same fake token, whichever form of the name is used."""
        tokens = ctx.persons.get(_key([span.text]))
        if tokens is None:                                            # defensive: unknown form
            return ctx.fakes.name_token(span.text, "first")
        fake_tokens = []
        for index, token in enumerate(tokens):
            if _INITIALS_RE.match(token):                                # keep initials as initials
                fake_tokens.append(ctx.fakes.name_token(token, "first")[:len(token.rstrip(".")) or 1].upper()
                                   + ("." if token.endswith(".") else ""))
            else:
                role = "last" if index == len(tokens) - 1 else "first"
                fake_tokens.append(ctx.fakes.name_token(token, role))
        return match_case(span.text, " ".join(fake_tokens))
