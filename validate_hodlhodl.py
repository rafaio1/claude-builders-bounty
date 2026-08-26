import os, hmac, hashlib, time, json, urllib.request
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("HODLHODL_API_KEY")
SECRET = os.getenv("HODLHODL_API_SECRET")

if not KEY or not SECRET:
    print("ERRO: Credenciais não encontradas no .env")
    exit(1)

def sign(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

nonce = str(int(time.time() * 1000))
payload = f"GET/api/v1/me{nonce}"
signature = sign(SECRET, payload)

req = urllib.request.Request("https://hodlhodl.com/api/v1/me")
req.add_header("X-Api-Key", KEY)
req.add_header("X-Api-Signature", signature)
req.add_header("X-Api-Nonce", nonce)

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        print(f"SUCESSO: Conectado como {data.get('email', 'N/A')} (ID: {data.get('id', 'N/A')})")
except urllib.error.HTTPError as e:
    print(f"FALHA: HTTP {e.code} - {e.reason}")
    try: print(e.read().decode())
    except: pass
except Exception as e:
    print(f"ERRO: {e}")
