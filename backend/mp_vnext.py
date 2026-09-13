"""Mortgage Protection vNext isolated implementation.

Business authority: WS40 v1.0 APPROVED plus John's 2026-09-13 branding /
producer-identity amendment. Unresolved legal, eligibility, TrustedForm masking,
notification-recipient, and Google Ads destination decisions remain explicit gates.
"""
from datetime import datetime, timezone
from functools import wraps
import hashlib, html, os, re, secrets, uuid
import requests
from flask import Blueprint, jsonify, request, session
from db import get_connection

bp = Blueprint("mp_vnext", __name__)
CONSENT_VERSION = "mp-vnext-2026-09-13-draft-1"
CONSENT_STATUS = "DRAFT_FOR_COMPLIANCE_REVIEW"
CONSENT_AUTHORITY = "BFG_WS40_V1_0_PLUS_2026_09_13_BRANDING_AMENDMENT"
CONSENT_TEXT = ("By checking the box below and selecting ‘Request My Mortgage Protection Quote,’ "
"I authorize BFG Insurance Solutions, a DBA of Centaurus Enterprises LLC, to contact me at the phone number and email address I provided about my request for mortgage protection insurance information and available insurance options by live-agent telephone call, SMS/text message, and email. Message and data rates may apply to texts. I understand that this consent is not a condition of purchasing any insurance product or service. I may revoke or limit this consent at any time, including by replying STOP to a text or asking not to be contacted during a call; additional revocation methods are described in the Privacy Notice.")
MORTGAGE_LABELS={"under_100k":"Under $100,000","100k_249999":"$100,000–$249,999","250k_499999":"$250,000–$499,999","500k_749999":"$500,000–$749,999","750k_plus":"$750,000 or more"}

def _now(): return datetime.now(timezone.utc)
def _err(msg,status=400,field=None,code="VALIDATION_FAILED"):
    p={"status":"error","outcome":code,"message":msg}
    if field:p["field"]=field
    return jsonify(p),status

def _name(v):
    v=re.sub(r"\s+"," ",(v or "").strip())
    if not 1<=len(v)<=80 or not any(c.isalpha() for c in v) or any(ord(c)<32 for c in v):raise ValueError
    return v

def _phone(v):
    d=re.sub(r"\D","",v or "")
    if len(d)==11 and d.startswith("1"):d=d[1:]
    if len(d)!=10:raise ValueError
    return "+1"+d

def _email(v):
    v=(v or "").strip()
    if len(v)>254 or any(c.isspace() for c in v) or not re.fullmatch(r"[^@]+@[^@]+\.[^@]+",v):raise ValueError
    a,b=v.rsplit("@",1);return a+"@"+b.lower()

def _code(v):
    v=(v or "").strip()
    if not re.fullmatch(r"[A-Za-z]{3,20}",v):raise ValueError
    return v

def _event(cur,sid,kind,payload=None): cur.execute("INSERT INTO mp_events(submission_id,event_type,event_payload,occurred_at_utc) VALUES(%s,%s,%s,%s)",(str(sid),kind,payload,_now()))
def _state(cur,z):
    cur.execute("SELECT state_code FROM mp_zip_state WHERE zip_code=%s AND active=TRUE",(z,));r=cur.fetchone();return r[0] if r else None

def _matrix(cur,s):
    cur.execute("SELECT state_name,producer_license_number,launch_allowed,matrix_version,verified_source,verified_at FROM mp_state_matrix WHERE state_code=%s",(s,));r=cur.fetchone()
    return None if not r else {"state_name":r[0],"producer_license_number":r[1],"launch_allowed":bool(r[2]),"matrix_version":r[3],"verified_source":r[4],"verified_at":r[5]}

def _retain_tf(url,email,phone):
    key=os.getenv("TRUSTEDFORM_API_KEY")
    if not key:return False,"TRUSTEDFORM_API_KEY_NOT_CONFIGURED"
    if not url or not url.startswith("https://cert.trustedform.com/"):return False,"TRUSTEDFORM_CERT_MISSING_OR_INVALID"
    try:r=requests.post(url,auth=("API",key),headers={"api-version":"4.0","Content-Type":"application/json","Accept":"application/json"},json={"retain":{},"match_lead":{"email":email,"phone":phone}},timeout=10)
    except requests.RequestException:return False,"TRUSTEDFORM_RETAIN_NETWORK_FAILURE"
    return (True,"RETAINED") if r.status_code==200 else (False,f"TRUSTEDFORM_RETAIN_HTTP_{r.status_code}")

