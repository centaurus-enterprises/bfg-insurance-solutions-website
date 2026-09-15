# CLAUDE.md — current repository controls

This file contains implementation controls for the organization repository
`centaurus-enterprises/bfg-insurance-solutions-website`. It is not a business,
legal, compliance, campaign, or production-authorization document.

## Authority and provenance

Apply this order: John's latest explicit decision; approved decision/specification;
workstream charter; verified current evidence; current approved architecture;
historical material; recommendations and AI interpretation.

The repository's default branch is shared organization state. A collaborator's
name, role, or commit authorship does not make `main` that person's branch and
does not establish current authority. Verify branch ancestry, file content, and
the controlling requirements independently.

## Greenfield rule

The current BFG website, intake, Google Ads, YouTube, measurement, CRM, and
lead-processing architecture is greenfield. Historical lessons may become
safeguards and tests. Historical identifiers, settings, assets, structures,
code paths, and configurations are preserve-only and must not become defaults.

No historical marketing identifier may appear in an active repository file or
active test, including as a negative fixture. Use generic sentinels and generic
configuration-validation tests. Preserve historical evidence outside the active
production repository.

## Work boundaries

- Inventory the stack and read current requirements before making changes.
- Keep work on the existing authorized branch/PR unless current evidence proves
  it unusable.
- Do not merge, deploy, mutate production data/schema, change DNS or Render,
  create or change Google Ads/YouTube/GTM/analytics assets, upload video,
  activate a campaign, or spend without separate authorization.
- Do not run staging until the complete WS30 correction candidate and the WS50
  greenfield measurement definition both exist. WS60 owns one integrated
  zero-spend acceptance pass.

## Mortgage Protection intake invariants

- Browser posts to the server, never directly to the CRM.
- Client validation is UX only; server validation is authoritative.
- First name, last name, phone, email, five-digit U.S. ZIP, age 18–100, gender,
  tobacco answer, and affirmative consent are required.
- ZIP intake is not California-only. State derivation and state/license/contact
  eligibility are separate controlled steps; receipt is not contact release.
- The consumer Thank You page must not display or infer a state name or license
  number from ZIP. State/license evaluation remains an internal contact-release
  control.
- Approximate Mortgage Balance is optional. If supplied, validate the current
  approved enum.
- Code Word is optional. If supplied, validate and protect it. Never place it in
  URLs, analytics, advertising payloads, routine logs, unnecessary third-party
  surfaces, or readable session replay.
- Consent text/version are server-controlled. Do not treat browser-supplied text
  as authoritative evidence.
- Persist a stable lead identity before external evidence processing.
- Missing, failed, malformed, timed-out, or inconsistent TrustedForm evidence
  remains `EVIDENCE_HOLD`.
- `EVIDENCE_HOLD` prohibits ordinary notification, contact release, and
  conversion authorization. Retry is idempotent, bounded, visible, and never
  silently releases or deletes the record.
- `INTAKE_ACCEPTED` requires affirmative consent, durable persistence,
  TrustedForm overall success, retention proof, and successful lead match.
- Contact remains `STATE_LICENSE_SCREENING_PENDING` until the authoritative
  state/license control clears it.

## TrustedForm security and parsing

- Accept only the exact HTTPS origin `cert.trustedform.com` with no userinfo or
  alternate port.
- Send `api-version: 4.0` and separate `retain` and `match_lead` operations.
- An HTTP 200 alone is not success. Parse overall outcome, retention result, lead
  match result, and reason/error information.
- Keep API credentials server-side in environment variables.

## Measurement

Measurement remains disabled in active pages until WS50 defines and verifies the
new BFG-owned architecture. Account ownership does not imply that any conversion
action, tag, label, campaign, or attribution configuration exists or is approved.
All uncreated values are `TBD`.

Generic click/submission identity and idempotent authorization concepts may be
tested without embedding any account-specific destination. Conversion may be
authorized only for an `INTAKE_ACCEPTED` record. The active repository must not
contain a historical conversion destination.

## Acceptance and Kaizen

- Map each current acceptance criterion to a named test.
- Test optional fields, national ZIP intake, explicit consent, TrustedForm
  origin/header/payload/outcome branches, evidence holds, retry bounds, no
  notification/conversion while held, and generic measurement configuration.
- Scan active files for prohibited historical artifacts without storing the
  prohibited values in the repository.
- Classify audit completeness accurately: known source contamination can be
  confirmed while complete repository/runtime inventory remains unresolved.
