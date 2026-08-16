# Agentic

Agentes GhostCLI com navegador, shell e env interna Bybit. A versão em execução é sempre `main`/`master`.

## Loop e autocrescimento

Três executores GhostCLI (map → develop → review) melhoram o próprio sistema, no mesmo modelo do BugHunter. Só o review faz merge na branch que o systemd está a correr e reinicia `agentic-loop.service`.

O loop **não** envia ordens Bybit (`AGENTIC_LIVE_TRADE=0`). ARO v1.0 corre em ciclos internos (`python -m agentic aro status`): sem propostas nem pagamentos até contas e destino de payout autorizados.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
scripts/local-control.sh install
.venv/bin/python -m agentic status
```

Detalhes: `improve/README.md` e `AGENTS.md`.
