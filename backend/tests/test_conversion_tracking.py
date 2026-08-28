"""
Tests for server-backed exactly-once Google Ads conversion authorization
on the protect-mortgage.com funnel (/submit-mortgage-protection +
/claim-conversion).

Covers: successful submission, an arbitrary token, a reused token, a
simulated refresh, simulated Back/Forward navigation, failed/declined
submissions, concurrent duplicate claims, and that GCLID/GBRAID/WBRAID and
TrustedForm diagnostics still make it onto the lead record untouched.
"""
import concurrent.futures

from app import app as flask_app
from conftest import count_leads, expire_token, fetch_claimed_at, fetch_lead_row_by_token


def valid_payload(**overrides):
    payload = {
        "first_name": "Jane",
        "last_name": "Doe",
        "phone": "5551234567",
        "email": "jane@example.com",
        "zip": "90210",
        "age": "35",
        "sex": "female",
        "mortgage_balance": "100000-200000",
        "homeowner": "yes",
        "tobacco_use": "no",
        "code_word": "sunflower",
        "gclid": "test-gclid-123",
        "gbraid": "test-gbraid-456",
        "wbraid": "test-wbraid-789",
        "submitted_url": "https://protect-mortgage.com/?gclid=test-gclid-123",
        "consent_text": "I agree to be contacted by phone, text, and email.",
        "trustedform_cert_url": "",
        "trustedform_diagnostic": "resolved",
    }
    payload.update(overrides)
    return payload


def submit(client, **overrides):
    return client.post("/submit-mortgage-protection", json=valid_payload(**overrides))


def claim(client, token):
    return client.post("/claim-conversion", json={"token": token})


# ── 1. Successful submission ────────────────────────────────────────────

def test_successful_submission_persists_lead_and_returns_token(client):
    resp = submit(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    token = body["conversion_token"]
    assert token

    row = fetch_lead_row_by_token(token)
    assert row is not None
    lead_id, gclid, gbraid, wbraid, retain_response, claimed_at, expires_at = row

    # item 9: gclid/gbraid/wbraid and TrustedForm diagnostics preserved
    assert gclid == "test-gclid-123"
    assert gbraid == "test-gbraid-456"
    assert wbraid == "test-wbraid-789"
    assert "client_diagnostic" in retain_response
    assert "resolved" in retain_response

    # item 1/3: token is tied to the committed lead, unclaimed, with an
    # expiry set
    assert claimed_at is None
    assert expires_at is not None


def test_claiming_a_valid_token_returns_a_transaction_id_and_marks_it_claimed(client):
    token = submit(client).get_json()["conversion_token"]

    resp = claim(client, token)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["transaction_id"]  # item 4: unique lead/transaction id returned

    assert fetch_claimed_at(token) is not None  # item 3: claim recorded atomically


# ── 2. Reject arbitrary / missing / expired / previously-claimed tokens ──

def test_arbitrary_token_is_rejected(client):
    resp = claim(client, "this-token-was-never-issued-by-the-server")
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_missing_token_is_rejected(client):
    resp = client.post("/claim-conversion", json={})
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_expired_token_is_rejected(client):
    token = submit(client).get_json()["conversion_token"]
    expire_token(token)

    resp = claim(client, token)
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"
    assert fetch_claimed_at(token) is None


def test_reused_token_is_rejected_on_second_claim(client):
    token = submit(client).get_json()["conversion_token"]

    first = claim(client, token)
    second = claim(client, token)

    assert first.status_code == 200
    assert first.get_json()["status"] == "ok"
    assert second.status_code == 400
    assert second.get_json()["status"] == "error"


# ── Refresh / Back-Forward: same URL (same ct token) loads a second time ─

def test_refresh_of_thank_you_page_does_not_refire(client):
    """A refresh re-runs the same page script, which calls /claim-conversion
    again with the same ?ct= token."""
    token = submit(client).get_json()["conversion_token"]

    first_page_load = claim(client, token)
    refresh = claim(client, token)

    assert first_page_load.get_json()["status"] == "ok"
    assert refresh.status_code == 400
    assert refresh.get_json()["status"] == "error"


def test_back_then_forward_navigation_does_not_refire(client):
    """Back/Forward returns the browser to the same thank-you URL (same
    ?ct= token) and re-runs its script a second time, later."""
    token = submit(client).get_json()["conversion_token"]

    original_visit = claim(client, token)
    navigated_away_then_back = claim(client, token)

    assert original_visit.get_json()["status"] == "ok"
    assert navigated_away_then_back.status_code == 400
    assert navigated_away_then_back.get_json()["status"] == "error"


# ── 7. Failed submissions never receive a valid conversion token ────────

def test_validation_failure_has_no_conversion_token(client):
    resp = submit(client, first_name="")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["status"] == "error"
    assert "conversion_token" not in body
    assert count_leads() == 0


def test_declined_non_homeowner_has_no_conversion_token(client):
    resp = submit(client, homeowner="no")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "declined"
    assert "conversion_token" not in body
    assert count_leads() == 0


def test_declined_outside_zip_allowlist_has_no_conversion_token(client):
    resp = submit(client, zip="10001")  # NYC zip, outside the CA-only allowlist
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "declined"
    assert "conversion_token" not in body
    assert count_leads() == 0


# ── 8. Concurrent duplicate claims ───────────────────────────────────────

def test_concurrent_duplicate_claims_only_one_succeeds(client):
    token = submit(client).get_json()["conversion_token"]

    def attempt_claim(_):
        # Each call gets its own test client / DB connection, so this is a
        # real concurrent hit on the same row, not a single serialized call.
        return flask_app.test_client().post("/claim-conversion", json={"token": token})

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt_claim, range(10)))

    statuses = [r.get_json()["status"] for r in results]
    assert statuses.count("ok") == 1
    assert statuses.count("error") == 9
    assert fetch_claimed_at(token) is not None
