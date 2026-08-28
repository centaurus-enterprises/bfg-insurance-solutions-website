#!/usr/bin/env python3
"""
Idempotent deploy-time migration: adds the conversion-token columns needed
for server-backed exactly-once Google Ads conversion authorization on the
mortgage-protection funnel (conversion_token, conversion_token_expires_at,
conversion_claimed_at, and the partial unique index on conversion_token).

This intentionally replaces an earlier draft of this change that exposed
the same ALTER TABLE statements as a public HTTP route
(/run-migration-conv-tok-x7q2m), applied only after the new release was
already live. That ordering leaves a window, between the new code
deploying and someone remembering to hit the route, where a real
submission can 500 because the columns it needs don't exist yet. Running
this as a Render Pre-Deploy Command instead applies the schema change
before the new release starts taking traffic, closing that window.

Render setup required (not made by this script -- a human with dashboard
access needs to set this; see the PR description for exact steps):

    Render dashboard -> this service -> Settings -> Pre-Deploy Command:
        python migrate_conversion_token.py

    (Render's Root Directory for this service is already `backend`, so do
    NOT prefix the command with `backend/` -- that would look for
    backend/backend/migrate_conversion_token.py and fail.)

Safe to run repeatedly against the same database: every statement is
IF NOT EXISTS / CREATE ... IF NOT EXISTS, so re-running after the columns
already exist is a no-op. Exits 0 on success, non-zero on failure, so a
broken migration fails the Render deploy instead of silently shipping
code against a stale schema.
"""
import sys

from db import get_connection

STATEMENTS = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS conversion_token VARCHAR(64)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS conversion_token_expires_at TIMESTAMPTZ",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS conversion_claimed_at TIMESTAMPTZ",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_conversion_token "
    "ON leads (conversion_token) WHERE conversion_token IS NOT NULL",
]


def run_migration():
    """Applies the conversion-token schema change. Raises on failure."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        for statement in STATEMENTS:
            cur.execute(statement)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def main():
    try:
        run_migration()
    except Exception as e:
        print(f"conversion-token migration failed: {e}", file=sys.stderr)
        return 1
    print("OK: conversion_token, conversion_token_expires_at, "
          "conversion_claimed_at columns and index present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
