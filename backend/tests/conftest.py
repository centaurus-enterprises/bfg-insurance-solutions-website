"""
Shared pytest fixtures for the mortgage-protection conversion-tracking
tests. Runs against a real Postgres database (matching this repo's own
"verified against real Postgres" convention) rather than mocks, so the
atomic-claim SQL is actually exercised.

Point these env vars at a scratch database before running pytest, e.g.:

    export DB_HOST=localhost DB_PORT=5432 DB_NAME=bfg_test \
           DB_USER=bfg_test DB_PASSWORD=bfg_test
    cd backend && pytest tests -v
"""
import os
import sys

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "bfg_test")
os.environ.setdefault("DB_USER", "bfg_test")
os.environ.setdefault("DB_PASSWORD", "bfg_test")

# Never let a real DATABASE_URL (e.g. someone's Render env leaking into a
# local shell) redirect tests at a live database.
os.environ.pop("DATABASE_URL", None)

# These are intentionally left unset: with no SendGrid/TrustedForm
# credentials configured, both send_lead_notification() and
# mp_retain_trustedform_certificate() take their documented no-network-call
# early-return paths, so tests exercise real code without needing live
# third-party credentials or mocks.
os.environ.pop("SENDGRID_API_KEY", None)
os.environ.pop("MAIL_SENDER", None)
os.environ.pop("TRUSTEDFORM_API_KEY", None)
os.environ.pop("MAINTENANCE_MODE", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from app import app as flask_app  # noqa: E402
from db import get_connection  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate_schema():
    """Ensure leads/agents tables and the conversion-token columns exist."""
    c = flask_app.test_client()
    init_resp = c.get("/run-migration-init-h4v9t")
    assert init_resp.status_code == 200, init_resp.data
    conv_resp = c.get("/run-migration-conv-tok-x7q2m")
    assert conv_resp.status_code == 200, conv_resp.data
    yield


@pytest.fixture(autouse=True)
def _clean_leads():
    """Isolate each test: start every test with an empty leads table."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE leads RESTART IDENTITY")
    conn.commit()
    cur.close()
    conn.close()
    yield


@pytest.fixture
def client():
    flask_app.testing = True
    return flask_app.test_client()


def fetch_lead_row_by_token(token):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, gclid, gbraid, wbraid, trustedform_retain_response,
               conversion_claimed_at, conversion_token_expires_at
        FROM leads WHERE conversion_token = %s
        """,
        (token,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def fetch_claimed_at(token):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT conversion_claimed_at FROM leads WHERE conversion_token = %s", (token,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def count_leads():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM leads")
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    return n


def expire_token(token):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE leads SET conversion_token_expires_at = NOW() - INTERVAL '1 hour' WHERE conversion_token = %s",
        (token,),
    )
    conn.commit()
    cur.close()
    conn.close()
