"""Reading and rewriting text inside a .docx while keeping its formatting.

Word splits text into many "runs" (`<w:t>` elements), so a name can be spread over several runs.
`ParagraphText` exposes a paragraph as one string and maps every character back to the run it
came from, so a replacement can be written into the first run and removed from the others.
"""
import re
from lxml import etree

from docx import Document
from docx.oxml.ns import qn

_W_P, _W_T, _W_TC = qn("w:p"), qn("w:t"), qn("w:tc")
# Tabs and line breaks separate words in Word; treat them as a space in the paragraph string.
_SPACE_TAGS = {qn("w:tab"), qn("w:br"), qn("w:cr")}
# Package parts that hold document text.
_TEXT_PARTS = re.compile(r"^/word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$")


class ParagraphText:
    """One `<w:p>` element seen as plain text, with a character -> run mapping."""

    def __init__(self, paragraph_element):
        self.element = paragraph_element
        self._nodes = []      # the `<w:t>` elements that own text
        self._chars = []      # the paragraph text, one character at a time
        self._origin = []     # per character: (index into _nodes, offset in that run), or None for a tab / break
        self._collect(paragraph_element)
        self.text = "".join(self._chars)

    def _collect(self, element):
        for child in element:
            if child.tag == _W_P:
                continue                        # nested paragraph (text box) is handled on its own
            if child.tag == _W_T:
                self._nodes.append(child)
                for offset, ch in enumerate(child.text or ""):
                    self._chars.append(ch)
                    self._origin.append((len(self._nodes) - 1, offset))
            elif child.tag in _SPACE_TAGS:
                self._chars.append(" ")
                self._origin.append(None)
            else:
                self._collect(child)

    def apply(self, replacements):
        """Apply [(start, end, new_text), ...] (non-overlapping) to the underlying runs."""
        if not replacements:
            return
        pieces = [list(node.text or "") for node in self._nodes]              # editable characters per run
        for start, end, new_text in replacements:
            covered = [origin for origin in self._origin[start:end] if origin is not None]   # tabs / breaks stay
            for n, (run, offset) in enumerate(covered):
                pieces[run][offset] = new_text if n == 0 else ""                # new text goes in the first run

        for node, chars in zip(self._nodes, pieces):
            node.text = "".join(chars)
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


class TextBlock:
    """Consecutive paragraphs of one table cell, exposed as one string (paragraphs joined by a newline)."""

    def __init__(self, paragraphs):
        self.paragraphs = paragraphs
        self.text = "\n".join(p.text for p in paragraphs)
        # Start offset of each paragraph inside `self.text`.
        self._offsets, position = [], 0
        for paragraph in paragraphs:
            self._offsets.append(position)
            position += len(paragraph.text) + 1

    def apply(self, replacements):
        """Apply [(start, end, new_text), ...] given in block coordinates. A span that crosses a
        paragraph boundary puts the new text in its first paragraph and empties the covered rest."""
        per_paragraph = [[] for _ in self.paragraphs]
        for start, end, new_text in replacements:
            first_piece = True
            for index, paragraph in enumerate(self.paragraphs):
                p_start = self._offsets[index]
                p_end = p_start + len(paragraph.text)
                lo, hi = max(start, p_start), min(end, p_end)
                if lo < hi:
                    per_paragraph[index].append((lo - p_start, hi - p_start, new_text if first_piece else ""))
                    first_piece = False
        for paragraph, edits in zip(self.paragraphs, per_paragraph):
            paragraph.apply(edits)


def _root_of(part):
    """XML root of a package part (python-docx loads header/footer parts, but not footnotes)."""
    if hasattr(part, "element"):
        return part.element, None
    try:
        root = etree.fromstring(part.blob)
    except etree.XMLSyntaxError:
        return None, None
    return root, part


class DocxDocument:
    """Opens a .docx and gives access to every paragraph in body, tables, headers, footers, text boxes."""

    # Body lines shorter than this may be pieces of one address or list ("Pune - 410 501" / "India").
    SHORT_LINE = 100

    def __init__(self, path):
        self.document = Document(path)
        self._roots = []           # (root element, generic part or None)
        for part in self.document.part.package.iter_parts():
            if _TEXT_PARTS.match(str(part.partname)):
                root, generic = _root_of(part)
                if root is not None:
                    self._roots.append((root, generic))

    def paragraphs(self):
        """All paragraphs with non-empty text, in a stable order."""
        found = []
        for root, _ in self._roots:
            for element in root.iter(_W_P):
                paragraph = ParagraphText(element)
                if paragraph.text.strip():
                    found.append(paragraph)
        return found

    def blocks(self):
        """Paragraphs grouped for detection: paragraphs of one table cell form one block (an address
        is often split over several lines of a cell); every other paragraph is its own block."""
        blocks, current, current_parent = [], [], None
        for paragraph in self.paragraphs():
            parent = paragraph.element.getparent()
            if current and parent is current_parent and self._belong_together(current[-1], paragraph, parent):
                current.append(paragraph)
                continue
            if current:
                blocks.append(TextBlock(current))
            current, current_parent = [paragraph], parent
        if current:
            blocks.append(TextBlock(current))
        return blocks

    def _belong_together(self, previous, paragraph, parent) -> bool:
        if parent.tag == _W_TC:                                    # same table cell
            return True
        # A short line that follows text which did not end a sentence (an address split over lines).
        return len(paragraph.text) <= self.SHORT_LINE and not previous.text.rstrip().endswith(".")

    def scrub_metadata(self):
        """Remove author / title style properties from the file."""
        props = self.document.core_properties
        for name in ("author", "last_modified_by", "title", "subject", "keywords", "comments", "category"):
            setattr(props, name, "")

    def save(self, path):
        """Write the document, including text parts that python-docx keeps as raw bytes."""
        for root, generic in self._roots:
            if generic is not None:                     # write back parts python-docx keeps as raw bytes
                generic._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        self.document.save(path)
