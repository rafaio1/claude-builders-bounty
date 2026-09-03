#!/usr/bin/env python3
"""Persistent single-consumer Telegram bridge for Agentic."""
from __future__ import annotations
import argparse, fcntl, hashlib, json, os, re, subprocess, sys, time
import urllib.error, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path("/Agentic")
STATE_FILE=ROOT/"state/telegram_bridge_state.json"
LOCK_FILE=Path("/run/agentic-telegram/bridge.lock")
COMMAND_LOCK_FILE=Path("/run/agentic-telegram/user-commands.lock")
INBOX_FILE=ROOT/"data/aro/inbox/user_commands.jsonl"
RECOVERY_OUTBOX=ROOT/"data/aro/inbox/notifications_outbox.jsonl"
EMAIL_OUTBOX=ROOT/"data/aro/inbox/email_outbox.jsonl"
REALIZED_LEDGER=ROOT/"data/aro/realized_revenue_ledger.jsonl"
BOUNTY_LEDGER=ROOT/"data/aro/bounty_receive_ledger.json"
TG_TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
TG_CHAT=os.environ.get("TELEGRAM_CHAT_ID","").strip()
TG_USER=(os.environ.get("TELEGRAM_USER_ID","").strip() or TG_CHAT)
TG_USERNAME=os.environ.get("TELEGRAM_USERNAME","rafaio1").strip().lower()
LLM_BASE=os.environ.get("AGENTIC_LLM_BASE_URL","http://127.0.0.1:8787/v1").rstrip("/")
LLM_KEY=os.environ.get("APIFABLE_API_KEY","").strip()
LLM_MODEL=os.environ.get("AGENTIC_LLM_MODEL","ghostcli-auto[1m]").strip()
RECOVERY_EMAIL=os.environ.get("BOUNTY_RECOVERY_EMAIL","rafaelantunes137@gmail.com").strip()
DEFAULT_STATE={"schema_version":5,"offset":0,"seen_settlements":[],"seen_notifications":[],"suppressed_notifications":[],"last_critical":{},
  "updated_at":None,"last_poll_ok_at":None,"last_error_at":None,"last_error_type":None,"consecutive_errors":0}
POLICY_COMMANDS={(869013124,1779),(869013125,1781)}
RTC_BRIDGE_REPO="Scottcjn/Rustchain"
RTC_BRIDGE_ISSUE_NUMBER=8316
RTC_BRIDGE_ISSUE_URL="https://github.com/Scottcjn/Rustchain/issues/8316"
RTC_BRIDGE_ASSOCIATIONS={"OWNER","MEMBER","COLLABORATOR"}
RTC_BRIDGE_FIELDS={
  "schema_version","notice_version","notice_id","event_id","event_type","alert_class","created_at",
  "action_required","human_action","informational","autonomous_recovery","terminal_blocked","funds_moved",
  "execution_enabled","execution_authorized","instruction_handling","bounty_key",
  "repo","issue_number","issue_url","comment_id","comment_url","comment_author",
  "author_association","comment_created_at","comment_updated_at","summary","comment_excerpt",
  "comment_excerpt_truncated","content_sha256","delivery_channels","delivery_policy",
}

def utcnow(): return datetime.now(timezone.utc).isoformat()
def log(msg): print(f"[{utcnow()}] TELEGRAM_BRIDGE: {msg}",flush=True)

def atomic_json(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); os.replace(tmp,path)

def atomic_text(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+f".{os.getpid()}.tmp")
    tmp.write_text(text,encoding="utf-8")
    os.chmod(tmp,0o600); os.replace(tmp,path)

def load_state():
    try: state={**DEFAULT_STATE,**json.loads(STATE_FILE.read_text(encoding="utf-8"))}
    except Exception: state=dict(DEFAULT_STATE)
    state["schema_version"]=5
    state["seen_settlements"]=list(state.get("seen_settlements") or [])[-10000:]
    state["seen_notifications"]=list(state.get("seen_notifications") or [])[-10000:]
    state["suppressed_notifications"]=list(state.get("suppressed_notifications") or [])[-10000:]
    state["last_critical"]=dict(state.get("last_critical") or {})
    return state

def save_state(state):
    state["updated_at"]=utcnow(); atomic_json(STATE_FILE,state)

def record_poll_error(state,error_type):
    state["last_error_at"]=utcnow()
    state["last_error_type"]=str(error_type)[:160]
    state["consecutive_errors"]=int(state.get("consecutive_errors") or 0)+1
    save_state(state)

def append_jsonl(path,item):
    path.parent.mkdir(parents=True,exist_ok=True)
    payload=(json.dumps(item,ensure_ascii=True,separators=(",",":"))+"\n").encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try: os.write(fd,payload); os.fsync(fd)
    finally: os.close(fd)
    os.chmod(path,0o600)

