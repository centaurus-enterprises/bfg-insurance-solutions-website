"""Additive Mortgage Protection vNext schema migration.

Designed for branch/staging review first. No destructive legacy changes.
Run directly (or from a later authorized Render pre-deploy command); never expose
this migration as a public HTTP route.
"""
from db import get_connection

ALTER_COLUMNS = [
    # Widen only: legacy VARCHAR(10) cannot hold approved non-overlapping vNext enums.
    "ALTER TABLE leads ALTER COLUMN mortgage_balance TYPE VARCHAR(40)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_uuid UUID",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS submission_id UUID",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS visit_id UUID",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS received_at_utc TIMESTAMPTZ",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS derived_state VARCHAR(2)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS intake_status VARCHAR(40)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS evidence_status VARCHAR(40)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS screening_status VARCHAR(40)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS contact_status VARCHAR(40)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS notification_status VARCHAR(80)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS consent_authority VARCHAR(160)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS consent_status VARCHAR(80)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS privacy_version VARCHAR(120)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS terms_version VARCHAR(120)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS producer_license_number VARCHAR(80)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS launch_matrix_version VARCHAR(120)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS receipt_token_hash VARCHAR(64)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS conversion_status VARCHAR(40)",
]

DDL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_mp_submission_id ON leads(submission_id) WHERE submission_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_mp_lead_uuid ON leads(lead_uuid) WHERE lead_uuid IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_mp_receipt_hash ON leads(receipt_token_hash) WHERE receipt_token_hash IS NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS mp_zip_state (
      zip_code CHAR(5) PRIMARY KEY,
      state_code CHAR(2) NOT NULL,
      source_name VARCHAR(160) NOT NULL,
      source_version VARCHAR(120) NOT NULL,
      verified_at TIMESTAMPTZ NOT NULL,
      active BOOLEAN NOT NULL DEFAULT TRUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mp_state_matrix (
      state_code CHAR(2) PRIMARY KEY,
      state_name VARCHAR(100) NOT NULL,
      producer_license_number VARCHAR(80),
      launch_allowed BOOLEAN NOT NULL DEFAULT FALSE,
      matrix_version VARCHAR(120) NOT NULL,
      verified_source VARCHAR(240) NOT NULL,
      verified_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mp_events (
      id BIGSERIAL PRIMARY KEY,
      submission_id UUID NOT NULL,
      event_type VARCHAR(80) NOT NULL,
      event_payload TEXT,
      occurred_at_utc TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mp_events_submission ON mp_events(submission_id, occurred_at_utc)",
    """
    CREATE TABLE IF NOT EXISTS mp_conversion_outbox (
      id BIGSERIAL PRIMARY KEY,
      submission_id UUID NOT NULL UNIQUE,
      transaction_id VARCHAR(80) NOT NULL UNIQUE,
      gclid VARCHAR(255),
      gbraid VARCHAR(255),
      wbraid VARCHAR(255),
      status VARCHAR(80) NOT NULL,
      destination_reference VARCHAR(255),
      created_at_utc TIMESTAMPTZ NOT NULL,
      authorized_at_utc TIMESTAMPTZ,
      delivered_at_utc TIMESTAMPTZ,
      last_error TEXT
    )
    """,
]


def run_migration():
    conn = get_connection(); cur = conn.cursor()
    try:
        for sql in ALTER_COLUMNS + DDL:
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    run_migration()
    print("OK: Mortgage Protection vNext additive schema ready")
