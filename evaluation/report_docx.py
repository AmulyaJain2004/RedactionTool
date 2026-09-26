"""Write "Evaluation Report.docx" from evaluation/results.json.

    python evaluation/run_evaluation.py     # produces results.json
    python evaluation/report_docx.py        # produces ../Evaluation Report.docx
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document                                   # noqa: E402
from docx.enum.table import WD_TABLE_ALIGNMENT              # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH               # noqa: E402
from docx.oxml import OxmlElement                           # noqa: E402
from docx.oxml.ns import qn                                 # noqa: E402
from docx.shared import Pt, RGBColor                        # noqa: E402

from evaluation import PROJECT, RESULTS_JSON                # noqa: E402

TYPE_LABEL = {"PERSON": "Full names", "COMPANY": "Company names", "ADDRESS": "Addresses",
              "EMAIL": "Email addresses", "PHONE": "Phone numbers", "URL": "Web addresses"}


def f3(value):
    """Three decimals."""
    return f"{value:.3f}"


def f4(value):
    """Four decimals (accuracy is so close to 1 that three are not enough)."""
    return f"{value:.4f}"


def shade(cell, hex_color):
    """Fill a table cell with a background colour."""
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shading)


class Report:
    """Thin wrapper around python-docx with the few building blocks the report needs."""

    def __init__(self):
        self.doc = Document()
        style = self.doc.styles["Normal"]
        style.font.name, style.font.size = "Calibri", Pt(10.5)
        for section in self.doc.sections:
            section.left_margin = section.right_margin = Pt(64)
            section.top_margin = section.bottom_margin = Pt(60)

    def heading(self, text, level=1):
        """Add a heading."""
        self.doc.add_heading(text, level=level)

    def paragraph(self, text, italic=False):
        """Add a paragraph."""
        self.doc.add_paragraph().add_run(text).italic = italic

    def bullets(self, items):
        """Add a bullet list."""
        for item in items:
            self.doc.add_paragraph(item, style="List Bullet")

    def table(self, header, rows, widths=None, highlight_last=False):
        """Add a table with a coloured header row; optionally emphasise the last (total) row."""
        table = self.doc.add_table(rows=1, cols=len(header))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for cell, text in zip(table.rows[0].cells, header):
            run = cell.paragraphs[0].add_run(text)
            run.bold, run.font.size = True, Pt(9)
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            shade(cell, "2F4B6E")
        for row_number, row in enumerate(rows):
            cells = table.add_row().cells
            is_total = highlight_last and row_number == len(rows) - 1
            for column, (cell, text) in enumerate(zip(cells, row)):
                run = cell.paragraphs[0].add_run(str(text))
                run.font.size, run.bold = Pt(9), is_total
                if column > 0:
                    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if is_total:
                    shade(cell, "E8EEF5")
        if widths:
            for row in table.rows:
                for cell, width in zip(row.cells, widths):
                    cell.width = Pt(width)
        self.doc.add_paragraph()

    def save(self, path):
        """Write the .docx."""
        self.doc.save(path)


# ---- one function per report section -----------------------------------------------------------------------

def section_summary(r, results):
    """Section 1: the headline numbers and how to read them."""
    o = results["overall"]
    r.heading("1. Summary", 1)
    r.table(["Accuracy", "Precision", "Recall", "F1", "PII spans", "Redacted correctly", "Wrongly redacted", "Missed"],
            [[f4(o["token_accuracy"]), f3(o["precision"]), f3(o["recall"]), f3(o["f1"]), results["reviewed_spans"],
              o["tp"], o["fp"], o["fn"]]], widths=[55, 55, 50, 40, 55, 75, 70, 45])
    r.bullets([
        f"Accuracy is measured on words: each of the {results['tokens']:,} words of the document is PII or not, "
        "and the redactor's label is compared with the label the review gave. Most words are not PII, so "
        "accuracy is always high; precision and recall are the numbers that show how good the redactor is.",
        "Precision, recall and F1 are measured on spans (one name, one address, one phone number, ...). "
        "Precision is the share of redactions that were correct; recall is the share of the PII that was redacted.",
        "The numbers come from one careful read of the whole document next to the redactor's output (section 2). "
        "Precision only says that the reviewer found nothing wrongly redacted; recall counts the PII the reviewer "
        "found that the redactor missed (section 6).",
    ])


def section_data(r, results):
    """Section 2: the document and how the review was done."""
    r.heading("2. Data and review", 1)
    r.paragraph(f"Document: Red Herring Prospectus of KSH International Limited: {results['blocks']:,} blocks, "
                f"{results['characters']:,} characters, {results['tokens']:,} words. A block is the unit that is "
                "scored: the paragraphs of one table cell, or one body paragraph.")
    rows = [[TYPE_LABEL[k], v["reviewed"]] for k, v in results["by_type"].items()]
    rows.append(["All types", results["reviewed_spans"]])
    r.table(["PII type", "PII spans in the document"], rows, widths=[200, 130], highlight_last=True)
    r.heading("How the review was done", 2)
    r.bullets([
        "All 2,262 blocks that contain letters were printed with the redactor's redactions marked in place and read "
        "in full; the remaining blocks are numeric table cells.",
        "Every redaction was judged: correct, or wrong. Nothing was found to be wrongly redacted in the final output.",
        "PII the redactor did not redact was listed by text. Each occurrence of such a text that the redactor did "
        "not already cover counts as one missed span. The list is in evaluation/data/review_corrections.json.",
        "Wrong redactions found during the review were fixed in the code, so the numbers describe the final code.",
        "Deliberately not treated as PII: regulators, exchanges and government bodies (SEBI, BSE, NSE, RBI, "
        "NSDL, ...); newspapers named as advertising media; CIN, SEBI registration, firm registration and "
        "peer-review numbers; deal and filing dates; page and section numbers.",
    ])


def section_metrics(r, results):
    """Section 3: what each number means."""
    r.heading("3. Metrics", 1)
    r.table(["Term", "Meaning"], [
        ["TP", "a redaction the review confirmed as PII"],
        ["FP", "a redaction the review judged not to be PII"],
        ["FN", "PII the redactor did not redact"],
        ["Accuracy", "(TP + TN) / all words, where a word is positive when it belongs to a PII span of that type"],
        ["Precision", "TP / (TP + FP): of the spans the redactor changed, how many should have been changed"],
        ["Recall", "TP / (TP + FN): of the PII spans in the document, how many were redacted"],
        ["F1", "Harmonic mean of precision and recall"],
    ], widths=[70, 400])
    r.paragraph("TP, FP and FN count spans. The overall row is the sum over all types (micro average). Per-type "
                "accuracy treats every word that is not part of that type as a true negative.")


def section_results(r, results):
    """Section 4: the per-type table."""
    r.heading("4. Results by PII type", 1)
    rows = []
    for kind, x in results["by_type"].items():
        rows.append([TYPE_LABEL[kind], x["reviewed"], x["tp"], x["fp"], x["fn"], f3(x["precision"]), f3(x["recall"]),
                     f3(x["f1"]), f4(x["token_accuracy"])])
    o = results["overall"]
    rows.append(["All types", results["reviewed_spans"], o["tp"], o["fp"], o["fn"], f3(o["precision"]),
                 f3(o["recall"]), f3(o["f1"]), f4(o["token_accuracy"])])
    r.table(["Type", "PII spans", "TP", "FP", "FN", "Precision", "Recall", "F1", "Accuracy"], rows,
            widths=[120, 50, 40, 35, 35, 55, 50, 45, 55], highlight_last=True)
    r.paragraph("SSNs, credit card numbers, dates of birth and IP addresses do not occur in this document, so they "
                "have no row. The rules for them are covered by unit tests (tests/). Web addresses are not on the "
                "assignment's list; they are redacted because a company web address identifies the company.")


def section_errors(r, results):
    """Section 5: what was missed and what was wrongly redacted."""
    r.heading("5. Error analysis", 1)
    wrong = results["wrongly_redacted"]
    r.paragraph("Wrongly redacted: " + ("nothing." if not wrong else "; ".join(
        f"{e['text']} ({TYPE_LABEL[e['type']]}, {e['count']}x)" for e in wrong)))
    r.paragraph(f"Missed ({results['overall']['fn']} spans):")
    r.table(["Type", "Text", "Times"], [[TYPE_LABEL[e["type"]], e["text"], e["count"]] for e in results["missed"]],
            widths=[120, 260, 50])
    r.bullets([
        "Organisations named without a legal suffix (I-Sec, CareEdge Research, Sterlite Copper, Trilegal, "
        "Citibank N.A., Export-Import Bank of India): the rules key on Limited / LLP / Trust / ... and on short forms "
        "of names that did carry a suffix.",
        "\"Gopal BO\": a person written with an initials-style surname that no rule links to a known name.",
        "\"C-101, Embassy 247\": the first line of an address whose postal code sits in the next table cell.",
        "Reference numbers were left alone on purpose: CIN, SEBI registration numbers, firm registration and "
        "peer-review numbers.",
    ])


def section_trust(r, results):
    """Section 6: limits of the evaluation."""
    r.heading("6. How far to trust these numbers", 1)
    r.bullets([
        "One person did the review, and only PII that the reviewer noticed can count as missed. Precision (no wrong "
        "redactions found) can therefore be too high, and recall too high if something was overlooked. A second, "
        "independent reviewer was not available.",
        "The redactor's rules were adjusted while the review went on, so the numbers describe the final rules on "
        "this document. They are not a prediction for other documents.",
        "One document was used. Other layouts and name styles will score differently; person recall in particular "
        "depends on cues in the text and on a short list of given names.",
        "Types that do not occur in the document (SSN, credit card, date of birth, IP address) are not scored here.",
    ])


def section_reproduce(r, results):
    """Section 7: the commands that regenerate everything."""
    r.heading("7. Reproduce", 1)
    r.paragraph("python redact.py \"Red Herring Prospectus.docx\" -o \"Redacted Prospectus.docx\"\n"
                "python evaluation/run_evaluation.py\n"
                "python evaluation/report_docx.py")


SECTIONS = (section_summary, section_data, section_metrics, section_results, section_errors, section_trust,
            section_reproduce)


def build(results):
    """Assemble the whole report from the data in results.json."""
    report = Report()
    report.doc.add_heading("PII Redaction: Evaluation Report", level=0)
    report.paragraph("Rule-based redactor (regex + context rules) scored on the Red Herring Prospectus.", italic=True)
    for section in SECTIONS:
        section(report, results)
    return report


if __name__ == "__main__":
    with open(RESULTS_JSON, encoding="utf8") as handle:
        data = json.load(handle)
    out = os.path.join(PROJECT, "Evaluation Report.docx")
    build(data).save(out)
    print("wrote", out)
