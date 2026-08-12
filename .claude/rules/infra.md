# Infrastructure — hand off, don't do

Scoped rule — loads when a task touches DNS, hosting, or deployment.

No access to the GoDaddy or Render dashboards, and must not attempt to
change them. When a task requires a DNS change, a Render service or
environment-variable change, a custom-domain addition, or anything else
in a vendor dashboard: write Joshua explicit step-by-step instructions —
exact screen, exact field, exact value, and how he verifies it worked —
and stop there. Include what to check if it fails. Then continue with
code-side work that doesn't depend on it, or say clearly that you're
blocked.

## Reference values (verified against Render's documentation)

| Need | Record | Value |
|---|---|---|
| Apex (protect-mortgage.com) | A | 216.24.57.1 |
| Apex, if registrar supports it | ANAME/ALIAS | `<service>.onrender.com` |
| Subdomain (www, etc.) | CNAME | `<service>.onrender.com` |

GoDaddy's DNS editor does not offer ANAME/ALIAS — expect to use the A
record path for the apex. Have Joshua confirm the available record types
in the dropdown rather than assuming.

Render custom domain flow: service → Settings → Add Custom Domain → add
DNS at the registrar → return and click Verify. Render issues the TLS
certificate on successful verification.

## Known blockers, in order they'll actually bite

1. **protect-mortgage.com currently resolves to a GoDaddy Websites +
   Marketing site.** Cutting DNS to Render detaches that product. Flag
   this to Joshua before he changes records, and have him confirm the
   Render service serves correctly at its .onrender.com URL first.
2. **Websites + Marketing may auto-manage its own DNS records** and can
   lock or silently revert manual A/CNAME edits while the product is
   still attached. Don't treat "I edited the record" as done until the
   editor stays edited — confirm the product has actually been detached,
   and note that detachment itself can take time to process.
3. **Propagation is not a fixed number.** It depends on the TTL of the
   existing records, and some resolvers hold stale answers past their
   TTL regardless. Don't promise same-day completion. Start any cutover
   early in the day/evening, not right before you need to stop being
   available to respond to failures.
4. **DNS resolving and TLS being issued are two separate checkpoints.**
   Verify both — don't treat "it resolves" as "it's done."
