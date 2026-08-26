import os, json, urllib.request
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("ROBOSATS_TOKEN")
BASE_URL = os.getenv("ROBOSATS_BASE_URL", "https://robosats.com")

if not TOKEN:
    print("ERRO: ROBOSATS_TOKEN não encontrado no .env")
    exit(1)

req = urllib.request.Request(f"{BASE_URL}/api/account/info/")
req.add_header("Authorization", f"Token {TOKEN}")
req.add_header("Accept", "application/json")

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
        print(f"SUCESSO: Conectado à RoboSats")
        print(f"  Nickname: {data.get('nickname', 'N/A')}")
        print(f"  Balance: {data.get('balance_sats', 0)} sats")
        print(f"  Active Orders: {data.get('active_orders', 0)}")
except urllib.error.HTTPError as e:
    body = ""
    try: body = e.read().decode()
    except: pass
    print(f"FALHA: HTTP {e.code} - {e.reason}")
    if body: print(f"  Resposta: {body[:200]}")
except Exception as e:
    print(f"ERRO: {e}")