def api_request(method,data,timeout=35):
    if not TG_TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    req=urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/{method}",data=json.dumps(data).encode(),headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as response: result=json.load(response)
    if not isinstance(result,dict) or result.get("ok") is not True:
        description=result.get("description") if isinstance(result,dict) else None
        raise RuntimeError(str(description or "Telegram API error"))
    return result

def send_text_receipt(text):
    if not TG_CHAT or not TG_TOKEN: log("send blocked: missing credentials"); return None
    message_ids=[]
    try:
        for chunk in ([text[i:i+3900] for i in range(0,len(text),3900)] or [""]):
            response=api_request("sendMessage",{"chat_id":TG_CHAT,"text":chunk,"disable_web_page_preview":True},20)
            result=response.get("result")
            message_id=result.get("message_id") if isinstance(result,dict) else None
            response_chat=str((result.get("chat") or {}).get("id","")) if isinstance(result,dict) else ""
            if not isinstance(message_id,int) or isinstance(message_id,bool) or response_chat!=TG_CHAT:
                raise RuntimeError("invalid Telegram sendMessage receipt")
            message_ids.append(message_id)
        return {"message_ids":message_ids,"chunk_count":len(message_ids)}
    except Exception as exc: log(f"send failed: {type(exc).__name__}"); return None

def send_text(text):
    return send_text_receipt(text) is not None

def event_id(payload):
    if isinstance(payload,dict) and payload.get("alert_class") in {"wallet_recovery_ready","route_options_pending","rtc_bridge_operator_response"}:
        stable=str(payload.get("notice_id") or "").strip().lower()
        if len(stable)==64 and all(ch in "0123456789abcdef" for ch in stable): return stable
    raw=json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()

def clean_text(value):
    return "".join(ch for ch in value if ch in "\n\t" or ord(ch)>=32).strip()[:4000]

def update_message(update):
    if isinstance(update.get("message"),dict): return update["message"],"message"
    if isinstance(update.get("edited_message"),dict): return update["edited_message"],"edited_message"
    return {},"unsupported"

def attachment_types(message):
    known=("photo","document","audio","voice","video","video_note","animation","sticker","contact","location","venue","poll")
    return [name for name in known if message.get(name) is not None]

def command_text(message):
    text=clean_text(str(message.get("text") or message.get("caption") or ""))
    attachments=attachment_types(message)
    if text: return text
    if attachments: return "[anexo sem legenda: "+",".join(attachments)+"]"
    return ""

def valid_numeric_id(value):
    return re.fullmatch(r"[0-9]+",str(value or "")) is not None

def authorized(message):
    chat=str((message.get("chat") or {}).get("id",""))
    chat_type=str((message.get("chat") or {}).get("type") or "")
    sender=str((message.get("from") or {}).get("id",""))
    return (
      valid_numeric_id(TG_CHAT) and valid_numeric_id(TG_USER)
      and chat_type=="private" and chat==TG_CHAT and sender==TG_USER
    )

def command_row_authorized(row):
    chat_type=str(row.get("chat_type") or "private")
    return (
      valid_numeric_id(TG_CHAT) and valid_numeric_id(TG_USER)
      and chat_type=="private"
      and str(row.get("chat_id") or "")==TG_CHAT
      and str(row.get("sender_id") or "")==TG_USER
    )

def _read_command_rows():
    rows=[]
    if not INBOX_FILE.exists(): return rows
    for line in INBOX_FILE.read_text(encoding="utf-8",errors="ignore").splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict): rows.append(row)
        except Exception: pass
    return rows

def _write_command_rows(rows):
    atomic_text(INBOX_FILE,"".join(json.dumps(row,ensure_ascii=True,separators=(",",":"))+"\n" for row in rows))

def reconcile_policy_commands():
    """Authorize the exact private sender and close the two applied policy commands."""
    COMMAND_LOCK_FILE.parent.mkdir(parents=True,exist_ok=True)
    with COMMAND_LOCK_FILE.open("w",encoding="utf-8") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=_read_command_rows(); changed=False; pending_ack=[]
        for row in rows:
            allowed=command_row_authorized(row)
            if bool(row.get("execution_authorized"))!=allowed:
                row["execution_authorized"]=allowed; changed=True
            identity=(int(row.get("update_id") or 0),int(row.get("message_id") or 0))
            if allowed and identity in POLICY_COMMANDS:
                if row.get("processed") is not True or row.get("processing_result")!="autonomous_recovery_policy_applied":
                    row["processed"]=True
                    row["processed_at"]=utcnow()
                    row["processing_result"]="autonomous_recovery_policy_applied"
                    changed=True
                if not row.get("acknowledged_at"):
                    pending_ack.append(str(row.get("correlation_id") or ""))
        if changed:
            archive=ROOT/"data/aro/archive"
            archive.mkdir(parents=True,exist_ok=True)
            if INBOX_FILE.exists():
                stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup=archive/f"user_commands-pre-autonomous-policy-{stamp}-{os.getpid()}.jsonl"
                backup.write_bytes(INBOX_FILE.read_bytes()); os.chmod(backup,0o600)
            _write_command_rows(rows)
        return sorted(set(pending_ack))

