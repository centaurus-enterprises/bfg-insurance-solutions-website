"""BFG application composition layer.

The prior application implementation is preserved verbatim in ``legacy_app``.
This module composes the Mortgage Protection vNext blueprint and security
boundary around it while preserving the historical routes required by the
rest of the site. Production merge/deployment remains separately gated.
"""
import os

from flask import jsonify, redirect, render_template, request, send_from_directory, url_for

import legacy_app as legacy
from legacy_app import *  # noqa: F401,F403 - preserve existing module API
from mp_vnext import bp as mp_vnext_blueprint

app = legacy.app

# The historical app enables Flask-CORS globally. The vNext application is
# same-origin, so remove only Flask-CORS's blanket after-request callbacks.
for scope, funcs in list(app.after_request_funcs.items()):
    app.after_request_funcs[scope] = [
        func for func in funcs
        if not getattr(func, "__module__", "").startswith("flask_cors")
    ]

app.register_blueprint(mp_vnext_blueprint)

_BLOCKED_LEGACY_PUBLIC_PATHS = {
    "/db-test",
    "/debug-notifications-r5m8v",
    "/run-migration-b3z7p1",
    "/run-migration-mp9k2q",
    "/run-migration-tf-k2x9p",
    "/run-migration-init-h4v9t",
    "/submit-mortgage-protection",
    "/claim-conversion",
}


def _is_mp_host() -> bool:
    host = (request.host or "").split(":", 1)[0].lower()
    return host in {"protect-mortgage.com", "www.protect-mortgage.com", "localhost", "127.0.0.1"}


@app.before_request
def vnext_security_boundary():
    if request.path in _BLOCKED_LEGACY_PUBLIC_PATHS or request.path.startswith("/run-migration-"):
        return jsonify({"status": "not_found"}), 404
    # The generic legacy lead endpoint is not part of the Mortgage Protection
    # surface and exposes raw exceptions. Keep it off the MP host.
    if request.path == "/submit" and _is_mp_host():
        return jsonify({"status": "not_found"}), 404
    # The prior expandable CRM inserts stored lead values into innerHTML.
    # Route users to the vNext textContent-only CRM instead.
    if request.path == "/admin":
        return redirect(url_for("admin_vnext"))
    return None


@app.after_request
def vnext_security_headers(response):
    response.headers.pop("Access-Control-Allow-Origin", None)
    response.headers.pop("Access-Control-Allow-Credentials", None)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://api.trustedform.com; "
        "connect-src 'self' https://api.trustedform.com https://cert.trustedform.com; "
        "frame-src https://api.trustedform.com https://cert.trustedform.com; "
        "img-src 'self' data: https://api.trustedform.com https://cert.trustedform.com; "
        "style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


@app.route("/admin-vnext")
@legacy.login_required
def admin_vnext():
    return render_template("admin_vnext.html", agent=legacy.get_current_agent())


@app.route("/licenses.html")
def licenses_vnext():
    return send_from_directory(legacy.SITE_ROOT, "licenses.html")


@app.route("/vnext-preview")
def vnext_preview():
    if os.getenv("MP_ENABLE_VNEXT_PREVIEW", "").lower() != "true":
        return jsonify({"status": "not_found"}), 404
    return send_from_directory(legacy.SITE_ROOT, "protect_mortgage.html")


if __name__ == "__main__":
    app.run(port=5000, debug=False)
