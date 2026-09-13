import os
from pathlib import Path
from conftest import valid_payload
from db import get_connection
import mp_vnext

ROOT=Path(__file__).resolve().parents[2]

def submit(client,**overrides): return client.post('/api/mp/submit',json=valid_payload(**overrides))

def test_form_is_bfg_branded_and_exact_headline_present():
    h=(ROOT/'protect_mortgage.html').read_text(encoding='utf-8')
    assert 'BFG Insurance Solutions' in h
    assert 'Request Your Mortgage Protection Quote' in h
    assert 'Request My Mortgage Protection Quote' in h
    assert 'John M. Brown' not in h and 'Joshua Brown' not in h
    assert 'Home Ownership' not in h and 'Date of Birth' not in h and 'Preferred Contact Method' not in h and 'Best Time to Contact' not in h

def test_form_has_required_vnext_fields_and_no_homeowner():
    h=(ROOT/'protect_mortgage.html').read_text(encoding='utf-8')
    for n in ['first_name','last_name','gender','age','phone','email','zip','mortgage_balance','tobacco_use','code_word']:
        assert f'name="{n}"' in h
    assert 'name="homeowner"' not in h

def test_success_persists_evidence_and_account_neutral_outbox(client):
    r=submit(client);assert r.status_code==200
    d=r.get_json();assert d['outcome']=='INTAKE_ACCEPTED';assert d['contact_status']=='DO_NOT_CONTACT';assert d['receipt_token']
    c=get_connection();q=c.cursor();q.execute("SELECT intake_status,evidence_status,derived_state,producer_license_number,consent_version,consent_text,homeowner,gclid,screening_status,contact_status,notification_status FROM leads WHERE submission_id=%s",(d['submission_id'],));row=q.fetchone();q.execute("SELECT transaction_id,status,gclid FROM mp_conversion_outbox WHERE submission_id=%s",(d['submission_id'],));out=q.fetchone();q.close();c.close()
    assert row[0:4]==('INTAKE_ACCEPTED','COMPLETE','CA','4374779')
    assert row[4]==mp_vnext.CONSENT_VERSION and 'BFG Insurance Solutions' in row[5]
    assert row[6] is None
    assert row[7]=='g-test' and row[8]=='SCREENING_PENDING' and row[9]=='DO_NOT_CONTACT'
    assert row[10]=='BLOCKED_MISSING_WS20_NOTIFICATION_CONFIG'
    assert out[0]==d['submission_id'] and out[1]=='PENDING_WS50_DESTINATION' and out[2]=='g-test'

def test_receipt_returns_verified_state_specific_identity(client):
    d=submit(client).get_json();r=client.get('/api/mp/receipt?token='+d['receipt_token']);x=r.get_json()
    assert x['producer_name']=='John M. Brown';assert x['business_name']=='BFG Insurance Solutions';assert x['state']=='CA';assert x['producer_license_number']=='4374779'

def test_no_google_destination_id_is_hardcoded_in_vnext_surfaces(client):
    form=(ROOT/'protect_mortgage.html').read_text(encoding='utf-8');ty=(ROOT/'mortgage_thank_you.html').read_text(encoding='utf-8')
    assert 'AW-18193879267' not in form+ty and 'send_to' not in ty
    d=submit(client).get_json();r=client.post('/api/mp/conversion-authorization',json={'receipt_token':d['receipt_token']});x=r.get_json()
    assert x['transaction_id']==d['submission_id'];assert x['destination_status']=='PENDING_WS50_DESTINATION'

def test_consent_is_server_authoritative(client):
    p=valid_payload();p['consent_text']='MALICIOUS CLIENT TEXT';r=client.post('/api/mp/submit',json=p);d=r.get_json()
    c=get_connection();q=c.cursor();q.execute('SELECT consent_text FROM leads WHERE submission_id=%s',(d['submission_id'],));text=q.fetchone()[0];q.close();c.close()
    assert text==mp_vnext.CONSENT_TEXT and 'MALICIOUS' not in text

def test_unchecked_consent_rejected_without_lead(client):
    r=submit(client,consent_accepted=False);assert r.status_code==400
    c=get_connection();q=c.cursor();q.execute('SELECT count(*) FROM leads');assert q.fetchone()[0]==0;q.close();c.close()

def test_zip_lookup_failure_is_not_treated_as_unsupported_state(client):
    r=submit(client,zip='10001');assert r.status_code==503;assert r.get_json()['outcome']=='LOOKUP_FAILED'

def test_verified_unsupported_state_is_distinct(client):
    c=get_connection();q=c.cursor();q.execute("INSERT INTO mp_zip_state(zip_code,state_code,source_name,source_version,verified_at,active) VALUES('85001','AZ','TEST','v1',NOW(),TRUE)");q.execute("INSERT INTO mp_state_matrix(state_code,state_name,producer_license_number,launch_allowed,matrix_version,verified_source,verified_at) VALUES('AZ','Arizona','TEST-LIC',FALSE,'test-v1','TEST',NOW())");c.commit();q.close();c.close()
    r=submit(client,zip='85001');assert r.status_code==200;assert r.get_json()['outcome']=='UNSUPPORTED_STATE'

def test_evidence_gate_blocks_success_when_consent_not_approved(client,monkeypatch):
    monkeypatch.setattr(mp_vnext,'CONSENT_STATUS','DRAFT_FOR_COMPLIANCE_REVIEW');r=submit(client);assert r.status_code==202;assert r.get_json()['outcome']=='EVIDENCE_HOLD'
    c=get_connection();q=c.cursor();q.execute('SELECT intake_status,conversion_status FROM leads');assert q.fetchone()==('EVIDENCE_HOLD','BLOCKED');q.execute('SELECT count(*) FROM mp_conversion_outbox');assert q.fetchone()[0]==0;q.close();c.close()

def test_code_word_never_appears_in_thank_you_or_conversion_outbox(client):
    d=submit(client,code_word='Falcon').get_json();ty=(ROOT/'mortgage_thank_you.html').read_text(encoding='utf-8');assert 'Falcon' not in ty
    c=get_connection();q=c.cursor();q.execute("SELECT column_name FROM information_schema.columns WHERE table_name='mp_conversion_outbox'");cols={r[0] for r in q.fetchall()};q.close();c.close();assert 'code_word' not in cols

def test_legacy_diagnostic_and_migration_http_routes_are_blocked(client):
    for path in ['/db-test','/debug-notifications-r5m8v','/run-migration-init-h4v9t','/run-migration-mp9k2q']:
        assert client.get(path).status_code==404

def test_blanket_cors_is_absent(client):
    r=client.get('/ping',headers={'Origin':'https://evil.example'});assert 'Access-Control-Allow-Origin' not in r.headers

def test_security_headers_present(client):
    r=client.get('/ping');assert r.headers['X-Content-Type-Options']=='nosniff';assert "frame-ancestors 'none'" in r.headers['Content-Security-Policy']

def test_admin_vnext_uses_textcontent_not_innerhtml():
    h=(ROOT/'backend'/'templates'/'admin_vnext.html').read_text(encoding='utf-8');assert 'textContent' in h;assert 'innerHTML' not in h

def test_migration_is_idempotent():
    from migrate_mp_vnext import run_migration
    run_migration();run_migration()
