"""Targeted acceptance tests for the Sep. 13 minimal Mortgage Protection intake update."""
import inspect
import os
import re

import app as app_module
from db import get_connection


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FORM_PATH = os.path.join(REPO_ROOT, "protect_mortgage.html")
THANK_YOU_PATH = os.path.join(REPO_ROOT, "mortgage_thank_you.html")
PRIVACY_PATH = os.path.join(REPO_ROOT, "privacy.html")
TERMS_PATH = os.path.join(REPO_ROOT, "terms.html")
DASHBOARD_PATH = os.path.join(REPO_ROOT, "backend", "templates", "dashboard.html")


def read_form():
    with open(FORM_PATH, "r", encoding="utf-8") as f:
        return f.read()


def read_thank_you():
    with open(THANK_YOU_PATH, "r", encoding="utf-8") as f:
        return f.read()


def read_legal_pages():
    with open(PRIVACY_PATH, "r", encoding="utf-8") as privacy_file:
        privacy = privacy_file.read()
    with open(TERMS_PATH, "r", encoding="utf-8") as terms_file:
        terms = terms_file.read()
    return privacy, terms


def test_exact_headline_cta_and_primary_branding():
    html = read_form()
    assert "Request Your Mortgage Protection Quote" in html
    assert "Request My Mortgage Protection Quote" in html
    assert "BFG Insurance Solutions" in html
    assert "Takes under 2 minutes" not in html
    assert "Get My Free Quote" not in html


def test_removed_consumer_fields_and_personal_producer_branding_are_absent():
    html = read_form()
    for removed in (
        'name="homeowner"',
        "Home Ownership",
        "Do you currently own your home?",
        "Date of Birth",
        'name="dob"',
        "Preferred Contact Method",
        "Best Time to Contact",
        "NPN ",
        "CA Lic.",
    ):
        assert removed not in html
    assert "personal producer branding" not in html.lower()


