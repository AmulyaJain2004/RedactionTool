"""Command line entry point.

    python redact.py "Red Herring Prospectus.docx" -o "Redacted Prospectus.docx"
"""
import argparse
import csv
import sys
from collections import Counter

from pii_redactor import Redactor


def main(argv=None):
    """Parse the command line, redact the file and print a per-type summary."""
    parser = argparse.ArgumentParser(description="Replace PII in a .docx with consistent fake values.")
    parser.add_argument("input", help="source .docx")
    parser.add_argument("-o", "--output", required=True, help="redacted .docx to write")
    parser.add_argument("--seed", default="pii-redactor", help="seed for the deterministic fake values")
    parser.add_argument("--audit", help="optional CSV of type,original,fake,count "
                                        "(contains the ORIGINAL values - keep it private)")
    args = parser.parse_args(argv)

    redactor = Redactor(seed=args.seed)
    total = redactor.redact_docx(args.input, args.output)

    per_type = Counter()
    for (pii_type, _, _), count in redactor.audit.items():
        per_type[pii_type] += count
    print(f"Redacted {total} spans -> {args.output}")
    for pii_type, count in sorted(per_type.items()):
        print(f"  {pii_type:12s} {count}")

    if args.audit:
        with open(args.audit, "w", newline="", encoding="utf8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["type", "original", "fake", "count"])
            for (pii_type, original, fake), count in sorted(redactor.audit.items()):
                writer.writerow([pii_type, original, fake, count])
    return 0


if __name__ == "__main__":
    sys.exit(main())
