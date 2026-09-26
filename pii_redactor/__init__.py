"""Rule-based PII redaction for .docx files (regex + context rules, no ML)."""
from .engine import Redactor

__all__ = ["Redactor"]
