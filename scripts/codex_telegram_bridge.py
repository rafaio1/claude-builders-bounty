#!/usr/bin/env python3
"""
Codex <-> Telegram Bidirectional Bridge v3 (Fixed Parsing).
- Polls Telegram and injects messages into Codex TTY using CR line ending.
- Tails Codex rollout JSONL, correctly parses stringified payloads, and sends to Telegram.
"""
import sys, os, json, time, ast, re
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

sys.path.insert(0, "/Agentic/src")
from telegram_ops import send_message, poll_and_dispatch, _log, load_state, save_state

CODEX_PID = 668289
TTY_PATH = "/dev/pts/4"
ROLLOUT_LOG = "/root/.codex/sessions/2026/08/29/rollout-2026-08-29T02-29-06-01a04b59-6c70-7261-aa39-27f445619e5c.jsonl"
STATE_FILE = Path("/Agentic/data/telegram_bridge_state.json")
POLL_INTERVAL = 10

def load_bridge_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: pass
    return {"last_log_offset": 0}

def save_bridge_state(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st))

def inject_to_tty(text: str):
    if not os.path.exists(TTY_PATH):
        _log(f"TTY {TTY_PATH} not found", "ERROR")
        return False
    try:
        fd = os.open(TTY_PATH, os.O_WRONLY | os.O_NOCTTY)
        try:
            data = (text + "\r").encode("utf-8")
            os.write(fd, data)
            _log(f"Injected {len(text)} chars to {TTY_PATH}")
            return True
        finally:
            os.close(fd)
    except Exception as e:
        _log(f"TTY injection failed: {e}", "ERROR")
        return False

def on_telegram_message(text: str):
    if not text.strip(): return
    _log(f"TG->Codex: {text[:80]}")
    inject_to_tty(text)

def safe_parse_payload(payload_val):
    """Payload in rollout is often a stringified Python dict, not JSON."""
    if isinstance(payload_val, dict):
        return payload_val
    if isinstance(payload_val, str):
        try:
            return json.loads(payload_val)
        except:
            try:
                return ast.literal_eval(payload_val)
            except:
                return {}
    return {}

def tail_rollout_and_notify():
    st = load_bridge_state()
    offset = st.get("last_log_offset", 0)
    
    if not os.path.exists(ROLLOUT_LOG):
        return
    
    try:
        size = os.path.getsize(ROLLOUT_LOG)
        if size < offset: offset = 0
        if size == offset: return
            
        with open(ROLLOUT_LOG, "rb") as f:
            f.seek(offset)
            new_data = f.read()
            new_offset = f.tell()
        
        lines = new_data.decode("utf-8", errors="replace").splitlines()
        for line in lines:
            if not line.strip(): continue
            try:
                obj = json.loads(line)
                t = obj.get("type")
                payload = safe_parse_payload(obj.get("payload"))
                
                # Notify on assistant text responses
                if t == "response_item" and payload.get("type") == "message":
                    contents = payload.get("content", [])
                    texts = []
                    for c in contents:
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            txt = c.get("text", "").strip()
                            if txt and len(txt) > 10:
                                texts.append(txt)
                    if texts:
                        combined = "\n".join(texts)[:3000]
                        # Escape HTML special chars for Telegram
                        safe_combined = combined.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        send_message(f"🤖 <b>Codex:</b>\n{safe_combined}", silent=True)
                        
                # Notify on tool calls (transparency)
                elif t == "response_item" and payload.get("type") == "function_call":
                    name = payload.get("name", "?")
                    args_raw = payload.get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        cmd_preview = args.get("cmd", "")[:100] or str(args)[:100]
                    except:
                        cmd_preview = str(args_raw)[:100]
                    send_message(f"⚙️ <i>Executando:</i> <code>{name}</code>\n{cmd_preview}", silent=True)
                    
            except Exception as e:
                pass
                
        st["last_log_offset"] = new_offset
        save_bridge_state(st)
        
    except Exception as e:
        _log(f"Rollout tail error: {e}", "ERROR")

def main():
    _log("=== Codex-Telegram Bridge v3 Started ===")
    _log(f"PID target: {CODEX_PID}, TTY: {TTY_PATH}")
    
    st = load_bridge_state()
    if st.get("last_log_offset", 0) == 0 and os.path.exists(ROLLOUT_LOG):
        st["last_log_offset"] = os.path.getsize(ROLLOUT_LOG)
        save_bridge_state(st)
        _log(f"Initialized log offset to {st['last_log_offset']}")
    
    while True:
        try:
            if not os.path.exists(f"/proc/{CODEX_PID}"):
                _log(f"Codex PID {CODEX_PID} not found, waiting...", "WARN")
                time.sleep(30)
                continue
                
            poll_and_dispatch(handler=on_telegram_message)
            tail_rollout_and_notify()
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            _log(f"Bridge loop error: {e}", "ERROR")
            
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
