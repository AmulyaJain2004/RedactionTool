"""Detector registry. Add new PII types here (see README, "Extending")."""
from .address import AddressDetector
from .base import Context, Detector, RegexDetector
from .company import CompanyDetector
from .person import PersonDetector
from .structured import (CreditCardDetector, DobDetector, EmailDetector, IpDetector,
                         PhoneDetector, SsnDetector, UrlDetector)

__all__ = ["Context", "Detector", "RegexDetector", "default_detectors"]


def default_detectors():
    """All detectors. Overlaps are settled by each detector's `priority`; list order only matters for
    learning: PersonDetector runs before CompanyDetector so company short forms never reuse a person's name."""
    return [
        EmailDetector(), UrlDetector(), SsnDetector(), CreditCardDetector(), IpDetector(),
        PhoneDetector(), DobDetector(), AddressDetector(), PersonDetector(), CompanyDetector(),
    ]