def _notify(lead):
    key,sender,to=os.getenv("SENDGRID_API_KEY"),os.getenv("MAIL_SENDER"),os.getenv("MP_LEAD_NOTIFICATION_TO")
    if not(key and sender and to):return False,"BLOCKED_MISSING_WS20_NOTIFICATION_CONFIG"
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    esc=lambda v:html.escape(str(v or ""));nm=re.sub(r"[\x00-\x1f\x7f]+"," ",f"{lead['first_name']} {lead['last_name']}").strip();link=f"https://protect-mortgage.com/admin-vnext?lead={lead['submission_id']}"
    body=f"<h2>BFG Insurance Solutions</h2><h3>Mortgage Protection Lead</h3><p><strong>CONTACT STATUS: SCREENING PENDING</strong><br><strong>DO NOT CONTACT YET.</strong></p><p>Lead ID: {esc(lead['lead_id'])}<br>Name: {esc(nm)}<br>Phone: {esc(lead['phone'])}<br>Email: {esc(lead['email'])}<br>ZIP/State: {esc(lead['zip'])} / {esc(lead['state'])}<br>Age/Gender: {esc(lead['age'])} / {esc(lead['gender'].title())}<br>Tobacco: {'Yes' if lead['tobacco_use'] else 'No'}<br>Mortgage Balance: {esc(MORTGAGE_LABELS[lead['mortgage_balance']])}<br>Code Word: <strong>{esc(lead['code_word'])}</strong></p><p><a href=\"{esc(link)}\">Open Secure CRM Record</a></p>"
    try:SendGridAPIClient(key).send(Mail(from_email=sender,to_emails=to,subject=f"Mortgage Protection Lead — SCREENING PENDING — {nm} — Lead {lead['lead_id']}",html_content=body));return True,"SENT"
    except Exception:return False,"SEND_FAILED"

def _auth(fn):
    @wraps(fn)
    def w(*a,**k):
        aid=session.get("agent_id")
        if not aid:return jsonify({"status":"error","message":"Authentication required."}),401
        c=get_connection();q=c.cursor()
        try:q.execute("SELECT id FROM agents WHERE id=%s AND is_active=TRUE",(aid,));ok=q.fetchone()
        finally:q.close();c.close()
        return fn(*a,**k) if ok else (jsonify({"status":"error","message":"Authentication required."}),401)
    return w