def test_desktop_field_order_matches_approved_rows():
    html = read_form()
    markers = [
        'for="first_name"', 'for="last_name"',
        '>Gender <', 'for="age"',
        'for="phone"', 'for="email"',
        'for="zip"', 'for="mortgage_balance"',
        '>Tobacco Use <', 'for="code_word"',
    ]
    positions = [html.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_gender_and_tobacco_are_radio_controls():
    html = read_form()
    assert 'type="radio" name="gender" value="male"' in html
    assert 'type="radio" name="gender" value="female"' in html
    assert 'type="radio" name="tobacco_use" value="yes"' in html
    assert 'type="radio" name="tobacco_use" value="no"' in html
    # Compatibility map preserves current backend field without DB rename.
    assert '<input type="hidden" id="sex" name="sex"/>' in html
    assert "if (name === 'gender') document.getElementById('sex').value = this.value;" in html


def test_approved_mortgage_bands_are_exact_and_non_overlapping():
    html = read_form()
    expected = {
        "under_100k": "Under $100,000",
        "100k_249999": "$100,000&ndash;$249,999",
        "250k_499999": "$250,000&ndash;$499,999",
        "500k_749999": "$500,000&ndash;$749,999",
        "750k_plus": "$750,000 or more",
    }
    for value, label in expected.items():
        assert f'value="{value}">{label}</option>' in html


def test_code_word_copy_and_trustedform_sensitive_masking():
    html = read_form()
    helper = (
        "Choose a word your BFG Insurance Solutions agent will say first when contacting you "
        "so you can verify the call is genuinely from BFG. Use 3&ndash;20 letters."
    )
    assert helper in html
    assert "We'll never ask you for it" not in html
    assert "We&rsquo;ll never ask you for it" not in html
    code_tag = re.search(r'<input[^>]+id="code_word"[^>]*>', html, re.DOTALL)
    assert code_tag
    assert 'data-tf-sensitive="true"' in code_tag.group(0)
    assert "required" not in code_tag.group(0)
    assert "(optional)" in html


def test_consent_is_fixed_visible_bfg_text_not_scroll_box():
    html = read_form()
    css = re.search(r"\.consent-box\s*\{([^}]*)\}", html, re.DOTALL)
    assert css
    rules = css.group(1)
    assert "max-height" not in rules
    assert "overflow-y" not in rules
    assert "BFG Insurance Solutions" in html
    for removed in ("artificial voice", "prerecorded voice", "artificial intelligence voice"):
        assert removed not in html.lower()


def test_measurement_is_disabled_and_trustedform_is_preserved_on_form():
    html = read_form()
    assert "googletagmanager.com" not in html
    assert "gtag(" not in html
    assert "api.trustedform.com/trustedform.js?field=xxTrustedFormCertUrl&use_tagged_consent=true" in html
    assert "xxTrustedFormCertUrl" in html
    assert "MP_CLICK_ID_STORAGE_KEYS" in html
    assert "gclid" in html and "gbraid" in html and "wbraid" in html


def test_backend_homeowner_is_not_required_validated_declined_or_persisted():
    source = inspect.getsource(app_module.submit_mortgage_protection)
    assert "homeowner" not in source.lower()


def test_submission_without_homeowner_persists_gender_and_leaves_legacy_column_null(client):
    payload = {
        "first_name": "Jane",
        "last_name": "Doe",
        "phone": "5551234567",
        "email": "jane@example.com",
        "zip": "90210",
        "age": "35",
        "sex": "female",
        "mortgage_balance": "250k_499999",
        "tobacco_use": "no",
        "code_word": "Sunflower",
        "gclid": "minimal-test-gclid",
        "submitted_url": "https://protect-mortgage.com/",
        "consent": True,
        "consent_text": "BFG consent test",
        "trustedform_cert_url": "https://cert.trustedform.com/generic-certificate",
        "trustedform_diagnostic": "resolved",
    }
    resp = client.post("/submit-mortgage-protection", json=payload)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT gender, homeowner, mortgage_balance FROM leads WHERE conversion_token = %s",
        (body["conversion_token"],),
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    assert row == ("female", None, "250k_499999")


def test_thank_you_visible_copy_and_existing_conversion_mechanism():
    html = read_thank_you()
    assert "BFG Insurance Solutions" in html
    assert "Thank you. We received your request for a free quote!" in html
    assert "Before any contact" in html
    assert "state and license controls" in html
    assert "Code Word" in html
    assert "call or text" in html
    assert "Submitting this request does not guarantee eligibility, approval, price, policy issuance, or coverage." in html
    assert "will call you shortly" not in html
    assert "fetch('/claim-conversion'" not in html
    assert "send_to" not in html
    assert "gtag(" not in html


def test_privacy_and_terms_use_entity_first_bfg_disclosure():
    privacy, terms = read_legal_pages()
    for html in (privacy, terms):
        assert "BFG Insurance Solutions" in html
        assert "Centaurus Enterprises LLC" in html
        assert "California Organization Producer License #6020392" in html
        assert "john.brown@bfginsurancesolutions.com" in html


def test_privacy_and_terms_contain_no_personal_era_identity_or_contact_details():
    privacy, terms = read_legal_pages()
    combined = privacy + terms
    for removed in (
        "John M. Brown",
        "Joshua Brown",
        "Joshua S. Brown",
        "NPN ",
        "CA Lic. #4374779",
        "CA Lic. #4509549",
        "537 Linda Ln",
        "john.brown@centaurusenterprises.com",
        "(619) 905-7488",
        "619-432-2727",
    ):
        assert removed not in combined


def test_dashboard_does_not_equate_evidence_retention_with_contact_clearance():
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as dashboard_file:
        dashboard = dashboard_file.read()
    assert "Retained — callable" not in dashboard
    assert "Evidence hold — do not contact" in dashboard
    assert "Evidence retained — contact control still applies" in dashboard
    assert "CLEARED_TO_CONTACT" in dashboard
