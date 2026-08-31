"""Browser-script regression coverage for Mortgage Protection click attribution.

The production page is plain HTML/JavaScript, so these tests execute its actual
inline script in Node with a minimal browser-shaped harness.  No production
endpoint, lead submission, TrustedForm call, or Google conversion is involved.
"""
import json
import os
import re
import subprocess


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROTECT_MORTGAGE_PATH = os.path.join(REPO_ROOT, "protect_mortgage.html")


def _page_html():
    with open(PROTECT_MORTGAGE_PATH, "r", encoding="utf-8") as page:
        return page.read()


def _form_script():
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", _page_html(), re.DOTALL)
    return next(script for script in scripts if "MP_CLICK_ID_STORAGE_KEYS" in script)


def _run_browser_harness(**overrides):
    config = {
        "href": "https://protect-mortgage.com/",
        "search": "",
        "now": 1_800_000_000_000,
        "storage": {},
        "storageBlocked": False,
        "submitOutcome": None,
        "invalidForm": False,
    }
    config.update(overrides)

    harness = r"""
const vm = require('vm');
const config = JSON.parse(process.argv[1]);
const productionScript = JSON.parse(process.argv[2]);
const store = new Map(Object.entries(config.storage || {}));
let submitHandler = null;
let fetchCalls = 0;

function classList() {
  return { add() {}, remove() {}, contains() { return false; } };
}

function element(value = '') {
  return {
    value,
    checked: false,
    disabled: false,
    textContent: '',
    innerText: '',
    style: {},
    classList: classList(),
    addEventListener(type, handler) {
      if (this === elements['mp-form'] && type === 'submit') submitHandler = handler;
    },
    scrollIntoView() {},
    querySelectorAll() { return []; },
    closest() { return { classList: classList() }; }
  };
}

const elements = {
  gclid: element(), gbraid: element(), wbraid: element(), submitted_url: element(),
  phone: element('(555) 123-4567'), first_name: element(config.invalidForm ? '' : 'Jane'),
  last_name: element('Doe'), email: element('jane@example.com'), zip: element('90210'),
  age: element('35'), sex: element('female'), mortgage_balance: element('100000-200000'),
  code_word: element('sunflower'), 'form-error': element(), 'decline-message': element(),
  'homeowner-row': element(), 'tobacco-row': element(), 'consent-label': element(),
  'consent-check': element(), 'submit-btn': element(), 'mp-form': element()
};
elements['consent-check'].checked = true;
const homeowner = { value: 'yes' };
const tobacco = { value: 'no' };
const trustedForm = { value: 'https://cert.example/test' };
const consentBox = { innerText: 'Existing consent text' };

const sessionStorage = {
  getItem(key) { if (config.storageBlocked) throw new Error('blocked'); return store.has(key) ? store.get(key) : null; },
  setItem(key, value) { if (config.storageBlocked) throw new Error('blocked'); store.set(key, String(value)); },
  removeItem(key) { if (config.storageBlocked) throw new Error('blocked'); store.delete(key); }
};

const document = {
  getElementById(id) { return elements[id] || (elements[id] = element()); },
  getElementsByName(name) { return name === 'xxTrustedFormCertUrl' ? [trustedForm] : []; },
  querySelector(selector) {
    if (selector === 'input[name="homeowner"]:checked') return homeowner;
    if (selector === 'input[name="tobacco_use"]:checked') return tobacco;
    if (selector === '.consent-box') return consentBox;
    return null;
  },
  querySelectorAll() { return []; }
};

const location = { href: config.href, search: config.search };
const window = { location, sessionStorage, mpTrustedFormScriptStatus: 'loaded' };
const fetch = function() {
  fetchCalls += 1;
  if (config.submitOutcome === 'network') return Promise.reject(new Error('network'));
  const body = config.submitOutcome === 'ok'
    ? { status: 'ok', conversion_token: 'server-token' }
    : config.submitOutcome === 'declined'
      ? { status: 'declined', message: 'Declined' }
      : { status: 'error', message: 'Retry' };
  return Promise.resolve({ ok: body.status !== 'error', json: () => Promise.resolve(body) });
};

const context = {
  window, document, fetch, URLSearchParams, Date: class extends Date { static now() { return config.now; } },
  Number, String, Promise, encodeURIComponent, setTimeout, clearTimeout, console
};
vm.createContext(context);
vm.runInContext(productionScript, context);

(async function() {
  if (config.submitOutcome !== null || config.invalidForm) {
    await submitHandler({ preventDefault() {} });
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  process.stdout.write(JSON.stringify({
    fields: {
      gclid: elements.gclid.value,
      gbraid: elements.gbraid.value,
      wbraid: elements.wbraid.value,
      submitted_url: elements.submitted_url.value
    },
    storage: Object.fromEntries(store),
    locationHref: location.href,
    fetchCalls,
    ttl: context.MP_CLICK_ID_TTL_MS
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", harness, json.dumps(config), json.dumps(_form_script())],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


KEYS = {
    "gclid": "bfg_mp_click_gclid",
    "gbraid": "bfg_mp_click_gbraid",
    "wbraid": "bfg_mp_click_wbraid",
    "saved_at": "bfg_mp_click_saved_at",
    "landing_url": "bfg_mp_click_landing_url",
}


def _stored(now, **ids):
    values = {
        KEYS["saved_at"]: str(now - 1_000),
        KEYS["landing_url"]: "https://protect-mortgage.com/?gclid=original",
    }
    values.update({KEYS[name]: value for name, value in ids.items()})
    return values


def test_url_click_ids_take_precedence_and_are_stored_as_one_fresh_set():
    now = 1_800_000_000_000
    href = "https://protect-mortgage.com/?gclid=new-gclid&gbraid=new-gbraid&wbraid=new-wbraid"
    result = _run_browser_harness(
        href=href,
        search="?gclid=new-gclid&gbraid=new-gbraid&wbraid=new-wbraid",
        now=now,
        storage=_stored(now, gclid="old-gclid", gbraid="old-gbraid", wbraid="old-wbraid"),
    )

    assert result["fields"] == {
        "gclid": "new-gclid",
        "gbraid": "new-gbraid",
        "wbraid": "new-wbraid",
        "submitted_url": href,
    }
    assert result["storage"][KEYS["saved_at"]] == str(now)
    assert result["storage"][KEYS["landing_url"]] == href


def test_clean_url_restores_unexpired_session_ids_and_original_landing_url():
    now = 1_800_000_000_000
    landing = "https://protect-mortgage.com/?gclid=saved-gclid&campaign=mp"
    storage = _stored(now, gclid="saved-gclid", gbraid="saved-gbraid", wbraid="saved-wbraid")
    storage[KEYS["landing_url"]] = landing

    result = _run_browser_harness(now=now, storage=storage)

    assert result["fields"] == {
        "gclid": "saved-gclid",
        "gbraid": "saved-gbraid",
        "wbraid": "saved-wbraid",
        "submitted_url": landing,
    }


def test_fresh_gclid_cannot_inherit_old_braid_identifiers():
    now = 1_800_000_000_000
    result = _run_browser_harness(
        href="https://protect-mortgage.com/?gclid=fresh",
        search="?gclid=fresh",
        now=now,
        storage=_stored(now, gclid="old", gbraid="old-gbraid", wbraid="old-wbraid"),
    )

    assert result["fields"]["gclid"] == "fresh"
    assert result["fields"]["gbraid"] == ""
    assert result["fields"]["wbraid"] == ""
    assert KEYS["gbraid"] not in result["storage"]
    assert KEYS["wbraid"] not in result["storage"]


def test_fresh_braid_identifier_cannot_inherit_stale_gclid():
    now = 1_800_000_000_000
    result = _run_browser_harness(
        href="https://protect-mortgage.com/?wbraid=fresh-wbraid",
        search="?wbraid=fresh-wbraid",
        now=now,
        storage=_stored(now, gclid="stale-gclid", gbraid="stale-gbraid"),
    )

    assert result["fields"]["gclid"] == ""
    assert result["fields"]["gbraid"] == ""
    assert result["fields"]["wbraid"] == "fresh-wbraid"
    assert KEYS["gclid"] not in result["storage"]
    assert KEYS["gbraid"] not in result["storage"]


def test_expired_attribution_is_cleared_and_not_restored():
    now = 1_800_000_000_000
    storage = _stored(now, gclid="expired")
    storage[KEYS["saved_at"]] = str(now - (2 * 60 * 60 * 1000) - 1)

    result = _run_browser_harness(now=now, storage=storage)

    assert result["fields"]["gclid"] == ""
    assert result["fields"]["submitted_url"] == "https://protect-mortgage.com/"
    assert result["storage"] == {}
    assert result["ttl"] == 2 * 60 * 60 * 1000


def test_blocked_session_storage_does_not_break_current_url_capture():
    href = "https://protect-mortgage.com/?gclid=current"
    result = _run_browser_harness(
        href=href, search="?gclid=current", storageBlocked=True
    )

    assert result["fields"]["gclid"] == "current"
    assert result["fields"]["submitted_url"] == href


def test_successful_response_clears_stored_attribution_before_redirect():
    result = _run_browser_harness(
        href="https://protect-mortgage.com/?gclid=success",
        search="?gclid=success",
        submitOutcome="ok",
    )

    assert result["storage"] == {}
    assert result["locationHref"] == "/thank-you?ct=server-token"


def test_declined_response_clears_stored_attribution():
    result = _run_browser_harness(
        href="https://protect-mortgage.com/?gclid=declined",
        search="?gclid=declined",
        submitOutcome="declined",
    )

    assert result["storage"] == {}
    assert result["locationHref"] == "https://protect-mortgage.com/?gclid=declined"


def test_validation_failure_does_not_clear_stored_attribution():
    result = _run_browser_harness(
        href="https://protect-mortgage.com/?gclid=retry",
        search="?gclid=retry",
        invalidForm=True,
    )

    assert result["storage"][KEYS["gclid"]] == "retry"
    assert result["fetchCalls"] == 0


def test_network_failure_does_not_clear_stored_attribution():
    result = _run_browser_harness(
        href="https://protect-mortgage.com/?gclid=retry",
        search="?gclid=retry",
        submitOutcome="network",
    )

    assert result["storage"][KEYS["gclid"]] == "retry"


def test_server_failure_does_not_clear_stored_attribution():
    result = _run_browser_harness(
        href="https://protect-mortgage.com/?gclid=retry",
        search="?gclid=retry",
        submitOutcome="server",
    )

    assert result["storage"][KEYS["gclid"]] == "retry"


def test_click_id_persistence_does_not_use_cookies_or_local_storage():
    script = _form_script()
    executable = re.sub(r"//.*", "", script)
    assert "window.localStorage" not in executable
    assert "localStorage." not in executable
    assert "document.cookie" not in executable
    assert "window.sessionStorage" in executable
