"""Evaluation of the redactor on the Red Herring Prospectus: scoring, runner and report."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(ROOT)
PROSPECTUS_DOCX = os.path.join(PROJECT, "Red Herring Prospectus.docx")
CORRECTIONS_JSON = os.path.join(ROOT, "data", "review_corrections.json")    # what the review found wrong
RESULTS_JSON = os.path.join(ROOT, "results.json")
