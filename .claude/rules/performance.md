# Performance / device targets

Scoped rule — loads when frontend/form files are being edited.

- LCP < 2.5s on throttled 4G, tested on a low-end Android device.
- Form above the fold at 360×800 first (Android), then verify 390×844
  (iPhone). 360 is the stricter target.
- Verify the full flow inside an Android Chrome Custom Tab and iOS
  SFSafariViewController — not just a normal desktop/mobile browser.
- `tel:` click-to-call must launch the dialer from inside an in-app
  browser.
- No carousel, autoplay video, interstitial, or cookie wall blocking the
  form.
- Degrade to a visible message rather than a silently dead form when JS
  is blocked.
