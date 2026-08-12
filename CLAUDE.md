# CLAUDE.md — protect-mortgage.com / Centaurus Enterprises web properties

Build context for Claude Code sessions on this repo. Functionality and code
only. Compliance rules appear here **as code invariants** — they are build
requirements, not commentary. Violating one is a bug.

Authoritative spec: **Build Spec v2.2 + v2.3 Addendum rev B + Conversion
Tracking Addendum** (consolidated here as v2.4). Where this file and a spec
document disagree, the spec document wins. Ask John for the current copy
before starting substantial work.

## 0. Before changing anything

The stack is not described here on purpose — inventory it first:

1. Read package.json, framework config, directory layout. Report findings
   before proposing changes.
2. Identify where form submission is handled today and whether a
   server-side layer exists.
3. Confirm the Render service name, branch, build/start commands.
4. Grep the entire repo for retired brand names (§10) before doing anything
   else — this blocks the domain move.
5. State the plan, then build. Do not refactor beyond the task.

## 1. What we're building

Two funnels, deliberately separate. Never commingle their data or branding.

| Funnel | Domain | Backend | Audience |
|---|---|---|---|
| Consumer mortgage protection | protect-mortgage.com | Consumer CRM (endpoint **PENDING**) | YouTube/Google ads |
| Agent recruiting | centaurusenterprises.com/careers | Recruiting CRM, separate | Agent prospects |

Consumer flow: ad click → protect-mortgage.com → 10-field intake →
server-side POST to CRM → verification → dial. Consumer never leaves
protect-mortgage.com; /thank-you is same host.

## 2. Hard architecture invariants

- Browser never posts directly to the CRM. Form → server → CRM.
- Client-side validation is UX only. Server-side is authoritative — a
  failing submission is rejected with the field flagged, never silently
  stored.
- API keys server-side only, env vars, never in client code/bundle.
- Timestamps from server clock, ISO 8601 with explicit UTC offset.
- CRM hostname never exposed to a consumer — no redirect, no visible form
  action, no link in consumer email.
- Never emit thebfg.net anywhere consumer-visible, including From address.
- Keep the two CRMs separate — consent records are a legal defense file.

## 3. Intake form — 10 fields, all required

first_name · last_name · phone (tel, 10-digit US) · email · zip (5) ·
date_of_birth · mortgage_balance (select) · homeowner (radio) ·
tobacco_use (radio, **now required**) · code_word (text) · hidden gclid,
gbraid, wbraid.

### code_word — free text, last field, above the consent block

Not a security question — it authenticates **the agent to the caller**,
not the reverse.

- 3–20 chars, letters only (A–Za–z), no digits/spaces/punctuation, single
  word.
- Trim before validate/store; store **as entered**; compare
  case-insensitively.
- Reject: matches lead's own first/last name; password/code/codeword/
  test/none/n-a; profanity (blocklist → polite retry, never a raw error).
- Do NOT blocklist retired brand names in consumer input — that rule
  applies to our copy, not theirs.
- Markup: autocapitalize="none" autocorrect="off" spellcheck="false".
- Stored plaintext, never hashed — agent reads it aloud on the call.
- Helper text (verbatim): "Pick a 'code' word we'll use when we call...
  We'll never ask you for it." Final sentence is load-bearing, do not cut.
- Never call it a security question, password, or PIN in any copy.

**Routing:** homeowner = No → soft decline, not a lead. ZIP outside
allowlist → polite decline, not an error. Allowlist ships California-only;
config change, not code change, to add states. Do not enable another
state without written confirmation from John.

**On success:** redirect to distinct /thank-you. Inline "thanks!" fires
zero conversions — this is a bug, not a style choice. /thank-you not
reachable except after a real submit: no nav link, no sitemap entry.

## 4. Click-ID capture — highest priority, one-way door

Read gclid/gbraid/wbraid from query string on load → hidden fields →
persist server-side on the lead record at submit.

- Must not depend on cookies (YouTube in-app browsers have isolated/
  short-lived cookie storage).
- Never strip unknown query params. Never put PII in a query string.
- Leads captured before this works are permanently unattributable.

## 5. Conversion tracking (supersedes prior §5 in full)

