"""Regression coverage for the Mortgage Protection lead-notification email.

The sender/recipient mechanism is mocked; this file only verifies the presentation
changes required by the minimal intake update. No real email is sent.
"""
from datetime import datetime, timezone

import app as app_module


class FakeCursor:
    def __init__(self, rows): self._rows = rows
    def execute(self, *a, **k): pass
    def fetchall(self): return self._rows
    def close(self): pass


class FakeConnection:
    def __init__(self, rows): self._rows = rows
    def cursor(self): return FakeCursor(self._rows)
    def commit(self): pass
    def close(self): pass


class FakeMail:
    def __init__(self, from_email=None, to_emails=None, subject=None, html_content=None):
        self.from_email = from_email
        self.to_emails = to_emails
        self.subject = subject
        self.html_content = html_content


class FakeSendGridClient:
    sent = []
    def __init__(self, api_key=None): self.api_key = api_key
    def send(self, message): FakeSendGridClient.sent.append(message)


def render_notification(monkeypatch, lead_overrides=None):
    monkeypatch.setenv("SENDGRID_API_KEY", "test-key")
    monkeypatch.setenv("MAIL_SENDER", "sender@example.com")
    monkeypatch.setattr(app_module, "get_connection", lambda: FakeConnection([("agent@example.com", "Agent One")]))
    FakeSendGridClient.sent = []
    monkeypatch.setattr("sendgrid.SendGridAPIClient", FakeSendGridClient)
    monkeypatch.setattr("sendgrid.helpers.mail.Mail", FakeMail)

    lead = {
        "lead_id": 42,
        "first_name": "John",
        "last_name": "Brown",
        "code_word": "Falcon",
        "phone_display": "(619) 432-2727",
        "email": "jb@example.com",
        "zip": "91910",
        "age": 53,
        "sex": "male",
        "tobacco_use": "no",
        "mortgage_balance": "250k_499999",
        "submitted_at_utc": datetime(2026, 8, 28, 18, 58, tzinfo=timezone.utc),
    }
    if lead_overrides:
        lead.update(lead_overrides)

    app_module.send_mortgage_protection_lead_notification(lead)
    assert len(FakeSendGridClient.sent) == 1
    return FakeSendGridClient.sent[0]


def test_subject_uses_first_and_last_name(monkeypatch):
    assert render_notification(monkeypatch).subject == "New Lead: John Brown — Mortgage Protection"


def test_subject_strips_control_characters(monkeypatch):
    message = render_notification(monkeypatch, {"first_name": "John\r\nBcc: bad@example.com", "last_name": "Brown\t"})
    assert "\r" not in message.subject and "\n" not in message.subject and "\t" not in message.subject


def test_brand_is_bfg_insurance_solutions(monkeypatch):
    body = render_notification(monkeypatch).html_content
    assert "BFG" in body and "Insurance Solutions" in body


def test_code_word_is_present(monkeypatch):
    assert "Falcon" in render_notification(monkeypatch).html_content


def test_lead_id_and_received_timestamp_are_present(monkeypatch):
    body = render_notification(monkeypatch).html_content
    assert "Lead ID" in body and ">42<" in body
    assert "Received" in body and "Aug 28, 2026 · 11:58 AM PDT" in body


def test_contact_fields_are_present(monkeypatch):
    body = render_notification(monkeypatch).html_content
    assert "(619) 432-2727" in body
    assert "jb@example.com" in body
    assert "91910" in body


def test_age_and_gender_are_present(monkeypatch):
    body = render_notification(monkeypatch).html_content
    assert ">53<" in body
    assert "Gender" in body and ">Male<" in body


def test_tobacco_is_present_as_no(monkeypatch):
    body = render_notification(monkeypatch).html_content
    assert "Tobacco Use" in body and ">No<" in body


def test_mortgage_balance_approved_enum_is_displayed_human_readable(monkeypatch):
    body = render_notification(monkeypatch).html_content
    assert "$250,000–$499,999" in body
    assert "250k_499999" not in body


def test_historical_mortgage_enum_remains_display_compatible(monkeypatch):
    body = render_notification(monkeypatch, {"mortgage_balance": "250k_500k"}).html_content
    assert "$250,000–$499,999" in body


def test_homeowner_and_product_rows_are_absent(monkeypatch):
    body = render_notification(monkeypatch).html_content
    assert "Homeowner" not in body
    assert ">Product<" not in body


def test_legacy_default_fields_are_absent(monkeypatch):
    body = render_notification(monkeypatch).html_content
    for field in ("Book Appointment", "Contact Pref", "Home Phone", "Has Beneficiary", "Beneficiary Rel.", "Reason"):
        assert field not in body


def test_malicious_html_in_consumer_field_is_escaped(monkeypatch):
    body = render_notification(monkeypatch, {"first_name": "<script>alert(1)</script>", "code_word": "Falcon<b>bad</b>"}).html_content
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<b>bad</b>" not in body


def test_email_does_not_assert_consent_was_captured(monkeypatch):
    body = render_notification(monkeypatch).html_content
    assert ">Consent<" not in body and ">Captured<" not in body


def test_dashboard_link_is_present(monkeypatch):
    assert "https://protect-mortgage.com/admin" in render_notification(monkeypatch).html_content
