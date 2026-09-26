# PII redaction for Word documents

`redact.py` reads a `.docx`, finds personal information and writes a new `.docx` in which every value is replaced by a
realistic fake one. Formatting, tables, headers, footers and images are kept.

```
python redact.py "Red Herring Prospectus.docx" -o "Redacted Prospectus.docx"
```

Tested on Python 3.12 with two packages (`pip install -r requirements.txt`). No model download, no network access.

## Approach

**Rule-based only: regular expressions plus context rules.** No NER model, Presidio or LLM, so every decision can be
traced to a rule. The tool makes two passes over the document. First it *learns* from the whole text: which lower-case
words are ordinary prose (so "Offer" is not taken for a name), which names appear (from cues such as `Contact Person:`,
`being`, `Promoter,` and from name lists), and which company names and short forms appear (`KSH International Limited`
also teaches `KSH`). Then every detector proposes spans, overlaps are settled by priority, and each span gets a fake value.

Fakes are deterministic and consistent: the same real value always gets the same fake, different real values never share
one, and the format is kept (`+91 98765 43210` stays a 10-digit number after `+91`, card numbers stay Luhn-valid, a shared
surname maps to the same fake surname). Word splits text into runs (`rohan.` `dey@gmail` `.com`); the code joins them,
edits, and writes the fake into the first run so formatting survives.

| Type | How it is found |
|---|---|
| Names | learned names in any case (also `KushalSubbayya`), cues, a short given-name list |
| Emails, phones | patterns; a bare 10-digit number is a phone only after a cue such as `Call`, never after `Order` / `Ticket` |
| Company names | words ending in Limited / Private Limited / LLP / Trust / ..., plus learned short forms |
| Addresses | anchored on a postal code (Indian PIN, US ZIP), a PO box, or `State, India` with a house number; the start is found by walking left |
| SSN, credit card | `NNN-NN-NNNN` (impossible areas rejected); 13-19 digits that pass the Luhn check |
| Date of birth | a date next to a cue (`DOB`, `born on`, `date of birth`); other dates are left alone |
| IP addresses | IPv4 (octets 0-255) and validated IPv6 |
| Web addresses | not on the spec's list; redacted because a company website identifies the company we just renamed |

## Evaluation

I read the whole prospectus (all 2,262 blocks that contain letters) next to the tool's output, and recorded what was
wrong: redactions that were not PII, and PII the tool missed (`evaluation/data/review_corrections.json`). Every other
redaction counts as correct. Accuracy is measured per word (is this word PII of this type or not?); precision, recall and
F1 are measured per span. Run `python evaluation/run_evaluation.py`; **Evaluation Report.docx** has the definitions,
per-type tables and error analysis.

| Accuracy | Precision | Recall | F1 |
|---|---|---|---|
| 0.9993 | 1.000 | 0.971 | 0.985 |

Accuracy is high because most words are not PII. Precision only says the reviewer found nothing wrongly redacted; recall
counts the 20 spans the reviewer found that the tool missed. The review was done by one person and the rules were
adjusted while reading, so treat the numbers as describing this document, not others. SSNs, cards, IPs and dates of birth
do not occur in the prospectus, so they are not scored; they are covered by unit tests (`python -m unittest discover -s tests`).

## Tradeoffs, false positives and false negatives

