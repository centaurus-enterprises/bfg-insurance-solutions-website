"""Acceptance coverage for evidence-gated intake and generic conversion authorization."""
import concurrent.futures
import os
import re
import subprocess
import sys

import app as app_module
from app import app as flask_app
from conftest import (
    BACKEND_DIR,
    MORTGAGE_THANK_YOU_PATH,
    count_leads,
    expire_token,
    fetch_claimed_at,
    fetch_lead_row_by_token,
)
from db import get_connection
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
        "mortgage_balance": "100k_249999",
        "tobacco_use": "no",
        "code_word": "sunflower",
        "gclid": "test-gclid-123",
        "gbraid": "test-gbraid-456",
        "wbraid": "test-wbraid-789",
        "submitted_url": "https://protect-mortgage.com/?gclid=test-gclid-123",
        "consent": True,
        "consent_text": "browser text is not authoritative",
        "trustedform_cert_url": "https://cert.trustedform.com/test-certificate",
        "trustedform_diagnostic": "resolved",
    }
    payload.update(overrides)
    return payload


def submit(client, **overrides):
    return client.post("/submit-mortgage-protection", json=valid_payload(**overrides))


def claim(client, token):
    return client.post("/claim-conversion", json={"token": token})


def fetch_processing_state(lead_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT lead_processing_status, evidence_hold_reason, evidence_retry_count,
               evidence_next_retry_at, contact_status, state_derivation_status,
               conversion_token, consent_affirmed, consent_text,
               mortgage_balance, code_word
        FROM leads WHERE id = %s
    """, (lead_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def test_verified_submission_is_accepted_and_mints_token(client):
    resp = submit(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    token = body["conversion_token"]
    row = fetch_lead_row_by_token(token)
    assert row is not None
    _, gclid, gbraid, wbraid, detail, claimed_at, expires_at = row
    assert (gclid, gbraid, wbraid) == (
        "test-gclid-123", "test-gbraid-456", "test-wbraid-789"
    )
    assert '"accepted": true' in detail
    assert claimed_at is None
    assert expires_at is not None


def test_non_california_five_digit_zip_is_received(client):
    resp = submit(client, zip="10001")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert count_leads() == 1


def test_mortgage_balance_and_code_word_are_optional(client):
    resp = submit(client, mortgage_balance="", code_word="")
    assert resp.status_code == 200
    token = resp.get_json()["conversion_token"]
    lead_id = fetch_lead_row_by_token(token)[0]
    state = fetch_processing_state(lead_id)
    assert state[-2:] == (None, None)


def test_optional_fields_validate_when_supplied(client):
    bad_balance = submit(client, mortgage_balance="not-an-approved-band")
    assert bad_balance.status_code == 400
    assert bad_balance.get_json()["field"] == "mortgage_balance"
    bad_code = submit(client, code_word="12")
    assert bad_code.status_code == 400
    assert bad_code.get_json()["field"] == "code_word"
    assert count_leads() == 0


def test_affirmative_consent_is_enforced_server_side(client):
    for value in (False, None, "true", "yes"):
        resp = submit(client, consent=value)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "consent"
    assert count_leads() == 0


def test_server_controlled_consent_text_is_persisted(client):
    resp = submit(client, consent_text="tampered browser copy")
    lead_id = fetch_lead_row_by_token(resp.get_json()["conversion_token"])[0]
    state = fetch_processing_state(lead_id)
    assert state[7] is True
    assert state[8] == app_module.MP_CONSENT_TEXT


def test_evidence_failure_persists_hold_without_notification_or_token(client, monkeypatch):
    sent = []
    monkeypatch.setattr(app_module, "send_mortgage_protection_lead_notification", sent.append)
    monkeypatch.setattr(app_module, "mp_retain_trustedform_certificate", lambda *args: {
        "accepted": False, "retained": True, "match_success": False,
        "outcome": "failure", "reason": "lead mismatch", "retryable": False,
        "status_code": 200,
    })
    resp = submit(client)
    assert resp.status_code == 202
    assert resp.get_json()["status"] == "received"
    assert "conversion_token" not in resp.get_json()
    assert sent == []

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM leads")
    lead_id = cur.fetchone()[0]
    cur.close(); conn.close()
    state = fetch_processing_state(lead_id)
    assert state[0] == "EVIDENCE_HOLD"
    assert state[1] == "lead mismatch"
    assert state[4] == "DO_NOT_CONTACT"
    assert state[6] is None


def test_transport_error_is_held_with_bounded_retry(client, monkeypatch):
    monkeypatch.setattr(app_module, "mp_retain_trustedform_certificate", lambda *args: {
        "accepted": False, "retained": False, "match_success": False,
        "outcome": "error", "reason": "timeout", "retryable": True,
    })
    assert submit(client).status_code == 202
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM leads")
    lead_id = cur.fetchone()[0]
    cur.close(); conn.close()
    state = fetch_processing_state(lead_id)
    assert state[0] == "EVIDENCE_HOLD"
    assert state[2] == 1
    assert state[3] is not None


def test_retry_promotes_once_and_reuses_the_same_token(client, monkeypatch):
    sent = []
    monkeypatch.setattr(app_module, "send_mortgage_protection_lead_notification", sent.append)
    monkeypatch.setattr(app_module, "mp_retain_trustedform_certificate", lambda *args: {
        "accepted": False, "retained": False, "match_success": False,
        "outcome": "error", "reason": "temporary timeout", "retryable": True,
    })
    assert submit(client).status_code == 202
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM leads")
    lead_id = cur.fetchone()[0]
    cur.close(); conn.close()

    monkeypatch.setattr(app_module, "mp_retain_trustedform_certificate", lambda *args: {
        "accepted": True, "retained": True, "match_success": True,
        "outcome": "success", "reason": None, "retryable": False,
        "status_code": 200,
    })
    first = app_module.mp_process_evidence(lead_id)
    repeat = app_module.mp_process_evidence(lead_id)
    assert first["status"] == repeat["status"] == "accepted"
    assert first["conversion_token"] == repeat["conversion_token"]
    assert len(sent) == 1


def test_first_and_repeat_claim_return_same_transaction_id(client):
    token = submit(client).get_json()["conversion_token"]
    responses = [claim(client, token) for _ in range(3)]
    assert all(resp.status_code == 200 for resp in responses)
    assert len({resp.get_json()["transaction_id"] for resp in responses}) == 1
    assert fetch_claimed_at(token) is not None


def test_concurrent_claims_resolve_to_one_state_transition(client):
    token = submit(client).get_json()["conversion_token"]

    def attempt(_):
        return flask_app.test_client().post("/claim-conversion", json={"token": token})

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(attempt, range(10)))
    assert all(resp.status_code == 200 for resp in responses)
    assert len({resp.get_json()["transaction_id"] for resp in responses}) == 1


def test_missing_arbitrary_and_expired_tokens_are_rejected(client):
    assert client.post("/claim-conversion", json={}).status_code == 400
    assert claim(client, "generic-unissued-token").status_code == 400
    token = submit(client).get_json()["conversion_token"]
    expire_token(token)
    assert claim(client, token).status_code == 400


def test_measurement_is_disabled_until_greenfield_configuration_exists():
    html = open(MORTGAGE_THANK_YOU_PATH, encoding="utf-8").read()
    assert "googletagmanager.com" not in html
    assert "gtag(" not in html
    assert "send_to" not in html


def test_active_text_files_contain_no_embedded_ads_destination():
    repo_root = os.path.dirname(BACKEND_DIR)
    pattern = re.compile(r"AW-\d+")
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__"}]
        for name in files:
            if not name.endswith((".py", ".html", ".md", ".js", ".json", ".yml", ".yaml")):
                continue
            path = os.path.join(root, name)
            assert not pattern.search(open(path, encoding="utf-8").read()), path


def test_trustedform_url_requires_exact_https_origin():
    assert app_module.mp_trustedform_url_is_allowed(
        "https://cert.trustedform.com/generic-certificate"
    )
    assert not app_module.mp_trustedform_url_is_allowed(
        "https://cert.trustedform.com.attacker.example/generic-certificate"
    )
    assert not app_module.mp_trustedform_url_is_allowed(
        "https://attacker.example/?next=https://cert.trustedform.com/generic-certificate"
    )
    assert not app_module.mp_trustedform_url_is_allowed(
        "http://cert.trustedform.com/generic-certificate"
    )


def test_trustedform_v4_header_payload_and_success_parsing(monkeypatch):
    class Response:
        status_code = 200
        def json(self):
            return {
                "outcome": "success",
                "retain": {"results": {"previously_retained": False}},
                "match_lead": {"result": {"success": True}},
            }

    captured = {}
    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(app_module, "TRUSTEDFORM_API_KEY", "test-key")
    monkeypatch.setattr(app_module.requests, "post", fake_post)
    result = app_module.mp_retain_trustedform_certificate(
        "https://cert.trustedform.com/generic-certificate", "jane@example.com", "+15551234567"
    )
    assert result["accepted"] is True
    assert captured["headers"]["api-version"] == "4.0"
    assert set(captured["json"]) == {"retain", "match_lead"}
    assert captured["json"]["match_lead"] == {
        "email": "jane@example.com", "phone": "+15551234567"
    }


def test_http_200_with_failure_or_malformed_body_is_not_accepted(monkeypatch):
    class FailureResponse:
        status_code = 200
        def json(self):
            return {"outcome": "failure", "retain": {"results": {"stored": True}},
                    "match_lead": {"result": {"success": False}}}

    monkeypatch.setattr(app_module, "TRUSTEDFORM_API_KEY", "test-key")
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FailureResponse())
    failure = app_module.mp_retain_trustedform_certificate(
        "https://cert.trustedform.com/generic-certificate", "jane@example.com", "+15551234567"
    )
    assert failure["accepted"] is False
    assert failure["retained"] is True
    assert failure["outcome"] == "failure"

    class MalformedResponse:
        status_code = 200
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: MalformedResponse())
    malformed = app_module.mp_retain_trustedform_certificate(
        "https://cert.trustedform.com/generic-certificate", "jane@example.com", "+15551234567"
    )
    assert malformed["accepted"] is False
    assert malformed["outcome"] == "error"


def test_migration_function_and_script_are_idempotent():
    run_conversion_token_migration()
    run_conversion_token_migration()
    result = subprocess.run(
        [sys.executable, "migrate_conversion_token.py"], cwd=BACKEND_DIR,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_migration_script_exits_nonzero_on_failure():
    env = {
        "DB_HOST": "127.0.0.1", "DB_PORT": "1", "DB_NAME": "bfg_test",
        "DB_USER": "bfg_test", "DB_PASSWORD": "bfg_test",
        "PATH": os.environ.get("PATH", ""),
    }
    result = subprocess.run(
        [sys.executable, "migrate_conversion_token.py"], cwd=BACKEND_DIR,
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert result.returncode != 0
    assert "failed" in result.stderr.lower()
