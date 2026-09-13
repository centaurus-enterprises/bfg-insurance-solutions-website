"""Targeted acceptance tests for the Sep. 13 minimal Mortgage Protection intake update."""
import os
from db import get_connection

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FORM_PATH = os.path.join(REPO_ROOT, "protect_mortgage.html")
THANK_YOU_PATH = os.path.join(REPO_ROOT, "mortgage_thank_you.html")


def form_html():
    return open(FORM_PATH, encoding="utf-8").read()


def thank_you_html():
    return open(THANK_YOU_PATH, encoding="utf-8").read()


def payload(**overrides):
    d = {
        "first_name":"Jane", "last_name":"Doe", "phone":"5551234567",
        "email":"jane@example.com", "zip":"90210", "age":"35", "sex":"female",
        "mortgage_balance":"250k_499999", "tobacco_use":"no", "code_word":"Sunshine",
        "gclid":"g-test", "gbraid":"", "wbraid":"",
        "submitted_url":"https://protect-mortgage.com/?gclid=g-test",
        "consent_text":"test consent", "trustedform_cert_url":"", "trustedform_diagnostic":"resolved",
    }
    d.update(overrides)
    return d


def test_primary_brand_headline_and_cta_are_exact():
    h=form_html()
    assert "BFG Insurance Solutions" in h
    assert "Request Your Mortgage Protection Quote" in h
    assert "Request My Mortgage Protection Quote" in h
    assert "Takes under 2 minutes" not in h


def test_personal_producer_identity_is_absent_from_intake():
    h=form_html()
    for forbidden in ("John M. Brown", "Joshua Brown", "21148038", "22098686", "4374779", "4509549"):
        assert forbidden not in h


def test_removed_consumer_fields_are_absent():
    h=form_html().lower()
    assert "homeowner" not in h and "home ownership" not in h and "own your home" not in h
    assert 'name="dob"' not in h and "preferred contact" not in h and "best time" not in h


def test_gender_is_male_female_radio_and_tobacco_is_yes_no_radio():
    h=form_html()
    assert 'type="radio" name="gender" value="male"' in h
    assert 'type="radio" name="gender" value="female"' in h
    assert 'type="radio" name="tobacco_use" value="yes"' in h
    assert 'type="radio" name="tobacco_use" value="no"' in h


def test_approved_mortgage_bands_are_present():
    h=form_html()
    expected = {
        "under_100k":"Under $100,000",
        "100k_249999":"$100,000–$249,999",
        "250k_499999":"$250,000–$499,999",
        "500k_749999":"$500,000–$749,999",
        "750k_plus":"$750,000 or more",
    }
    for value,label in expected.items():
        assert f'value="{value}"' in h and label in h


def test_code_word_required_helper_and_trustedform_sensitive_masking():
    h=form_html()
    assert 'id="code_word"' in h and 'data-tf-sensitive="true"' in h
    assert "Choose a word your BFG Insurance Solutions agent will say first" in h
    assert "Use 3–20 letters" in h
    assert "We'll never ask you for it" not in h


def test_consent_is_fixed_normal_flow_and_bfg_branded():
    h=form_html()
    assert 'class="consent-text"' in h
    assert 'class="consent-box"' not in h
    assert "Centaurus Enterprises LLC d/b/a BFG Insurance Solutions" in h
    for obsolete in ("artificial voice", "prerecorded voice", "AI voice"):
        assert obsolete.lower() not in h.lower()


def test_existing_google_click_id_and_trustedform_mechanics_remain_present():
    h=form_html()
    assert "AW-18193879267" in h
    assert 'id="gclid"' in h and 'id="gbraid"' in h and 'id="wbraid"' in h
    assert "MP_CLICK_ID_STORAGE_KEYS" in h and "window.sessionStorage" in h
    assert "api.trustedform.com/trustedform.js?field=xxTrustedFormCertUrl&use_tagged_consent=true" in h
    assert "fetch('/submit-mortgage-protection'" in h


def test_backend_accepts_submission_without_homeowner_and_stores_gender(client):
    r=client.post('/submit-mortgage-protection', json=payload())
    assert r.status_code==200 and r.get_json()['status']=='ok'
    c=get_connection();q=c.cursor();q.execute("SELECT gender, homeowner, mortgage_balance, code_word FROM leads ORDER BY id DESC LIMIT 1");row=q.fetchone();q.close();c.close()
    assert row[0]=='female'
    assert row[1] is None
    assert row[2]=='250k_499999'
    assert row[3]=='Sunshine'


def test_backend_ignores_legacy_homeowner_no_instead_of_declining(client):
    r=client.post('/submit-mortgage-protection', json=payload(homeowner='no'))
    assert r.status_code==200 and r.get_json()['status']=='ok'


def test_tobacco_and_code_word_remain_required(client):
    r=client.post('/submit-mortgage-protection', json=payload(tobacco_use=''))
    assert r.status_code==400 and r.get_json()['field']=='tobacco_use'
    r=client.post('/submit-mortgage-protection', json=payload(code_word=''))
    assert r.status_code==400 and r.get_json()['field']=='code_word'


def test_thank_you_visible_presentation_updated_without_changing_conversion_label():
    h=thank_you_html()
    assert "John M. Brown" in h and "BFG Insurance Solutions" in h
    assert "call you shortly" not in h.lower()
    assert h.count("AW-18193879267/jLl8CIfe39wcEOOhwuND") == 1
    assert "fetch('/claim-conversion'" in h
