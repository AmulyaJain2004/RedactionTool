# RedactionTool

A command-line tool that finds personally identifiable information (PII) in Word documents and replaces each value with a
realistic, consistent fake one. Formatting, tables, headers, footers and images are preserved.

It is rule-based (regular expressions plus context rules): no NER model, no external service, no network access.

## Contents

- [Quick start](#quick-start)
- [What is redacted](#what-is-redacted)
- [How it works](#how-it-works)
- [Web app and hosting](#web-app-and-hosting)
- [Project structure](#project-structure)
- [Evaluation](#evaluation)
- [Trade-offs and known limitations](#trade-offs-and-known-limitations)
- [Design decisions](#design-decisions)
- [Extending the tool](#extending-the-tool)

## Quick start

Requirements: Python 3.12 (the version the tool was developed and tested on).

```bash
git clone https://github.com/AmulyaJain2004/RedactionTool.git
cd RedactionTool
pip install -r requirements.txt

python redact.py "Red Herring Prospectus.docx" -o "Redacted Prospectus.docx"
```

The command prints how many values of each type were replaced. The same input and seed always give the same output.

| Option | Purpose |
|---|---|
| `-o, --output FILE` | Redacted `.docx` to write (required) |
| `--seed TEXT` | Seed for the fake values (default `pii-redactor`) |
| `--audit FILE.csv` | Write a CSV of `type, original, fake, count` for debugging. It contains the real values, so it must stay private (the `.gitignore` excludes `audit*.csv`). |

Run the tests and the evaluation:

```bash
python -m unittest discover -s tests          # unit tests (the web-app tests need requirements-web.txt)
python evaluation/run_evaluation.py           # accuracy, precision, recall, F1 on the prospectus
python evaluation/report_docx.py              # regenerate Evaluation Report.docx
```

## What is redacted

| Type | How it is found |
|---|---|
| Names | Names learned from context (`Contact Person:`, `being`, `Promoter,`, lists of names) and matched everywhere in any case, plus a short given-name list |
| Emails, phones | Patterns. A bare 10-digit number counts as a phone only after a cue such as `Call`, and never after `Order` or `Ticket` |
| Company names | Names ending in Limited, Private Limited, LLP, Trust and similar, plus their learned short forms |
| Addresses | Anchored on a postal code (Indian PIN, US ZIP), a PO box, or `State, India` with a house number; the start is found by walking left |
| SSN, credit card | `NNN-NN-NNNN` with impossible areas rejected; 13 to 19 digits that pass the Luhn check |
| Date of birth | A date next to a cue (`DOB`, `born on`, `date of birth`); other dates are left alone |
| IP addresses | IPv4 (octets 0 to 255) and validated IPv6 |
| Web addresses | Not on the assignment's list; redacted because a company website identifies the renamed company |

## How it works

The tool makes two passes over the document.

1. **Learn.** All text is read once to find which lower-case words are ordinary prose (so "Offer" is not taken for a
   name), which people appear, and which company names and short forms appear (`KSH International Limited` also teaches
   `KSH`).
2. **Redact.** Every detector proposes spans, overlaps are settled by priority, and each span receives a fake value.

Fake values are deterministic and consistent: the same real value always gets the same fake, different real values never
share one, and the format is kept (`+91 98765 43210` stays a 10-digit number after `+91`, card numbers stay Luhn-valid, a
shared surname maps to the same fake surname). Word splits text into runs (`rohan.` `dey@gmail` `.com`); the tool joins
them, edits the text, and writes the fake into the first run so the formatting survives.

## Web app and hosting

`app.py` is a small Flask app: a page where a user uploads a `.docx` and downloads the redacted copy. The same code runs
locally, in Docker and on any hosting platform.

### Run the web app locally

```bash
pip install -r requirements.txt -r requirements-web.txt
python app.py                      # http://localhost:8000
```

`GET /health` returns `{"status": "ok"}` for uptime checks. Environment variables: `PORT` (default 8000) and
`MAX_UPLOAD_MB` (default 25).

### Run it in Docker

```bash
docker build -t redactiontool .
docker run --rm -p 8000:8000 redactiontool          # http://localhost:8000
```

The image runs `gunicorn` as an unprivileged user and honours the `PORT` variable that hosting platforms set.

### Deploy on Render (free tier available)

1. Push the repository to GitHub.
2. In Render choose **New > Web Service**, connect the repository and select the `main` branch.
3. Render detects the `Dockerfile` and builds it. Set the **Health Check Path** to `/health`.
4. Choose an instance type and click **Create Web Service**. Render provides an HTTPS URL when the build finishes.

Without Docker, use the same service with build command `pip install -r requirements.txt -r requirements-web.txt` and start
command `gunicorn app:app --workers 2 --timeout 120`. The Docker image also runs on Fly.io, Railway, Google Cloud Run,
Azure Container Apps and AWS App Runner.

### Before exposing it to real users

- The page has **no login**. For sensitive documents run it inside a private network or behind an authenticating proxy.
- Uploads are processed in a temporary folder that is deleted before the response is sent; nothing is stored or logged.
- Free tiers put idle services to sleep, so the first request after a pause can take several seconds.
- Very large documents take longer; raise `--timeout` in the start command and `MAX_UPLOAD_MB` if needed.

## Project structure

```
RedactionTool/
├── redact.py                     Command-line entry point
├── app.py                        Web app: upload a .docx, download the redacted copy
├── Dockerfile                    Container image for the web app
├── requirements.txt              Core dependencies: python-docx, lxml
├── requirements-web.txt          Web dependencies: flask, gunicorn
├── pii_redactor/                 The redaction library
│   ├── engine.py                 Redactor: learn pass, detect, replace, write the .docx
│   ├── docx_io.py                Word text and runs, table-cell blocks, safe in-place edits
│   ├── detectors/                One module per family of PII
│   │   ├── base.py               Detector base classes and the shared Context
│   │   ├── structured.py         Email, URL, SSN, card, IP, phone, date of birth
│   │   ├── address.py            Addresses
│   │   ├── person.py             Person names
│   │   └── company.py            Company names
│   ├── fakes.py                  Deterministic, format-preserving fake values
│   ├── lexicons.py               Every word list and switch (allowlists, given names, suffixes)
│   └── spans.py                  Span type and overlap resolution
├── evaluation/                   Scoring on the prospectus
│   ├── metrics.py                Accuracy, precision, recall, F1
│   ├── run_evaluation.py         Runs the redactor and scores it; writes results.json
│   ├── report_docx.py            Builds Evaluation Report.docx from results.json
│   └── data/review_corrections.json   What the review found wrong (see Evaluation)
├── tests/                        Unit tests
├── Red Herring Prospectus.docx   Input document
├── Redacted Prospectus.docx      Output
└── Evaluation Report.docx        Accuracy, precision, recall and error analysis
```

## Evaluation

The whole prospectus (all 2,262 blocks that contain letters) was read next to the tool's output. Two things were recorded
in `evaluation/data/review_corrections.json`: redactions that were not PII (none) and PII the tool missed (20 spans).
Every other redaction counts as correct. Accuracy is measured per word (is this word PII of this type or not?);
precision, recall and F1 are measured per span.

| Accuracy | Precision | Recall | F1 |
|---|---|---|---|
| 0.9993 | 1.000 | 0.971 | 0.985 |

Accuracy is high because most words are not PII. Precision only shows that the review found nothing wrongly redacted;
recall counts the PII the review found that the tool missed. The review was done by one person and the rules were adjusted
while reading, so the numbers describe this document, not others. SSNs, cards, IP addresses and dates of birth do not
occur in the prospectus, so they are not scored; unit tests cover them. Definitions, per-type tables and the error
analysis are in `Evaluation Report.docx`.

## Trade-offs and known limitations

- **Names without a cue are missed.** A rule cannot tell `Priya Nair` from `Field Manager` by shape. Names are found from
  context, from the document itself, or from the given-name list.
- **Organisations without a legal suffix are missed** (`I-Sec`, `CareEdge Research`, `Trilegal`, `Citibank N.A.`): 18 of the
  20 misses. The other two are a person written as `Gopal BO` and the first line of an address separated from its PIN code.
- **False positives** were found and fixed during the review (glossary terms such as `Basic Custom Duty` looked like
  names); none remain in the final output. `lexicons.NON_NAME_WORDS` is the list to extend when this happens.
- Addresses without a postal code are found only when they carry a house or unit number and end in a state and `India`.
- A 16-digit tracking number that passes the Luhn check is redacted unless a label such as `Tracking` or `Order` precedes it.
- Not handled: text inside images (the QR code), tracked changes and comments (read but untested), and names split across
  different table cells.

## Design decisions

The assignment mentions a "ticket log", but the supplied file is a Red Herring Prospectus, so a general `.docx` redactor was
built and evaluated on the prospectus. Where the assignment is silent, these decisions were made; most are word-list changes
in `pii_redactor/lexicons.py`.

1. **Company names:** all are redacted, third parties included (banks, auditors, customers, suppliers), because the
   assignment lists company names as PII. Regulators, exchanges, depositories and government bodies (SEBI, BSE, NSE, RBI,
   NSDL, Registrar of Companies) are kept, since naming them identifies nobody (`ORG_ALLOWLIST_KEYWORDS`).
2. **Business contact details of named people** (a bank officer's email and phone) are redacted although the document is
   public.
3. **Reference numbers are not PII:** order and ticket numbers, CIN, SEBI registration, firm registration and peer-review
   numbers.
4. **Dates:** only dates of birth are redacted; deal, filing and certificate dates stay.
5. **Addresses of public bodies** (SEBI, the Registrar of Companies, the registrar to the offer) are redacted, because the
   assignment asks for physical addresses.
6. **Websites** are redacted unless they belong to a regulator, exchange or government body (`URL_ALLOWLIST_SUFFIXES`).
7. **Newspapers** named as advertising media (Financial Express, Jansatta) are treated as public references.
8. **Family "Branch" labels** (`Rajesh Branch`) are redacted, because the first name identifies a person.
9. **SSNs starting with 9** are treated as invalid (never issued), and **documentation IP ranges** (192.0.2.x, 198.51.100.x,
   203.0.113.x, 2001:db8:ffff::) as already fake, so the tool's own fakes are never redacted again.
10. **No reversal:** fakes come from a seeded hash, so a run is reproducible, but the real-to-fake mapping is not stored.
    Document properties (author, title) are cleared.
11. **Locale:** English text with Indian and US formats (PIN, ZIP, `+91`, US phone numbers). Other locales are not covered.

## Extending the tool

A new PII type takes three steps. Example: Indian PAN numbers.

```python
# 1. Detector (pii_redactor/detectors/structured.py)
class PanDetector(RegexDetector):
    """Indian PAN: five letters, four digits, one letter."""
    type, priority = "PAN", 45          # lower priority number wins when spans overlap
    pattern = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

# 2. Fake generator (pii_redactor/fakes.py; the method name is "_fake_" + type in lower case)
def _fake_pan(self, original):
    def make(n):
        h = _h(self.seed, "pan", original, n)
        letters = "".join(chr(65 + (h >> (5 * i)) % 26) for i in range(6))
        return letters[:5] + f"{h % 10000:04d}" + letters[5]
    return self._unique("PAN", original, make)      # keeps fakes distinct and consistent

# 3. Registration (pii_redactor/detectors/__init__.py)
def default_detectors():
    return [..., PanDetector()]
```

A detector that needs document-wide knowledge (like names) also implements `learn(texts, ctx)` and stores what it learned on
the shared `Context`; see `detectors/person.py`.
