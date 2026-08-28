"""
Tests for server-backed exactly-once (recoverable) Google Ads conversion
authorization on the protect-mortgage.com funnel
(/submit-mortgage-protection + /claim-conversion), plus the standalone
migration script and the on-page conversion label itself.

Covers: the first atomic claim, a repeat claim returning the same
transaction_id, arbitrary/missing/expired token rejection, concurrent
requests resolving to one underlying state transition, simulated refresh
and Back/Forward recovery, failed/declined submissions never minting a
token, the exact send_to label appearing exactly once (and the known-bad
label appearing zero times) at the correct Unicode code point, and that
the migration script is idempotent.
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


# ── First atomic claim ───────────────────────────────────────────────────

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

    # item 9 (original PR): gclid/gbraid/wbraid and TrustedForm diagnostics preserved
    assert gclid == "test-gclid-123"
    assert gbraid == "test-gbraid-456"
    assert wbraid == "test-wbraid-789"
    assert "client_diagnostic" in retain_response
    assert "resolved" in retain_response

    assert claimed_at is None
    assert expires_at is not None


def test_first_claim_is_atomic_and_returns_a_transaction_id(client):
    token = submit(client).get_json()["conversion_token"]

    resp = claim(client, token)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["transaction_id"]

    assert fetch_claimed_at(token) is not None


# ── Repeat claim recovery: same transaction_id, not a rejection ─────────

def test_repeat_claim_of_valid_token_returns_the_same_transaction_id(client):
    token = submit(client).get_json()["conversion_token"]

    first = claim(client, token)
    second = claim(client, token)
    third = claim(client, token)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    tx_ids = {r.get_json()["transaction_id"] for r in (first, second, third)}
    assert len(tx_ids) == 1, "every claim of the same valid token must return the same transaction_id"


def test_refresh_of_thank_you_page_recovers_the_same_transaction_id(client):
    """A refresh re-runs the page script, which calls /claim-conversion
    again with the same ?ct= token -- this must succeed and hand back the
    same transaction_id so a dropped gtag hit can be retried."""
    token = submit(client).get_json()["conversion_token"]

    first_page_load = claim(client, token)
    refresh = claim(client, token)

    assert first_page_load.status_code == 200
    assert refresh.status_code == 200
    assert first_page_load.get_json()["transaction_id"] == refresh.get_json()["transaction_id"]


def test_back_then_forward_navigation_recovers_the_same_transaction_id(client):
    """Back/Forward returns the browser to the same thank-you URL (same
    ?ct= token) and re-runs its script later -- same recovery guarantee
    as a refresh."""
    token = submit(client).get_json()["conversion_token"]

    original_visit = claim(client, token)
    navigated_away_then_back = claim(client, token)

    assert original_visit.status_code == 200
    assert navigated_away_then_back.status_code == 200
    assert original_visit.get_json()["transaction_id"] == navigated_away_then_back.get_json()["transaction_id"]


# ── Arbitrary / missing / expired token rejection ────────────────────────

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


def test_expired_token_is_rejected_even_if_claimed_before_expiry(client):
    """Expiry must win over a prior successful claim -- a token doesn't
    become eligible for recovery forever just because it was claimed once
    while still valid."""
    token = submit(client).get_json()["conversion_token"]
    assert claim(client, token).status_code == 200  # claimed while still valid

    expire_token(token)

    resp = claim(client, token)
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


# ── Concurrent requests: exactly one underlying state transition ────────

def test_concurrent_duplicate_claims_resolve_to_one_state_transition(client):
    token = submit(client).get_json()["conversion_token"]

    def attempt_claim(_):
        # Each call gets its own test client / DB connection: a real
        # concurrent hit on the same row, not a single serialized call.
        return flask_app.test_client().post("/claim-conversion", json={"token": token})

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt_claim, range(10)))

    # Every concurrent request must succeed now (recovery semantics)...
    assert all(r.status_code == 200 for r in results)
    # ...and all of them must agree on exactly one transaction_id, which is
    # only possible if the NULL -> claimed transition happened once and
    # every other racer saw the already-claimed value rather than
    # independently "winning" its own claim.
    tx_ids = {r.get_json()["transaction_id"] for r in results}
    assert len(tx_ids) == 1
    assert fetch_claimed_at(token) is not None


# ── Failed submissions never receive a valid conversion token ───────────

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


# ── The on-page conversion label itself ──────────────────────────────────

CORRECT_LABEL = "AW-18193879267/jLl8CIfe39wcEOOhwuND"
INCORRECT_LABEL = "AW-18193879267/jL18CIfe39wcEOOhwuND"


def _read_thank_you_html():
    with open(MORTGAGE_THANK_YOU_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_correct_send_to_label_occurs_exactly_once():
    html = _read_thank_you_html()
    assert html.count(CORRECT_LABEL) == 1


def test_incorrect_digit_one_label_occurs_zero_times():
    html = _read_thank_you_html()
    assert html.count(INCORRECT_LABEL) == 0


def test_lowercase_l_in_label_is_u_plus_006c():
    # Isolate the label's 3rd character programmatically -- never eyeball it.
    suffix = CORRECT_LABEL.split("/")[1]  # "jLl8CIfe39wcEOOhwuND"
    third_char = suffix[2]
    assert third_char == "l"
    assert ord(third_char) == 0x6C == 108
    # And explicitly rule out the visually similar digit "1" (U+0031 / 49).
    assert third_char != "1"
    assert ord(third_char) != 0x31


# ── Migration idempotency ────────────────────────────────────────────────

def test_migration_function_is_idempotent():
    # The session-scoped fixture already ran this once; running it two
    # more times back-to-back must not raise (every statement is
    # IF NOT EXISTS / CREATE ... IF NOT EXISTS).
    run_conversion_token_migration()
    run_conversion_token_migration()


def test_migration_script_exits_zero_on_success():
    result = subprocess.run(
        [sys.executable, "migrate_conversion_token.py"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_migration_script_exits_nonzero_on_failure():
    env = {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "1",  # nothing listens here -- connection must fail
        "DB_NAME": "bfg_test",
        "DB_USER": "bfg_test",
        "DB_PASSWORD": "bfg_test",
        "PATH": os.environ.get("PATH", ""),
    }
    result = subprocess.run(
        [sys.executable, "migrate_conversion_token.py"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode != 0
    assert "failed" in result.stderr.lower()