Google tag AW-18193879267 immediately after `<head>` on **every** page,
including /thank-you, Privacy Policy, Terms of Use, CCPA notice. One tag
per page, never two.

```html
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-18193879267"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', 'AW-18193879267');
</script>
```

On /thank-you ONLY, inside `<head>`, immediately after the tag above:

```html
<!-- Event snippet for MP Lead - Site Form Submit -->
<script>
gtag('event', 'conversion', {'send_to': 'AW-18193879267/jLl8CIfe39wcEOOhwuND'});
</script>
```

- Fires on page load, never wired to the submit button click — a click
  fires before validation/storage and would count failed submissions.
- Do not hand-transcribe the label; copy from Ads UI (Goals → Conversions
  → Summary → MP Lead - Site Form Submit → See event snippet). Contains
  lowercase L, uppercase i, digit 1.
- Acceptance proof is the Ads UI status changing Inactive → Recording
  conversions, not Tag Assistant firing. Allow up to 3h for status, 24h
  for reporting.
- Enhanced conversions deliberately OFF until the Privacy Policy discloses
  hashed identifiers shared with ad platforms.

## 6. Consent and copy — verbatim, do not reword

- Consent checkbox unchecked by default, submit blocked until checked,
  immediately above submit button, visible without scrolling.
- Store exact consent text rendered + consent_version: "1.0".
- TrustedForm (or Jornaya) must fire; certificate URL lands on the CRM
  record. No certificate = not callable — system-enforced gate.
- Unlike the Ads conversion action, TrustedForm/Jornaya does not lock to
  a verified domain — the script hashes the current page/session and
  issues a certificate wherever it's embedded. This can be built and
  tested end-to-end (script fires → cert URL populates → lands on the
  CRM record) on the current live domain, independent of the DNS
  cutover. Don't block this on the domain move.
- Footer disclosure exact text. Never render a numeric state count —
  approved wording: "Licensed in California and additional states; not
  all products are available in all states."
- Attribution is footer-only, attributing to John M. Brown (CA Lic.
  #4374779) and Joshua Brown (CA Lic. #4509549). BFG Insurance Solutions
  is the only approved dba. No hero attribution block.
- Never generate: guarantee language, lender/servicer/government
  affiliation implication, fear/urgency hooks, a specific premium as
  universal, named carriers, "our agency/agents," "we are licensed."
- Above-the-fold is advertising — Google screenshots it into the ad unit.

## 7. Operational stop rule (wrong/reassigned number)

If the person answering does not recognize the code word: stop, no
product mention, apologize, set code_word_confirmed = false, disposition
as "possible wrong number" (distinct from reject queue), suppress from
further dialing pending review.

Script order on first contact (voice and SMS): name + license + code word
→ California recorded-line disclosure → permission to proceed → only then
anything substantive. No product language until code word is confirmed.

## 8. Lead record fields

Written server-side at intake: code_word, code_word_set_at (server clock,
ISO 8601+offset), code_word_confirmed (enum), code_word_confirmed_at,
lead_source (non-nullable), lead_source_bucket (approved|outside|
self_generated, non-nullable), consent_version ("1.0"). Plus TrustedForm
cert URL, submission timestamp, IP, full URL with query string, exact
consent text, user agent — treat as **one artifact**, never split.

Retention: consent records, certs, verification responses, code-word
fields — 5 years minimum. Revocation events permanent, never purged.
Purge must be haltable per-cohort.

**PENDING — ask John, do not guess:**
- Consumer CRM endpoint URL (was crm.thebfg.net; changing)
- Data storage location, backups, encryption at rest, DB access list

Build against a configurable endpoint until these land.

## 9. Performance / device targets

See `.claude/rules/performance.md` — LCP, mobile-fold, in-app-browser,
and degradation requirements. Load it whenever editing frontend/form
files.

## 10. Never do these

- Zero occurrences anywhere consumer-facing of: Brown Financial Group,
  The Brown Financial Group, Brown Agency, TheBFG. Grep before shipping.
- Auto-dialer, power dialer, predictive dialer of any kind — human-
  initiated click-to-dial only.

## 11. Infrastructure — hand off, don't do

See `.claude/rules/infra.md` — no dashboard access, DNS/Render reference
values, and the known blockers on the domain cutover. Load it whenever a
task touches DNS, hosting, or deployment.