@bp.post("/api/mp/submit")
def submit_mp():
    d=request.get_json(silent=True) or {}
    try:first,last=_name(d.get("first_name")),_name(d.get("last_name"))
    except ValueError:return _err("Enter your first and last name.",field="name")
    gender=d.get("gender")
    if gender not in("male","female"):return _err("Select Male or Female.",field="gender")
    try:age=int(str(d.get("age","")).strip());assert 18<=age<=100
    except Exception:return _err("Enter a valid age from 18 to 100.",field="age")
    try:phone=_phone(d.get("phone"))
    except ValueError:return _err("Enter a valid 10-digit US phone number.",field="phone")
    try:email=_email(d.get("email"))
    except ValueError:return _err("Enter a valid email address.",field="email")
    z=str(d.get("zip","")).strip()
    if not re.fullmatch(r"\d{5}",z):return _err("Enter a valid 5-digit ZIP Code.",field="zip")
    bal=d.get("mortgage_balance")
    if bal not in MORTGAGE_LABELS:return _err("Select your approximate mortgage balance.",field="mortgage_balance")
    tob=d.get("tobacco_use")
    if tob not in("yes","no"):return _err("Select Yes or No.",field="tobacco_use")
    try:cw=_code(d.get("code_word"))
    except ValueError:return _err("Enter a Code Word using 3–20 letters.",field="code_word")
    if d.get("consent_accepted") is not True:return _err("You must agree to the contact authorization to submit this request.",field="consent")
    try:visit=uuid.UUID(str(d.get("visit_id","")).strip())
    except ValueError:return _err("Please reload the page and try again.",field="visit_id",code="LOOKUP_FAILED")
    sid,luid=uuid.uuid4(),uuid.uuid4();received=_now();raw_receipt=secrets.token_urlsafe(32);receipt_hash=hashlib.sha256(raw_receipt.encode()).hexdigest()
    c=get_connection();q=c.cursor()
    try:
        st=_state(q,z)
        if not st:_event(q,sid,"LOOKUP_FAILED","ZIP_TO_STATE_NOT_FOUND");c.commit();return jsonify({"status":"hold","outcome":"LOOKUP_FAILED","message":"We could not verify your ZIP Code right now. Please try again."}),503
        mx=_matrix(q,st)
        if not mx:_event(q,sid,"LOOKUP_FAILED","LAUNCH_MATRIX_STATE_NOT_FOUND");c.commit();return jsonify({"status":"hold","outcome":"LOOKUP_FAILED","message":"We could not verify availability right now. Please try again."}),503
        if not mx["launch_allowed"]:_event(q,sid,"UNSUPPORTED_STATE",st);c.commit();return jsonify({"status":"declined","outcome":"UNSUPPORTED_STATE","message":"BFG Insurance Solutions is not currently accepting online mortgage protection requests in your area."})
        if not mx["producer_license_number"]:_event(q,sid,"LOOKUP_FAILED","VERIFIED_PRODUCER_LICENSE_MISSING");c.commit();return jsonify({"status":"hold","outcome":"LOOKUP_FAILED","message":"We could not verify availability right now. Please try again."}),503
        reasons=[];privacy=os.getenv("MP_PRIVACY_VERSION","").strip();terms=os.getenv("MP_TERMS_VERSION","").strip();mask=os.getenv("MP_TF_CODE_WORD_MASKING_VERIFIED","").lower()=="true"
        if CONSENT_STATUS!="APPROVED_FOR_PRODUCTION":reasons.append("CONSENT_COMPLIANCE_REVIEW_PENDING")
        if not privacy:reasons.append("PRIVACY_VERSION_NOT_CONFIGURED")
        if not terms:reasons.append("TERMS_VERSION_NOT_CONFIGURED")
        if not mask:reasons.append("TRUSTEDFORM_CODE_WORD_MASKING_NOT_VERIFIED")
        tfok,tfresult=_retain_tf(d.get("trustedform_cert_url",""),email,phone)
        if not tfok:reasons.append(tfresult)
        ev="COMPLETE" if not reasons else "EVIDENCE_HOLD";intake="INTAKE_ACCEPTED" if ev=="COMPLETE" else "EVIDENCE_HOLD";conv="AUTHORIZED" if intake=="INTAKE_ACCEPTED" else "BLOCKED"
        q.execute("""INSERT INTO leads(product_type,first_name,last_name,age,gender,mobile_phone,email,zip,state,tobacco,mortgage_balance,code_word,code_word_set_at,gclid,gbraid,wbraid,trustedform_cert_url,trustedform_retained,trustedform_retained_at,submitted_url,ip_address,user_agent,lead_source,lead_source_bucket,consent_version,consent_text,lead_uuid,submission_id,visit_id,received_at_utc,derived_state,intake_status,evidence_status,screening_status,contact_status,notification_status,consent_authority,consent_status,privacy_version,terms_version,producer_license_number,launch_matrix_version,receipt_token_hash,conversion_status) VALUES('mortgage-protection',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'protect-mortgage.com','vnext',%s,%s,%s,%s,%s,%s,%s,%s,%s,'SCREENING_PENDING','DO_NOT_CONTACT','PENDING',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",(first,last,age,gender,phone,email,z,st,tob=="yes",bal,cw,received,d.get("gclid") or None,d.get("gbraid") or None,d.get("wbraid") or None,d.get("trustedform_cert_url") or None,tfok,_now() if tfok else None,str(d.get("submitted_url",""))[:2000],(request.headers.get("X-Forwarded-For",request.remote_addr or "").split(",")[0].strip())[:64],request.headers.get("User-Agent","")[:500],CONSENT_VERSION,CONSENT_TEXT,str(luid),str(sid),str(visit),received,st,intake,ev,CONSENT_AUTHORITY,CONSENT_STATUS,privacy or None,terms or None,mx["producer_license_number"],mx["matrix_version"],receipt_hash,conv));lead_id=q.fetchone()[0]
        _event(q,sid,"SUBMISSION_PERSISTED",intake)
        if reasons:_event(q,sid,"EVIDENCE_HOLD",";".join(reasons))
        else:
            _event(q,sid,"INTAKE_ACCEPTED",st);q.execute("INSERT INTO mp_conversion_outbox(submission_id,transaction_id,gclid,gbraid,wbraid,status,created_at_utc) VALUES(%s,%s,%s,%s,%s,'PENDING_WS50_DESTINATION',%s) ON CONFLICT(submission_id) DO NOTHING",(str(sid),str(sid),d.get("gclid") or None,d.get("gbraid") or None,d.get("wbraid") or None,received))
        c.commit()
    except Exception:c.rollback();return _err("We could not process your request right now. Please try again.",500,code="TECHNICAL_FAILURE")
    finally:q.close();c.close()
    lead={"lead_id":lead_id,"submission_id":str(sid),"first_name":first,"last_name":last,"phone":phone,"email":email,"zip":z,"state":st,"age":age,"gender":gender,"tobacco_use":tob=="yes","mortgage_balance":bal,"code_word":cw}
    _,ns=_notify(lead) if intake=="INTAKE_ACCEPTED" else (False,"BLOCKED_EVIDENCE_HOLD")
    c=get_connection();q=c.cursor()
    try:q.execute("UPDATE leads SET notification_status=%s WHERE submission_id=%s",(ns,str(sid)));_event(q,sid,"NOTIFICATION_STATUS",ns);c.commit()
    finally:q.close();c.close()
    if intake!="INTAKE_ACCEPTED":return jsonify({"status":"hold","outcome":"EVIDENCE_HOLD","submission_id":str(sid),"message":"Your request was received, but we could not complete the required verification. BFG will not treat it as a completed online request until the verification issue is resolved."}),202
    return jsonify({"status":"ok","outcome":"INTAKE_ACCEPTED","submission_id":str(sid),"receipt_token":raw_receipt,"screening_status":"SCREENING_PENDING","contact_status":"DO_NOT_CONTACT","notification_status":ns})

@bp.get("/api/mp/receipt")
def receipt():
    t=request.args.get("token","");h=hashlib.sha256(t.encode()).hexdigest() if t else ""
    if not h:return _err("Receipt token required.")
    c=get_connection();q=c.cursor()
    try:q.execute("SELECT submission_id,derived_state,producer_license_number,intake_status,screening_status,contact_status,received_at_utc FROM leads WHERE receipt_token_hash=%s AND product_type='mortgage-protection'",(h,));r=q.fetchone()
    finally:q.close();c.close()
    if not r or r[3]!="INTAKE_ACCEPTED":return _err("Receipt not found.",404)
    return jsonify({"status":"ok","submission_id":str(r[0]),"producer_name":"John M. Brown","business_name":"BFG Insurance Solutions","state":r[1],"producer_license_number":r[2],"screening_status":r[4],"contact_status":r[5],"received_at":r[6].isoformat() if r[6] else None})

@bp.post("/api/mp/conversion-authorization")
def conversion_auth():
    t=(request.get_json(silent=True) or {}).get("receipt_token","");h=hashlib.sha256(t.encode()).hexdigest() if t else ""
    if not h:return _err("Receipt token required.")
    c=get_connection();q=c.cursor()
    try:
        q.execute("SELECT l.submission_id,o.transaction_id,o.status FROM leads l JOIN mp_conversion_outbox o ON o.submission_id=l.submission_id WHERE l.receipt_token_hash=%s AND l.intake_status='INTAKE_ACCEPTED' AND l.conversion_status='AUTHORIZED'",(h,));r=q.fetchone()
        if not r:return _err("Conversion is not authorized for this submission.",403,code="CONVERSION_BLOCKED")
        _event(q,uuid.UUID(str(r[0])),"CONVERSION_AUTHORIZATION_READ",r[2]);c.commit();return jsonify({"status":"ok","transaction_id":r[1],"destination_status":r[2],"message":"Conversion is queued at the account-neutral boundary; Google Ads destination remains WS50-controlled."})
    finally:q.close();c.close()

@bp.get("/api/mp/leads")
@_auth
def leads():
    c=get_connection();q=c.cursor()
    try:q.execute("SELECT submission_id,received_at_utc,first_name,last_name,derived_state,intake_status,evidence_status,screening_status,contact_status FROM leads WHERE product_type='mortgage-protection' ORDER BY received_at_utc DESC NULLS LAST,id DESC LIMIT 250");rows=q.fetchall()
    finally:q.close();c.close()
    return jsonify({"status":"ok","leads":[{"submission_id":str(r[0]),"received_at":r[1].isoformat() if r[1] else None,"first_name":r[2],"last_name":r[3],"state":r[4],"intake_status":r[5],"evidence_status":r[6],"screening_status":r[7],"contact_status":r[8]} for r in rows]})

@bp.get("/api/mp/leads/<submission_id>")
@_auth
def lead(submission_id):
    try:sid=uuid.UUID(submission_id)
    except ValueError:return _err("Invalid submission id.")
    c=get_connection();q=c.cursor()
    try:q.execute("SELECT first_name,last_name,mobile_phone,email,zip,derived_state,age,gender,tobacco,mortgage_balance,code_word,intake_status,evidence_status,screening_status,contact_status,notification_status,consent_version,consent_status,trustedform_retained,received_at_utc,producer_license_number FROM leads WHERE submission_id=%s AND product_type='mortgage-protection'",(str(sid),));r=q.fetchone()
    finally:q.close();c.close()
    if not r:return _err("Lead not found.",404)
    keys=["first_name","last_name","phone","email","zip","state","age","gender","tobacco_use","mortgage_balance","code_word","intake_status","evidence_status","screening_status","contact_status","notification_status","consent_version","consent_status","trustedform_retained","received_at","producer_license_number"];v=list(r);v[19]=v[19].isoformat() if v[19] else None
    return jsonify({"status":"ok","lead":dict(zip(keys,v))})