def mark_policy_acknowledged(correlation_ids):
    wanted={str(value) for value in correlation_ids if value}
    if not wanted: return
    with COMMAND_LOCK_FILE.open("w",encoding="utf-8") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=_read_command_rows(); changed=False; now=utcnow()
        for row in rows:
            if str(row.get("correlation_id") or "") in wanted and not row.get("acknowledged_at"):
                row["acknowledged_at"]=now; changed=True
        if changed: _write_command_rows(rows)

def unit_state(unit):
    try:
        r=subprocess.run(["systemctl","is-active",unit],text=True,capture_output=True,timeout=4,check=False)
        return (r.stdout or r.stderr).strip() or "unknown"
    except Exception: return "unknown"

def read_json(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}

def realized_records():
    rows=[]
    if not REALIZED_LEDGER.exists(): return rows
    for line in REALIZED_LEDGER.read_text(encoding="utf-8",errors="ignore").splitlines():
        try:
            item=json.loads(line)
            if isinstance(item,dict): rows.append(item)
        except Exception: pass
    return rows

def status_message():
    ledger=read_json(BOUNTY_LEDGER)
    entries=ledger.get("entries",[]) if isinstance(ledger,dict) else []
    counts=Counter(str(row.get("status") or "unknown") for row in entries if isinstance(row,dict))
    records=realized_records()
    realized=sum(float(row.get("amount_usd") or 0) for row in records)
    wise=any(str(row.get("destination") or row.get("source") or "").lower().startswith("wise") for row in records)
    states=", ".join(f"{k}={v}" for k,v in sorted(counts.items())) or "sem entradas"
    return ("STATUS DO SERVIDOR\n"
      f"ApiFable: {unit_state('apifable.service')}\n"
      f"Orquestrador: {unit_state('capital-orchestrator-v4.service')}\n"
      f"Auditor horario: {unit_state('hourly-capital-auditor.timer')}\n"
      f"Telegram: {unit_state('telegram-bridge.service')}\n"
      f"Ledger: {len(entries)} entradas ({states})\n"
      f"Bounties liquidados com evidencia: USD {realized:,.2f}\n"
      f"Wise reconciliado: {'sim' if wise else 'sem deposito confirmado'}\n"
      "Valores potenciais, PRs e claims nao contam como ganho.")