* **Names without any cue are missed.** A rule cannot tell `Priya Nair` from `Field Manager` by shape. Names are found from
  context, from the document itself, or from the given-name list (names in the prospectus and the spec's examples).
* **Organisations with no legal suffix are missed** (`I-Sec`, `CareEdge Research`, `Trilegal`, `Citibank N.A.`): 18 of the 20
  misses. The other two are a person written as `Gopal BO` and the first line of an address split from its PIN code.
* **No false positives in the final output**, but earlier versions had them: glossary terms such as `Basic Custom Duty` or
  `Indian Rupees` looked like names. `lexicons.NON_NAME_WORDS` is the list that grows when that happens.
* Addresses with no postal code are found only when they carry a house or unit number and end in a state and `India`.
* A 16-digit tracking number that happens to pass the Luhn check is redacted unless a label such as `Tracking` or `Order`
  precedes it.

## Decisions and open questions (not covered by the spec)

The spec says "ticket log" but the attached file is a Red Herring Prospectus, so I built a general `.docx` redactor and
evaluated it on the prospectus. Where the spec is silent I made these calls; most are word-list changes in
`pii_redactor/lexicons.py`.

1. **Company names:** all are redacted, third parties included (banks, auditors, customers, suppliers), because the spec
   lists company names as PII. **Kept:** regulators, exchanges, depositories and government bodies (SEBI, BSE, NSE, RBI, NSDL,
   Registrar of Companies, ...), since naming them identifies nobody (`ORG_ALLOWLIST_KEYWORDS`).
2. **Business contact details of named people** (a bank officer's email and phone) are redacted although the document is public.
3. **Reference numbers are not PII:** order and ticket numbers, CIN, SEBI registration, firm registration and peer-review numbers.
4. **Dates:** only dates of birth are redacted; deal, filing and certificate dates stay (the prospectus has no DOBs).
5. **Addresses of public bodies** (SEBI, the Registrar of Companies, the registrar to the offer) are redacted, because the
   spec asks for physical addresses.
6. **Websites** are redacted unless they belong to a regulator, exchange or government body (`URL_ALLOWLIST_SUFFIXES`).
7. **Newspapers** named as advertising media (Financial Express, Jansatta) are treated as public references.
8. **Family "Branch" labels** (`Rajesh Branch`) are redacted, because the first name identifies a person.
9. **SSNs starting with 9** are treated as invalid (never issued), and **documentation IP ranges** (192.0.2.x, 198.51.100.x,
   203.0.113.x, 2001:db8:ffff::) as already fake, so that the tool's own fakes are never redacted again.
10. **Not handled:** text inside images (the QR code), tracked changes and comments (read but untested), names split across
    different table cells. Document properties (author, title) are cleared.
11. **No reversal:** fakes come from a seeded hash, so a run is reproducible, but the real-to-fake mapping is not stored.
    `--audit file.csv` writes it for debugging; it contains the real values, so keep it private.
12. **Locale:** English text with Indian and US formats (PIN, ZIP, `+91`, US phone numbers). Other locales are not covered.

## Extending: adding a new PII type

Three steps. Example: Indian PAN numbers.

```python
# 1. a detector (pii_redactor/detectors/structured.py)
class PanDetector(RegexDetector):
    """Indian PAN: five letters, four digits, one letter."""
    type, priority = "PAN", 45          # lower priority number wins when spans overlap
    pattern = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

# 2. its fake generator (pii_redactor/fakes.py, method name = "_fake_" + type.lower())
def _fake_pan(self, original):
    def make(n):
        h = _h(self.seed, "pan", original, n)
        letters = "".join(chr(65 + (h >> (5 * i)) % 26) for i in range(6))
        return letters[:5] + f"{h % 10000:04d}" + letters[5]
    return self._unique("PAN", original, make)      # _unique keeps fakes distinct and consistent

# 3. register it (pii_redactor/detectors/__init__.py)
def default_detectors():
    return [..., PanDetector()]
```

A detector that needs document-wide knowledge (like names) also implements `learn(texts, ctx)` and stores what it learned
on the shared `Context`; see `detectors/person.py`.

## Layout

```
redact.py                  command line entry point
pii_redactor/              engine.py (two passes), docx_io.py (Word text and runs), detectors/ (one module per family),
                           fakes.py (fake values), lexicons.py (all word lists and switches), spans.py
tests/                     unit tests
evaluation/                metrics.py, run_evaluation.py, report_docx.py, data/review_corrections.json
Redacted Prospectus.docx   output for the assignment
Evaluation Report.docx     accuracy, precision, recall, error analysis
```
