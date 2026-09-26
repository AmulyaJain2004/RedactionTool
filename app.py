"""Web front end: upload a .docx, download the redacted .docx.

    python app.py                                  # development server on http://localhost:8000
    gunicorn app:app --bind 0.0.0.0:8000           # production server (what the Dockerfile runs)

Uploaded files are processed in a temporary folder that is deleted before the response is sent; nothing is stored
or logged. The page has no login, so put it behind your own network or an authenticating proxy if the documents are
sensitive.
"""
import io
import os
import tempfile

from docx.opc.exceptions import PackageNotFoundError
from flask import Flask, render_template_string, request, send_file

from pii_redactor import Redactor

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RedactionTool</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 34rem; margin: 3rem auto; padding: 0 1rem; color: #1f2937; }
    h1 { margin-bottom: .2rem; }
    p.lead { color: #4b5563; margin-top: 0; }
    form { border: 1px solid #d1d5db; border-radius: .5rem; padding: 1.25rem; }
    input[type=file] { display: block; margin: 0 0 1rem; }
    button { background: #2f4b6e; color: #fff; border: 0; border-radius: .4rem; padding: .6rem 1.2rem;
             font-size: 1rem; cursor: pointer; }
    .error { color: #b91c1c; margin-top: 1rem; }
    small { color: #6b7280; display: block; margin-top: 1rem; }
  </style>
</head>
<body>
  <h1>RedactionTool</h1>
  <p class="lead">Upload a Word document and download a copy with names, emails, phone numbers, company names,
     addresses and other personal data replaced by fake values.</p>
  <form method="post" action="/redact" enctype="multipart/form-data">
    <input type="file" name="file" accept=".docx" required>
    <button type="submit">Redact and download</button>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
  </form>
  <small>Only .docx files up to {{ max_mb }} MB. Files are processed in memory and deleted immediately.</small>
</body>
</html>"""


def _page(error=None, status=200):
    max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return render_template_string(PAGE, error=error, max_mb=max_mb), status


@app.get("/")
def index():
    """The upload form."""
    return _page()


@app.get("/health")
def health():
    """Liveness check for the hosting platform."""
    return {"status": "ok"}


@app.post("/redact")
def redact():
    """Redact the uploaded .docx and send the result back as a download."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return _page("Choose a .docx file first.", 400)
    if not upload.filename.lower().endswith(".docx"):
        return _page("Only .docx files are supported.", 400)

    with tempfile.TemporaryDirectory() as folder:
        source, target = os.path.join(folder, "in.docx"), os.path.join(folder, "out.docx")
        upload.save(source)
        try:
            Redactor().redact_docx(source, target)
        except (PackageNotFoundError, KeyError):
            return _page("That file is not a valid .docx document.", 400)
        with open(target, "rb") as handle:
            result = io.BytesIO(handle.read())          # read before the temporary folder disappears

    name = os.path.splitext(os.path.basename(upload.filename))[0] + "_redacted.docx"
    return send_file(result, as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.errorhandler(413)
def too_large(_error):
    """Upload bigger than MAX_UPLOAD_MB."""
    return _page("The file is too large.", 413)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
