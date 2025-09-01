#!/usr/bin/env bash
set -e

echo "=== BOOT: print PHONE_ID/TOKEN from config and env ==="
python3 - << "PY"
import hashlib, os
try:
    import config
    cfg_id = getattr(config, "WHATSAPP_PHONE_ID", "")
    cfg_tok = getattr(config, "WHATSAPP_TOKEN", "")
except Exception as e:
    cfg_id, cfg_tok = "", ""
    print("config import error:", e)

env_id  = os.getenv("WHATSAPP_PHONE_ID","")
env_tok = os.getenv("WHATSAPP_TOKEN","")

def h(s): 
    return (hashlib.sha1(s.encode()).hexdigest()[:8] if s else "EMPTY")

print(f"[BOOT] PHONE_ID(config)={cfg_id or '(empty)'}  TOKEN_SHA1(config)={h(cfg_tok)}")
print(f"[BOOT] PHONE_ID(env)   ={env_id or '(empty)'}  TOKEN_SHA1(env)   ={h(env_tok)}")
PY

echo "=== WEB: launching Uvicorn ==="
exec uvicorn app1:app --host 0.0.0.0 --port 8080
