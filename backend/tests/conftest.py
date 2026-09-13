import os, sys
from datetime import datetime, timezone

os.environ.setdefault('DB_HOST','localhost');os.environ.setdefault('DB_PORT','5432');os.environ.setdefault('DB_NAME','bfg_test');os.environ.setdefault('DB_USER','bfg_test');os.environ.setdefault('DB_PASSWORD','bfg_test')
os.environ.pop('DATABASE_URL',None);os.environ.pop('SENDGRID_API_KEY',None);os.environ.pop('MAIL_SENDER',None);os.environ.pop('MP_LEAD_NOTIFICATION_TO',None)
os.environ['MP_PRIVACY_VERSION']='test-approved-privacy';os.environ['MP_TERMS_VERSION']='test-approved-terms';os.environ['MP_TF_CODE_WORD_MASKING_VERIFIED']='true';os.environ['MP_ENABLE_VNEXT_PREVIEW']='true'
BACKEND=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,BACKEND)
import pytest
import legacy_app
from app import app as flask_app
import mp_vnext
from db import get_connection
from migrate_mp_vnext import run_migration

@pytest.fixture(scope='session',autouse=True)
def schema():
    legacy_app.run_migration_init()
    run_migration()
    yield

@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(mp_vnext,'CONSENT_STATUS','APPROVED_FOR_PRODUCTION')
    monkeypatch.setattr(mp_vnext,'_retain_tf',lambda url,email,phone:(True,'RETAINED'))
    c=get_connection();q=c.cursor()
    q.execute('TRUNCATE TABLE mp_events, mp_conversion_outbox, leads RESTART IDENTITY')
    q.execute('DELETE FROM mp_zip_state');q.execute('DELETE FROM mp_state_matrix')
    q.execute("INSERT INTO mp_zip_state(zip_code,state_code,source_name,source_version,verified_at,active) VALUES('90210','CA','TEST_AUTHORITATIVE_ZIP','test-v1',%s,TRUE)",(datetime.now(timezone.utc),))
    q.execute("INSERT INTO mp_state_matrix(state_code,state_name,producer_license_number,launch_allowed,matrix_version,verified_source,verified_at) VALUES('CA','California','4374779',TRUE,'test-launch-v1','TEST_FIXTURE',%s)",(datetime.now(timezone.utc),))
    c.commit();q.close();c.close();yield

@pytest.fixture
def client():
    flask_app.testing=True
    return flask_app.test_client()

def valid_payload(**overrides):
    d={'first_name':'Jane','last_name':'Doe','gender':'female','age':'35','phone':'5551234567','email':'jane@example.com','zip':'90210','mortgage_balance':'250k_499999','tobacco_use':'no','code_word':'Falcon','consent_accepted':True,'visit_id':'11111111-1111-4111-8111-111111111111','gclid':'g-test','gbraid':'','wbraid':'','submitted_url':'https://protect-mortgage.com/?gclid=g-test','trustedform_cert_url':'https://cert.trustedform.com/test'};d.update(overrides);return d
