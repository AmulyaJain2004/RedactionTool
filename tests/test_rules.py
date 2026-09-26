"""Tests for the rules added after the first evaluation round (precision guards, extra formats)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pii_redactor import Redactor


def spans(text, *context):
    redactor = Redactor()
    redactor.learn([text, *context])
    return [(s.type, s.text) for s in redactor.detect(text)]


class ReferenceNumbersStayUntouched(unittest.TestCase):
    """The assignment: order / ticket numbers are not PII."""

    def test_bare_ten_digit_order_number_is_not_a_phone(self):
        self.assertEqual(spans("Order 9876543210 shipped"), [])
        self.assertEqual(spans("Order #9876543210 is delayed"), [])

    def test_bare_mobile_needs_a_cue_or_grouping(self):
        self.assertEqual(spans("Call 9876543210 now"), [("PHONE", "9876543210")])
        self.assertEqual(spans("Contact: 98765 43210"), [("PHONE", "98765 43210")])
        self.assertEqual(spans("the value 9876543210 was stored"), [])

    def test_luhn_valid_number_after_a_reference_label_is_not_a_card(self):
        self.assertEqual(spans("Case 4111111111111111 migrated"), [])
        self.assertEqual(spans("Tracking 4111 1111 1111 1111"), [])
        self.assertEqual(spans("card 4111 1111 1111 1111")[0][0], "CREDIT_CARD")

    def test_version_numbers_are_not_ip_addresses(self):
        self.assertEqual(spans("Server build v2.3.4.5 restarted"), [])
        self.assertEqual(spans("version 10.1.2.3 released"), [])
        self.assertEqual(spans("from 10.1.2.3 blocked")[0][0], "IP_ADDRESS")

    def test_reference_pin_is_not_an_address(self):
        self.assertEqual(spans("PIN code 400001 is not serviceable"), [])


class MoreFormats(unittest.TestCase):
    def test_phone_at_the_end_of_a_sentence(self):
        self.assertEqual(spans("Callback: (415) 555-9618."), [("PHONE", "(415) 555-9618")])
        self.assertEqual(spans("reach them on 415-555-7395."), [("PHONE", "415-555-7395")])
        self.assertEqual(spans("Phone: 022-2367 1980."), [("PHONE", "022-2367 1980")])
        self.assertEqual(spans("Phone: (+91) 98107-53029 today")[0][0], "PHONE")

    def test_date_of_birth_cue_may_be_a_few_words_away(self):
        found = spans("change the date of birth of Uday E. Chatterjee to 12/02/1967")
        self.assertEqual(found[-1], ("DOB", "12/02/1967"))
        self.assertEqual(spans("Invoice dated 12/03/2024 is overdue"), [])

    def test_all_caps_and_apostrophe_names_after_a_label(self):
        self.assertIn(("PERSON", "MASON ANDERSON"), spans("Customer: MASON ANDERSON | Company: Zenco Limited"))
        self.assertIn(("PERSON", "Rahul O'Brien"), spans("Customer: Rahul O'Brien"))

    def test_acronyms_after_a_preposition_are_not_names(self):
        self.assertEqual([t for k, t in spans("issued by SEBI ICDR and filed") if k == "PERSON"], [])

    def test_spec_example_line(self):
        found = spans("Rashi Patil: rashhi.patil@gmail.com and Rohan Dey: +91 9876543210")
        self.assertEqual(found, [("PERSON", "Rashi Patil"), ("EMAIL", "rashhi.patil@gmail.com"),
                                 ("PERSON", "Rohan Dey"), ("PHONE", "+91 9876543210")])

    def test_field_labels_are_not_names(self):
        self.assertEqual([k for k, _ in spans("Registered Office: 11 Main Road") if k == "PERSON"], [])

    def test_po_box(self):
        self.assertEqual(spans("Write to P.O. Box 6209, Seattle, WA 98101 today")[0][0], "ADDRESS")

    def test_company_suffixes(self):
        for name in ["Zentrio Corp.", "Kavora Inc.", "Nexor Solutions Pvt. Ltd.", "Orbis GmbH"]:
            self.assertEqual(spans(f"paid to {name} yesterday")[0], ("COMPANY", name), name)

    def test_role_words_do_not_join_a_company_name(self):
        self.assertEqual(spans("Vendor Zentrio Labs Limited invoiced us"), [("COMPANY", "Zentrio Labs Limited")])


class Idempotence(unittest.TestCase):
    def test_redacting_twice_changes_nothing_for_structured_types(self):
        text = "mail a.b@corp.com from 10.20.30.40 and 2001:db8:85a3::8a2e:370:7334, SSN 123-45-6789"
        once = Redactor()
        once.learn([text])
        first = once.redact_text(text)
        again = Redactor()
        again.learn([first])
        self.assertEqual(again.redact_text(first), first)

    def test_same_number_different_layout_keeps_each_layout(self):
        redactor = Redactor()
        text = "Call 9876543210 or Contact: 98765 43210"
        redactor.learn([text])
        first, second = [p for p in redactor.redact_text(text).replace("Call ", "").split(" or Contact: ")]
        self.assertEqual(first, second.replace(" ", ""))
        self.assertIn(" ", second)


if __name__ == "__main__":
    unittest.main()