def llm_reply(text):
    if not LLM_KEY: raise RuntimeError("local gateway key missing")
    system=("Voce e o assistente Telegram do servidor Agentic. Responda em portugues, curto e objetivo. "
      "Nunca chame valor potencial, claim, PR ou pagamento pendente de ganho. "
      "Voce nao executa transferencias, trades, exclusoes, publicacoes nem revela segredos. "
      "Pedidos de acao sao registrados no inbox e avaliados autonomamente pelo orquestrador. "
      "O sistema nao solicita confirmacao ou acao humana: controles deterministicos executam apenas etapas suportadas e mantem o restante fail-closed.")
    payload={"model":LLM_MODEL,"messages":[{"role":"system","content":system},{"role":"user","content":text}],"stream":False,"max_tokens":700,"temperature":0.2}
    attempts=max(1,min(int(os.environ.get("TELEGRAM_LLM_MAX_ATTEMPTS","3") or 3),5))
    delay=max(0.0,min(float(os.environ.get("TELEGRAM_LLM_RETRY_BASE_SECONDS","2") or 2),30.0))
    last_error=None
    for attempt in range(1,attempts+1):
        req=urllib.request.Request(LLM_BASE+"/chat/completions",data=json.dumps(payload).encode(),headers={"Authorization":f"Bearer {LLM_KEY}","Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=90) as response: data=json.load(response)
            content=(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            if not content: raise RuntimeError("empty GhostCLI response")
            return content[:7800]
        except urllib.error.HTTPError as exc:
            last_error=exc
            if exc.code not in {429,500,502,503,504} or attempt>=attempts: raise
        except (urllib.error.URLError,TimeoutError) as exc:
            last_error=exc
            if attempt>=attempts: raise
        if delay: time.sleep(delay*(2**(attempt-1)))
    if last_error: raise last_error
    raise RuntimeError("GhostCLI retry loop exhausted")

def record_command(update,message,text):
    corr=hashlib.sha256(f"{update.get('update_id')}:{message.get('message_id')}:{text}".encode()).hexdigest()[:24]
    sender=message.get("from") or {}
    _,source_update_type=update_message(update)
    row={"schema_version":3,"timestamp":utcnow(),"correlation_id":corr,
      "update_id":update.get("update_id"),"message_id":message.get("message_id"),
      "chat_id":str((message.get("chat") or {}).get("id","")),"chat_type":str((message.get("chat") or {}).get("type") or ""),
      "sender_id":str(sender.get("id","")),"sender_username":sender.get("username"),"text":text,
      "source_update_type":source_update_type,"edit_date":message.get("edit_date"),"attachment_types":attachment_types(message),
      "processed":False,"execution_authorized":authorized(message),"authorization_basis":"private_chat_numeric_ids",
      "processing_status":"queued","processing_attempts":0,"reply_status":"pending"}
    COMMAND_LOCK_FILE.parent.mkdir(parents=True,exist_ok=True)
    with COMMAND_LOCK_FILE.open("w",encoding="utf-8") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=_read_command_rows()
        for existing in rows:
            if (
              int(existing.get("update_id") or 0)==int(update.get("update_id") or 0)
              and int(existing.get("message_id") or 0)==int(message.get("message_id") or 0)
            ):
                return str(existing.get("correlation_id") or corr)
        if source_update_type=="edited_message":
            for existing in rows:
                if (
                  str(existing.get("chat_id") or "")==str(row.get("chat_id") or "")
                  and int(existing.get("message_id") or 0)==int(row.get("message_id") or 0)
                  and existing.get("processed") is not True
                ):
                    existing["processed"]=True
                    existing["processed_at"]=utcnow()
                    existing["processing_status"]="superseded_by_edit"
                    existing["processing_result"]="superseded_by_edited_message"
        rows.append(row); _write_command_rows(rows)
    return corr

def maybe_critical(state,key,text,cooldown=21600):
    now=int(time.time()); last=int((state.get("last_critical") or {}).get(key,0) or 0)
    if now-last<cooldown: return
    if send_text("BLOQUEIO CRITICO\n"+text):
        state.setdefault("last_critical",{})[key]=now; save_state(state)

def handle_message(update,state):
    message,_=update_message(update); text=command_text(message)
    if not text: return "ignored_no_text"
    if not authorized(message): log(f"unauthorized update ignored: {update.get('update_id')}"); return "ignored_unauthorized"
    record_command(update,message,text)
    return "queued"

def valid_settlement(row):
    try: amount=float(row.get("amount_usd") or 0); confirmations=int(row.get("confirmations") or 0)
    except Exception: return False
    return amount>0 and confirmations>=0 and bool(str(row.get("txid") or "").strip()) and str(row.get("source") or "")=="bounty_receive_ledger"

def scan_settlements(state):
    seen=set(state.get("seen_settlements") or []); changed=False
    for row in realized_records():
        eid=event_id(row)
        if eid in seen or not valid_settlement(row): continue
        msg=("GANHO LIQUIDADO CONFIRMADO\n"
          f"Ledger: {row.get('ledger_id')}\nBounty: {row.get('bounty_key')}\n"
          f"Valor: {float(row.get('amount_usd')):,.2f} {row.get('currency') or 'USD'}\n"
          f"Txid: {row.get('txid')}\nConfirmacoes: {row.get('confirmations')}\n"
          "Este valor tem evidencia de liquidacao; Wise so conta apos reconciliacao propria.")
        if send_text(msg): seen.add(eid); changed=True
    if changed: state["seen_settlements"]=sorted(seen)[-10000:]; save_state(state)

def notification_rows():
    rows=[]
    if not RECOVERY_OUTBOX.exists(): return rows
    for line in RECOVERY_OUTBOX.read_text(encoding="utf-8",errors="ignore").splitlines():
        try:
            item=json.loads(line)
            if isinstance(item,dict): rows.append(item)
        except Exception: pass
    return rows

def queue_email(item,eid,body):
    if EMAIL_OUTBOX.exists():
        for line in EMAIL_OUTBOX.read_text(encoding="utf-8",errors="ignore").splitlines():
            try:
                if json.loads(line).get("event_id")==eid: return False
            except Exception: pass
    alert_class=item.get("alert_class")
    if alert_class=="wallet_received": label="Recebimento em carteira"
    elif alert_class=="wallet_recovery_ready": label="Recuperacao segura da carteira"
    elif alert_class=="route_options_pending": label="Opcoes de rota ate Wise"
    elif alert_class=="rtc_bridge_operator_response": label="Resposta do operador RTC bridge"
    else: label="Trava real"
    if alert_class=="rtc_bridge_operator_response": target=f"{item.get('repo')}#{item.get('issue_number')}"
    else: target=item.get("bounty_key") if item.get("bounty_key") else item.get("wallet_id")
    append_jsonl(EMAIL_OUTBOX,{"schema_version":1,"event_id":eid,"created_at":utcnow(),"to":RECOVERY_EMAIL,
      "subject":f"{label}: {target}","body":body,"delivery_status":"queued"})
    return True

def transaction_refs(item):
    refs=[]
    if str(item.get("txid") or "").strip(): refs.append(str(item.get("txid")).strip())
    if isinstance(item.get("txids"),list):
        refs.extend(str(value).strip() for value in item["txids"] if str(value).strip())
    return list(dict.fromkeys(refs))

def valid_wallet_received_event(item):
    try: amount=float(item.get("amount") or 0)
    except Exception: return False
    evidence=item.get("wallet_history_url") or item.get("wallet_history_evidence")
    return (
      item.get("alert_class")=="wallet_received"
      and item.get("terminal_blocked") is not True
      and str(item.get("status") or "")=="wallet_received"
      and amount>0
      and bool(str(item.get("asset") or "").strip())
      and bool(str(item.get("network") or "").strip())
      and bool(str(item.get("receive_address") or "").strip())
      and bool(transaction_refs(item))
      and bool(evidence)
    )

def valid_hard_block_event(item):
    blockers=item.get("blockers")
    return (
      item.get("alert_class")=="hard_block"
      and item.get("terminal_blocked") is True
      and isinstance(blockers,list) and bool(blockers)
      and all(isinstance(row,dict) and bool(row.get("type")) and bool(row.get("evidence")) for row in blockers)
    )

def forbidden_recovery_notice_keys(value):
    forbidden={"private_key","privatekey","privkey","secret_key","secretkey","mnemonic","seed","seed_phrase",
      "password","api_secret","recovery_key","master_key","keypair","ciphertext","nonce"}
    if isinstance(value,dict):
        for key,child in value.items():
            lowered=str(key).lower()
            if lowered in forbidden or lowered.endswith("_b64") or forbidden_recovery_notice_keys(child): return True
    elif isinstance(value,list):
        return any(forbidden_recovery_notice_keys(child) for child in value)
    return False

def is_hex64(value):
    return isinstance(value,str) and len(value)==64 and value==value.lower() and all(ch in "0123456789abcdef" for ch in value)

def canonical_utc_datetime(value):
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z",value): return None
    try: parsed=datetime.fromisoformat(value[:-1]+"+00:00")
    except ValueError: return None
    return parsed if parsed.tzinfo==timezone.utc else None

def valid_canonical_utc(value):
    return canonical_utc_datetime(value) is not None

def valid_github_login(value):
    return (
      isinstance(value,str) and len(value)<=39 and "--" not in value
      and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?",value) is not None
    )

def valid_bounded_text(value,limit,allow_newlines=True):
    return (
      isinstance(value,str) and bool(value) and len(value)<=limit and value==clean_text(value)
      and (allow_newlines or "\n" not in value)
    )

def valid_rtc_bridge_operator_response_event(item):
    if not isinstance(item,dict) or set(item)!=RTC_BRIDGE_FIELDS: return False
    notice_id=item.get("notice_id")
    content_sha256=item.get("content_sha256")
    comment_id=item.get("comment_id")
    channels=item.get("delivery_channels")
    comment_created_at=canonical_utc_datetime(item.get("comment_created_at"))
    comment_updated_at=canonical_utc_datetime(item.get("comment_updated_at"))
    expected_comment_url=f"{RTC_BRIDGE_ISSUE_URL}#issuecomment-{comment_id}"
    return (
      item.get("schema_version")==1
      and item.get("notice_version")=="rtc_bridge_operator_response_v1"
      and is_hex64(notice_id) and item.get("event_id")==notice_id
      and item.get("event_type")=="rtc_bridge_operator_response"
      and item.get("alert_class")=="rtc_bridge_operator_response"
      and valid_canonical_utc(item.get("created_at"))
      and item.get("action_required") is False and item.get("human_action")=="none"
      and item.get("informational") is True and item.get("autonomous_recovery") is True
      and item.get("terminal_blocked") is False
      and item.get("funds_moved") is False and item.get("execution_enabled") is False
      and item.get("execution_authorized") is False
      and item.get("instruction_handling")=="display_only_never_execute"
      and item.get("bounty_key")=="github|Scottcjn/Rustchain|8316"
      and item.get("repo")==RTC_BRIDGE_REPO and item.get("issue_number")==RTC_BRIDGE_ISSUE_NUMBER
      and item.get("issue_url")==RTC_BRIDGE_ISSUE_URL
      and isinstance(comment_id,int) and not isinstance(comment_id,bool) and comment_id>0
      and item.get("comment_url")==expected_comment_url
      and valid_github_login(item.get("comment_author"))
      and item.get("author_association") in RTC_BRIDGE_ASSOCIATIONS
      and comment_created_at is not None and comment_updated_at is not None
      and comment_updated_at>=comment_created_at
      and valid_bounded_text(item.get("summary"),240,False)
      and valid_bounded_text(item.get("comment_excerpt"),1000,True)
      and isinstance(item.get("comment_excerpt_truncated"),bool)
      and is_hex64(content_sha256)
      and isinstance(channels,list) and len(channels)==2 and set(channels)=={"telegram","email"}
      and item.get("delivery_policy")=="required_idempotent"
      and not forbidden_recovery_notice_keys(item)
    )

def valid_wallet_recovery_ready_event(item):
    fingerprint=str(item.get("recovery_bundle_fingerprint") or "").lower()
    notice_id=str(item.get("notice_id") or "").lower()
    instructions=item.get("recovery_instructions")
    channels=item.get("delivery_channels")
    return (
      item.get("alert_class")=="wallet_recovery_ready"
      and item.get("event_type")=="wallet_recovery_ready"
      and len(notice_id)==64 and all(ch in "0123456789abcdef" for ch in notice_id)
      and item.get("terminal_blocked") is False
      and item.get("role")=="client_receive_self_custody"
      and item.get("receive_ready") is True
      and bool(str(item.get("wallet_id") or "").strip())
      and bool(str(item.get("rail_id") or "").strip())
      and bool(str(item.get("asset") or "").strip())
      and bool(str(item.get("network") or "").strip())
      and bool(str(item.get("receive_address") or "").strip())
      and item.get("recovery_status")=="verified_encrypted_server_local"
      and len(fingerprint)==64 and all(ch in "0123456789abcdef" for ch in fingerprint)
      and isinstance(instructions,list) and len(instructions)>=3
      and all(isinstance(step,str) and bool(step.strip()) for step in instructions)
      and isinstance(channels,list) and {"telegram","email"}.issubset(set(channels))
      and item.get("delivery_policy")=="required_idempotent"
      and not forbidden_recovery_notice_keys(item)
    )

def valid_route_options_pending_event(item):
    notice_id=str(item.get("notice_id") or "").lower()
    evidence=item.get("evidence")
    reasons=item.get("reason_codes")
    options=item.get("route_options")
    channels=item.get("delivery_channels")
    if not isinstance(evidence,dict): return False
    fingerprints=(evidence or {}).get("wallet_registry_fingerprint"), (evidence or {}).get("wallet_audit_fingerprint")
    return (
      item.get("alert_class")=="route_options_pending"
      and item.get("event_type")=="route_options_pending"
      and len(notice_id)==64 and all(ch in "0123456789abcdef" for ch in notice_id)
      and item.get("status")=="route_pending" and item.get("route_status")=="route_pending"
      and item.get("terminal_blocked") is False and item.get("never_rejects_bounty") is True
      and item.get("role")=="client_receive_self_custody" and item.get("receive_ready") is True
      and bool(str(item.get("wallet_id") or "").strip())
      and bool(str(item.get("asset") or "").strip())
      and bool(str(item.get("network") or "").strip())
      and bool(str(item.get("receive_address") or "").strip())
      and isinstance(reasons,list) and len(reasons)>=3 and all(isinstance(reason,str) and reason for reason in reasons)
      and isinstance(options,list) and bool(options)
      and all(
        isinstance(option,dict) and bool(option.get("option_id"))
        and isinstance(option.get("stages"),list) and len(option["stages"])>=4
        and isinstance(option.get("evidence_required"),list) and bool(option["evidence_required"])
        and isinstance(option.get("cost_inputs_required"),list) and bool(option["cost_inputs_required"])
        and isinstance(option.get("risks"),list) and bool(option["risks"])
        for option in options
      )
      and isinstance(evidence,dict) and evidence.get("status")=="not_end_to_end_verified"
      and all(len(str(value or ""))==64 and all(ch in "0123456789abcdef" for ch in str(value)) for value in fingerprints)
      and item.get("execution_enabled") is False
      and item.get("execution_policy")=="automatic_only_after_all_technical_legal_destination_asset_network_and_fee_gates"
      and item.get("settlement_policy")=="never_before_wise_confirmation_and_reconciliation"
      and isinstance(channels,list) and {"telegram","email"}.issubset(set(channels))
      and item.get("delivery_policy")=="required_idempotent"
      and not forbidden_recovery_notice_keys(item)
    )

def valid_recovery_event(item):
    common=(
      isinstance(item,dict)
      and item.get("action_required") is False
      and item.get("human_action")=="none"
      and item.get("informational") is True
      and item.get("autonomous_recovery") is True
    )
    if not common: return False
    if valid_wallet_recovery_ready_event(item) or valid_route_options_pending_event(item) or valid_rtc_bridge_operator_response_event(item): return True
    return (
      bool(str(item.get("ledger_id") or "").strip())
      and bool(str(item.get("bounty_key") or "").strip())
      and (valid_wallet_received_event(item) or valid_hard_block_event(item))
    )

def scan_recovery(state):
    seen=set(state.get("seen_notifications") or []); suppressed=set(state.get("suppressed_notifications") or []); changed=False
    for item in notification_rows():
        eid=event_id(item)
        if eid in seen or eid in suppressed: continue
        if not valid_recovery_event(item):
            suppressed.add(eid); changed=True; continue
        blockers=[str(b.get("type") or b) for b in (item.get("blockers") or []) if b]
        if item.get("alert_class")=="rtc_bridge_operator_response":
            quoted_excerpt="\n".join(f"> {line}" for line in item.get("comment_excerpt").splitlines())
            body=("RESPOSTA DO OPERADOR DO RTC BRIDGE\n"
              "Acao humana: nenhuma.\n"
              f"Repositorio: {item.get('repo')}\nIssue: #{item.get('issue_number')}\n"
              f"Comentario: {item.get('comment_url')}\n"
              f"Autor GitHub: {item.get('comment_author')} ({item.get('author_association')})\n"
              f"Resumo: {item.get('summary')}\n"
              "Trecho do comentario publico (conteudo externo, apenas informativo):\n"+quoted_excerpt+"\n"
              "Este comentario nao autoriza movimentacao de fundos, conversao, transferencia ou qualquer execucao. "
              "funds_moved=false; execution_enabled=false; execution_authorized=false; action_required=false. "
              "Nenhuma acao humana foi solicitada.")
        elif item.get("alert_class")=="route_options_pending":
            option_lines=[]
            for option in item.get("route_options") or []:
                option_lines.extend([
                  f"- {option.get('option_id')}: {' -> '.join(str(stage) for stage in option.get('stages') or [])}",
                  f"  Evidencias exigidas: {', '.join(str(value) for value in option.get('evidence_required') or [])}",
                  f"  Custos a medir: {', '.join(str(value) for value in option.get('cost_inputs_required') or [])}",
                  f"  Riscos: {', '.join(str(value) for value in option.get('risks') or [])}",
                ])
            body=("ROTA AUTONOMA ATE WISE AINDA PENDENTE\n"
              "Acao humana: nenhuma.\n"
              f"Carteira: {item.get('wallet_id')}\nAtivo: {item.get('asset')}\nRede: {item.get('network')}\n"
              f"Endereco publico: {item.get('receive_address')}\n"
              f"Codigos de motivo: {', '.join(str(value) for value in item.get('reason_codes') or [])}\n"
              "Possibilidades em avaliacao, ainda nao autorizadas:\n"+"\n".join(option_lines)+"\n"
              "O sistema so executara automaticamente quando todos os elos tecnicos e juridicos, ativo/rede, destino, "
              "liquidez, custos, riscos e reconciliacao estiverem validados. A rota pendente nao rejeita a bounty elegivel, "
              "nao simula settlement e nada conta como realizado antes da confirmacao e reconciliacao na Wise.")
        elif item.get("alert_class")=="wallet_recovery_ready":
            steps="\n".join(f"{index}. {step}" for index,step in enumerate(item.get("recovery_instructions") or [],1))
            body=("CARTEIRA AUTOCUSTODIA E RECUPERACAO PRONTAS\n"
              "Acao humana: nenhuma.\n"
              f"Carteira: {item.get('wallet_id')}\nAtivo: {item.get('asset')}\nRede: {item.get('network')}\n"
              f"Endereco publico: {item.get('receive_address')}\n"
              f"Comprovante do pacote protegido: {item.get('recovery_bundle_fingerprint')}\n"
              "Recuperacao autonoma:\n"+steps+"\n"
              "Esta mensagem contem somente identificadores publicos, um comprovante criptografico e instrucoes do controlador; "
              "credenciais de custodia permanecem exclusivamente no servidor. "
              "Bybit sera consultada apenas como destino dinamico posterior e nunca decide a elegibilidade da bounty.")
        elif item.get("alert_class")=="wallet_received":
            refs=transaction_refs(item)
            body=("RECEBIMENTO EM CARTEIRA AUTOCUSTODIA CONFIRMADO\n"
              "Acao humana: nenhuma.\n"
              f"Ledger: {item.get('ledger_id')}\nBounty: {item.get('bounty_key')}\n"
              f"Recebido: {item.get('amount')} {item.get('asset')}\nRede: {item.get('network')}\n"
              f"Carteira publica: {item.get('receive_address')}\nTxid(s): {', '.join(refs)}\n"
              "A bounty foi recebida. A conversao e o destino Bybit permanecem etapas posteriores dinamicas; "
              "ausencia de suporte da exchange nao rejeita nem desfaz o recebimento. Wise so conta apos reconciliacao propria.")
        else:
            body=("TRAVA REAL DE BOUNTY\n"
              "Acao humana: nenhuma.\n"
              f"Ledger: {item.get('ledger_id')}\nBounty: {item.get('bounty_key')}\nEstado: {item.get('status')}\n"
              f"Trava comprovada: {', '.join(blockers)}\n"
              "O sistema preservou a evidencia e continuara outras oportunidades automaticas. "
              "Falta de suporte da Bybit ou conversao pendente nunca e classificada como trava da bounty.")
        queue_email(item,eid,body)
        if send_text(body+"\nEmail informativo enfileirado automaticamente; o dispatcher autonomo repete o envio ate a entrega."):
            seen.add(eid); changed=True
    if changed:
        state["seen_notifications"]=sorted(seen)[-10000:]
        state["suppressed_notifications"]=sorted(suppressed)[-10000:]
        save_state(state)

def poll_once(state):
    result=api_request("getUpdates",{"offset":int(state.get("offset") or 0),"timeout":25,"allowed_updates":["message","edited_message"]},35)
    for update in result.get("result") or []:
        uid=int(update.get("update_id") or 0)
        try: outcome=handle_message(update,state)
        except Exception as exc:
            log(f"update {uid} durable queue failed: {type(exc).__name__}")
            raise
        state["offset"]=max(int(state.get("offset") or 0),uid+1)
        state["last_update_outcome"]=outcome
        save_state(state)
    state["last_poll_ok_at"]=utcnow()
    state["last_error_type"]=None
    state["consecutive_errors"]=0
    save_state(state)

def health():
    STATE_FILE.parent.mkdir(parents=True,exist_ok=True); INBOX_FILE.parent.mkdir(parents=True,exist_ok=True)
    checks={"telegram_token":bool(TG_TOKEN),"telegram_chat":valid_numeric_id(TG_CHAT),"telegram_user":valid_numeric_id(TG_USER),"private_gateway_key":bool(LLM_KEY),
      "state_parent":os.access(STATE_FILE.parent,os.W_OK),"inbox_parent":os.access(INBOX_FILE.parent,os.W_OK)}
    print(json.dumps(checks,sort_keys=True)); return 0 if all(checks.values()) else 1

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--health",action="store_true"); parser.add_argument("--once",action="store_true"); args=parser.parse_args()
    if args.health: return health()
    if not TG_TOKEN or not TG_CHAT: log("missing Telegram credentials"); return 2
    lock_handle=open(LOCK_FILE,"w",encoding="utf-8")
    try: fcntl.flock(lock_handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: log("another polling consumer owns the lock"); return 3
    state=load_state(); save_state(state); log(f"started offset={state.get('offset')} model={LLM_MODEL}")
    pending_policy_ack=reconcile_policy_commands()
    if pending_policy_ack:
        acknowledgement=("POLITICA DE RECEBIMENTO AUTONOMO APLICADA\n"
          "Acao humana: nenhuma.\n"
          "Bounties elegiveis recebem primeiro em carteira de autocustodia estavel. Bybit e apenas destino dinamico posterior. "
          "Estados pendentes ficam silenciosos; Telegram alerta apenas recebimento/pagamento confirmado ou trava real comprovada.")
        if send_text(acknowledgement): mark_policy_acknowledged(pending_policy_ack)
    while True:
        try: scan_settlements(state); scan_recovery(state); poll_once(state)
        except urllib.error.HTTPError as exc:
            record_poll_error(state,f"HTTPError:{exc.code}")
            if exc.code==409:
                maybe_critical(state,"telegram_conflict","Outro consumidor esta chamando getUpdates; aguardando.",3600); time.sleep(60)
            else: log(f"Telegram HTTP error: {exc.code}"); time.sleep(15)
        except Exception as exc:
            record_poll_error(state,type(exc).__name__)
            log(f"loop error: {type(exc).__name__}"); time.sleep(15)
        if args.once: break
        time.sleep(2)
    return 0
if __name__=="__main__": raise SystemExit(main())
