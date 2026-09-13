"""Tests for existing server-backed recoverable Google Ads conversion authorization.

The measurement mechanism is intentionally unchanged by the WS30 minimal intake update.
Only the superseded Home Ownership eligibility assertion is replaced with a compatibility
assertion proving the submission succeeds without Home Ownership.
"""
import concurrent.futures
import os
import subprocess
import sys

from app import app as flask_app
from conftest import (
    BACKEND_DIR,
    MORTGAGE_THANK_YOU_PATH,
    count_leads,
    expire_token,
    fetch_claimed_at,
    fetch_lead_row_by_token,
)
from migrate_conversion_token import run_migration as run_conversion_token_migration


def valid_payload(**overrides):
    payload = {
        "first_name": "Jane", "last_name": "Doe", "phone": "5551234567",
        "email": "jane@example.com", "zip": "90210", "age": "35", "sex": "female",
        "mortgage_balance": "100000-200000", "tobacco_use": "no", "code_word": "sunflower",
        "gclid": "test-gclid-123", "gbraid": "test-gbraid-456", "wbraid": "test-wbraid-789",
        "submitted_url": "https://protect-mortgage.com/?gclid=test-gclid-123",
        "consent_text": "I agree to be contacted by phone, text, and email.",
        "trustedform_cert_url": "", "trustedform_diagnostic": "resolved",
    }
    payload.update(overrides)
    return payload


def submit(client, **overrides):
    return client.post("/submit-mortgage-protection", json=valid_payload(**overrides))


def claim(client, token):
    return client.post("/claim-conversion", json={"token": token})


def test_successful_submission_persists_lead_and_returns_token(client):
    resp = submit(client)
    assert resp.status_code == 200
    body = resp.get_json(); assert body["status"] == "ok"
    token = body["conversion_token"]; assert token
    row = fetch_lead_row_by_token(token); assert row is not None
    lead_id, gclid, gbraid, wbraid, retain_response, claimed_at, expires_at = row
    assert gclid == "test-gclid-123" and gbraid == "test-gbraid-456" and wbraid == "test-wbraid-789"
    assert "client_diagnostic" in retain_response and "resolved" in retain_response
    assert claimed_at is None and expires_at is not None


def test_first_claim_is_atomic_and_returns_a_transaction_id(client):
    token = submit(client).get_json()["conversion_token"]
    resp = claim(client, token); assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok" and resp.get_json()["transaction_id"]
    assert fetch_claimed_at(token) is not None


def test_repeat_claim_of_valid_token_returns_the_same_transaction_id(client):
    token = submit(client).get_json()["conversion_token"]
    results = [claim(client, token) for _ in range(3)]
    assert all(r.status_code == 200 for r in results)
    assert len({r.get_json()["transaction_id"] for r in results}) == 1


def test_refresh_of_thank_you_page_recovers_the_same_transaction_id(client):
    token = submit(client).get_json()["conversion_token"]
    first, refresh = claim(client, token), claim(client, token)
    assert first.status_code == refresh.status_code == 200
    assert first.get_json()["transaction_id"] == refresh.get_json()["transaction_id"]


def test_back_then_forward_navigation_recovers_the_same_transaction_id(client):
    token = submit(client).get_json()["conversion_token"]
    first, second = claim(client, token), claim(client, token)
    assert first.status_code == second.status_code == 200
    assert first.get_json()["transaction_id"] == second.get_json()["transaction_id"]


def test_arbitrary_token_is_rejected(client):
    resp = claim(client, "this-token-was-never-issued-by-the-server")
    assert resp.status_code == 400 and resp.get_json()["status"] == "error"


def test_missing_token_is_rejected(client):
    resp = client.post("/claim-conversion", json={})
    assert resp.status_code == 400 and resp.get_json()["status"] == "error"


def test_expired_token_is_rejected(client):
    token = submit(client).get_json()["conversion_token"]; expire_token(token)
    resp = claim(client, token)
    assert resp.status_code == 400 and resp.get_json()["status"] == "error"
    assert fetch_claimed_at(token) is None


def test_expired_token_is_rejected_even_if_claimed_before_expiry(client):
    token = submit(client).get_json()["conversion_token"]
    assert claim(client, token).status_code == 200
    expire_token(token)
    assert claim(client, token).status_code == 400


def test_concurrent_duplicate_claims_resolve_to_one_state_transition(client):
    token = submit(client).get_json()["conversion_token"]
    def attempt_claim(_):
        return flask_app.test_client().post("/claim-conversion", json={"token": token})
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt_claim, range(10)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.get_json()["transaction_id"] for r in results}) == 1
    assert fetch_claimed_at(token) is not None


def test_validation_failure_has_no_conversion_token(client):
    resp = submit(client, first_name="")
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error" and "conversion_token" not in resp.get_json()
    assert count_leads() == 0


def test_submission_no_longer_requires_homeowner_and_still_mints_conversion_token(client):
    resp = submit(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok" and body["conversion_token"]
    assert count_leads() == 1


def test_legacy_homeowner_value_is_ignored_not_used_for_decline(client):
    resp = submit(client, homeowner="no")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert resp.get_json()["conversion_token"]
    assert count_leads() == 1


def test_declined_outside_zip_allowlist_has_no_conversion_token(client):
    resp = submit(client, zip="10001")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "declined" and "conversion_token" not in body
    assert count_leads() == 0


CORRECT_LABEL = "AW-18193879267/jLl8CIfe39wcEOOhwuND"
INCORRECT_LABEL = "AW-18193879267/jL18CIfe39wcEOOhwuND"


def _read_thank_you_html():
    with open(MORTGAGE_THANK_YOU_PATH, "r", encoding="utf-8") as f: return f.read()


def test_correct_send_to_label_occurs_exactly_once():
    assert _read_thank_you_html().count(CORRECT_LABEL) == 1


def test_incorrect_digit_one_label_occurs_zero_times():
    assert _read_thank_you_html().count(INCORRECT_LABEL) == 0


def test_lowercase_l_in_label_is_u_plus_006c():
    third_char = CORRECT_LABEL.split("/")[1][2]
    assert third_char == "l" and ord(third_char) == 0x6C == 108
    assert third_char != "1" and ord(third_char) != 0x31


def test_migration_function_is_idempotent():
    run_conversion_token_migration(); run_conversion_token_migration()


def test_migration_script_exits_zero_on_success():
    result = subprocess.run([sys.executable, "migrate_conversion_token.py"], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_migration_script_exits_nonzero_on_failure():
    env = {"DB_HOST":"127.0.0.1","DB_PORT":"1","DB_NAME":"bfg_test","DB_USER":"bfg_test","DB_PASSWORD":"bfg_test","PATH":os.environ.get("PATH","")}
    result = subprocess.run([sys.executable, "migrate_conversion_token.py"], cwd=BACKEND_DIR, capture_output=True, text=True, env=env, timeout=30)
    assert result.returncode != 0
    assert "failed" in result.stderr.lower()
