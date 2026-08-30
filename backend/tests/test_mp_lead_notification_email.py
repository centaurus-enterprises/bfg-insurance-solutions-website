"""
Regression coverage for the Mortgage Protection lead-notification email
(send_mortgage_protection_lead_notification in app.py).

Exercises the function directly with SendGrid and the agent-recipient
lookup mocked out -- no real email is ever sent and no real DB connection
is required for these tests. Uses the known representative fixture (John
Brown / Falcon / etc.) from the acceptance test that originally exposed
the legacy-field/branding/timezone bugs this function fixes.
"""
from datetime import datetime, timezone

import app as app_module


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *a, **k):
        pass

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return FakeCursor(self._rows)

    def commit(self):
        pass

    def close(self):
        pass


class FakeMail:
    """Stand-in for sendgrid.helpers.mail.Mail that just records its args."""

    def __init__(self, from_email=None, to_emails=None, subject=None, html_content=None):
        self.from_email = from_email
        self.to_emails = to_emails
        self.subject = subject
        self.html_content = html_content


class FakeSendGridClient:
    """Stand-in for sendgrid.SendGridAPIClient. Records every message it
    would have sent instead of making a network call."""

    sent = []

    def __init__(self, api_key=None):
        self.api_key = api_key

    def send(self, message):
        FakeSendGridClient.sent.append(message)


def render_notification(monkeypatch, lead_overrides=None):
    """Configures env/mocks, calls send_mortgage_protection_lead_notification
    with the representative fixture (plus any overrides), and returns the
    single captured outbound message."""
    monkeypatch.setenv("SENDGRID_API_KEY", "test-key")
    monkeypatch.setenv("MAIL_SENDER", "josh@thebrownfinancialgroup.com")

    monkeypatch.setattr(
        app_module, "get_connection",
        lambda: FakeConnection([("agent@example.com", "Agent One")])
    )

    FakeSendGridClient.sent = []
    monkeypatch.setattr("sendgrid.SendGridAPIClient", FakeSendGridClient)
    monkeypatch.setattr("sendgrid.helpers.mail.Mail", FakeMail)

    lead = {
        "first_name": "John",
        "last_name": "Brown",
        "code_word": "Falcon",
        "phone_display": "(619) 432-2727",
        "email": "jb_51_99@yahoo.com",
        "zip": "91910",
        "age": 53,
        "sex": "male",
        "homeowner": "yes",
        "tobacco_use": "no",
        "mortgage_balance": "250k_500k",
        "submitted_at_utc": datetime(2026, 8, 28, 18, 58, tzinfo=timezone.utc),
    }
    if lead_overrides:
        lead.update(lead_overrides)

    app_module.send_mortgage_protection_lead_notification(lead)

    assert len(FakeSendGridClient.sent) == 1, "expected exactly one outbound message"
    return FakeSendGridClient.sent[0]


def test_subject_uses_first_and_last_name(monkeypatch):
    message = render_notification(monkeypatch)
    assert message.subject == "New Lead: John Brown — Mortgage Protection"


def test_subject_strips_control_characters(monkeypatch):
    message = render_notification(monkeypatch, lead_overrides={
        "first_name": "John\r\nBcc: bad@example.com",
        "last_name": "Brown\t",
    })
    assert "\r" not in message.subject
    assert "\n" not in message.subject
    assert "\t" not in message.subject
    assert message.subject == (
        "New Lead: John Bcc: bad@example.com Brown — Mortgage Protection"
    )


def test_brand_is_bfg_insurance_solutions(monkeypatch):
    message = render_notification(monkeypatch)
    body = message.html_content
    assert "BFG" in body and "Insurance Solutions" in body


def test_code_word_is_present(monkeypatch):
    message = render_notification(monkeypatch)
    assert "Falcon" in message.html_content


def test_zip_is_present(monkeypatch):
    message = render_notification(monkeypatch)
    assert "91910" in message.html_content


def test_age_is_present(monkeypatch):
    message = render_notification(monkeypatch)
    assert ">53<" in message.html_content


def test_sex_is_present_as_male(monkeypatch):
    message = render_notification(monkeypatch)
    assert ">Male<" in message.html_content


def test_homeowner_is_present_as_yes(monkeypatch):
    message = render_notification(monkeypatch)
    body = message.html_content
    assert "Homeowner" in body
    assert ">Yes<" in body


def test_tobacco_is_present_as_no(monkeypatch):
    message = render_notification(monkeypatch)
    body = message.html_content
    assert "Tobacco" in body
    assert ">No<" in body


def test_mortgage_balance_enum_is_displayed_human_readable(monkeypatch):
    message = render_notification(monkeypatch)
    body = message.html_content
    assert "$250,000 – $500,000" in body
    assert "250k_500k" not in body


def test_phone_and_email_are_present(monkeypatch):
    message = render_notification(monkeypatch)
    body = message.html_content
    assert "(619) 432-2727" in body
    assert "jb_51_99@yahoo.com" in body


def test_legacy_and_default_fields_are_absent(monkeypatch):
    message = render_notification(monkeypatch)
    body = message.html_content
    for legacy_field in (
        "Book Appointment",
        "Contact Pref",
        "Home Phone",
        "Has Beneficiary",
        "Beneficiary Rel.",
        "Reason",
    ):
        assert legacy_field not in body


def test_utc_timestamp_converts_to_pacific_with_dst_label(monkeypatch):
    message = render_notification(monkeypatch)
    assert "Aug 28, 2026 · 11:58 AM PDT" in message.html_content


def test_malicious_html_in_consumer_field_is_escaped(monkeypatch):
    message = render_notification(monkeypatch, lead_overrides={
        "first_name": "<script>alert(1)</script>",
        "code_word": "Fal\"con<b>onload=alert(1)</b>",
    })
    body = message.html_content
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<b>onload=alert(1)</b>" not in body


def test_email_does_not_assert_consent_was_captured(monkeypatch):
    message = render_notification(monkeypatch)
    body = message.html_content
    assert ">Consent<" not in body
    assert ">Captured<" not in body


def test_dashboard_link_is_present(monkeypatch):
    message = render_notification(monkeypatch)
    assert "https://protect-mortgage.com/admin" in message.html_content
