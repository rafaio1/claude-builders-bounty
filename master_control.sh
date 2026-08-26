#!/bin/bash
# ==============================================================================
# MASTER CONTROL SCRIPT & ARCHITECTURAL BLUEPRINT
# ==============================================================================
# PROPÓSITO: Este script é a fonte única da verdade para a infraestrutura de
# agentes autônomos. Ele serve tanto como documentação explícita para IAs/Humanos
# quanto como executável para gerenciar o ciclo de vida dos subagentes.
# ==============================================================================

# --- [1] DADOS GLOBAIS E INFRAESTRUTURA ---
GLOBAL_TARGET_USD=20000000
LINUX_ORCHESTRATOR_IP="179.198.117.31"
WINDOWS_EXECUTOR_IP="167.148.161.176"
CODEX_BIN="/root/.codex/packages/standalone/current/bin/codex"
ORCH_DIR="/Agentic/orchestrator"
SCRIPTS_DIR="/Agentic/scripts"
STATE_FILE="$ORCH_DIR/state.json"
LOG_FILE="$ORCH_DIR/central.log"

# --- [2] PORTAS E SERVIÇOS DE REDE ---
# 8787: API Orquestrador (Uvicorn/FastAPI)
# 8766: Portal UI (Python HTTP)
# 8767: Metrics/Health
# 11434: Ollama (Local LLM Fallback - localhost only)
# 8080: HTTP Server Temporário para Migração

# --- [3] CREDENCIAIS E SECRETS (INJETADAS VIA .env) ---
# BYBIT_API_KEY, BYBIT_API_SECRET
# BINANCE_API_KEY, BINANCE_API_SECRET
# GHOSTCLI_BASE_URL="https://ghostcli.dev"
# MT5_ACCOUNT="362244368", MT5_SERVER="XMGlobal-MT5 12", MT5_PASS="Primavera1@"

# ==============================================================================
# FUNÇÃO: EXIBIR BLUEPRINT COMPLETO (PARA IAs "BURRAS" OU HUMANOS)
# ==============================================================================
show_blueprint() {
    cat << 'BLUEPRINT'
# 🧠 ARQUITETURA DO ORQUESTRADOR CENTRAL (ORCA)

## 1. META GLOBAL
- Objetivo: Acumular 20.000.000 USD em ativos líquidos.
- Contas Alvo: Wise (Fiat), Bybit (Crypto Spot/Futures), Binance (Crypto Spot/Futures), OKX (Options/Perps), XM (Forex/CFD via MT5).
- Estratégia: Subagentes especializados operando em paralelo, coordenados via `state.json`.

## 2. INVENTÁRIO DE SUBAGENTES ATIVOS

| Nome do Agente      | Tipo       | Meta Parcial | Foco Principal                                     | Comando/Script Base                     |
|---------------------|------------|--------------|----------------------------------------------------|-----------------------------------------|
| bybit_futures       | Codex Ultra| 8M USD       | Perpétuos USDT-M, alavancagem, funding rate        | codex -p fable-ultra ...                |
| binance_futures     | Codex Ultra| 8M USD       | COIN-M/USDT-M, momentum, arb cross-exchange        | codex -p fable-ultra ...                |
| okx_futures         | Codex Ultra| 4M USD       | Volatilidade, opções, hedge                        | codex -p fable-ultra ...                |
| bybit_spot          | Python Nat | Suporte      | Scalping ultra-rápido (ciclos 30s), trailing stop  | subagent_trailing_unified.py bybit      |
| binance_spot        | Python Nat | Suporte      | Scalping spot, micro-caps, composto agressivo      | subagent_trailing_unified.py binance    |
| bugbounty           | Codex Ultra| 2M USD       | Caça de vulnerabilidades (HackerOne/Bugcrowd)      | codex -p fable-ultra ...                |
| pr_freelance        | Codex Ultra| 1M USD       | Contratos high-ticket, automação sob demanda       | codex -p fable-ultra ...                |
| wise_liquidity      | Codex Ultra| Fluxo        | Arbitragem fiat-crypto, ponte de capital           | codex -p fable-ultra ...                |
| revenue_monitor     | Python Nat | Auditoria    | Monitora PnL, saúde das APIs, logs de erro         | scripts/revenue_monitor.py              |
| scalper_daemon      | Python Nat | Executor     | Daemon de execução de ordens de baixa latência     | scripts/scalper_daemon.py               |
| bounty_engine       | Python Nat | Recon        | Scanner de programas de bug bounty                 | scripts/bounty_engine.py                |
| high_ticket_sniper  | Python Nat | Freelance    | Identifica e propõe contratos freelance caros      | scripts/high_ticket_sniper.py           |

## 3. FLUXO DE COMUNICAÇÃO
1. O `central.sh` (ou este script) lê o `state.json`.
2. Spawna os processos em background (`nohup ... &`).
3. Cada agente Codex tem acesso ao filesystem (`/Agentic/`) e às ferramentas (shell, web, MCP).
4. Agentes Python usam as libs `ccxt`, `requests`, `metaapi-cloud-sdk` para interagir com exchanges.
5. O `state.json` é o barramento de mensagens: agentes leem o saldo global e escrevem seu PnL individual.

## 4. ESTRUTURA DE DIRETÓRIOS
/Agentic/
├── orchestrator/       # PIDs, logs, state.json, scripts de spawn
├── scripts/            # Daemons Python (scalper, monitor, bounty)
├── revenue/            # Módulos de novas receitas (freelance, affiliate, saas)
├── wise_liquidity/     # Bridge fiat-crypto
├── tools/              # Ferramentas auxiliares (decision_router, ai_reviewer)
└── .env                # Secrets (API Keys, Tokens)

## 5. COMANDOS DE CONTROLE
- ./master_control.sh status    # Verifica PIDs e saúde
- ./master_control.sh stop      # Mata todos os agentes
- ./master_control.sh rebuild   # Para, limpa e reinicia tudo
- ./master_control.sh blueprint # Exibe este manifesto
BLUEPRINT
}

# ==============================================================================
# FUNÇÕES DE GERENCIAMENTO DE CICLO DE VIDA
# ==============================================================================

stop_all() {
    echo "[$(date -u)] Parando todos os agentes..." | tee -a "$LOG_FILE"
    pkill -9 -f "subagent_trailing_unified" 2>/dev/null || true
    pkill -9 -f "bounty_engine|high_ticket_sniper|scalper_daemon|revenue_monitor|polymarket|airdrop_farmer|autonomous_executor" 2>/dev/null || true

    # Encerrar sessões tmux dos agentes Codex
    for session in $(tmux list-sessions -F "#{session_name}" 2>/dev/null | grep "^codex_"); do
        tmux kill-session -t "$session" 2>/dev/null || true
        rm -f "$ORCH_DIR/${session#codex_}.tmux.json"
    done

    sleep 2
    echo "[$(date -u)] Todos os processos finalizados." | tee -a "$LOG_FILE"
}

spawn_codex_agent() {
    local NAME=$1
    local GOAL=$2
    local SESSION_NAME="codex_${NAME}"

    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "[$(date -u)] $NAME já está rodando em sessão tmux ($SESSION_NAME)" | tee -a "$LOG_FILE"
        return 0
    fi

    echo "[$(date -u)] Spawnando $NAME (Codex Ultra) em sessão persistente..." | tee -a "$LOG_FILE"

    tmux new-session -d -s "$SESSION_NAME"
    tmux send-keys -t "$SESSION_NAME" "\"$CODEX_BIN\" --dangerously-bypass-approvals-and-sandbox -c model_provider=\"ghostcli\" -c model=\"claude-sonnet-5[1m]\" -c model_reasoning_effort=\"medium\" -c model_providers.ghostcli.base_url=\"http://127.0.0.1:8787/v1\" \"$GOAL\"" C-m

    # Salvar metadata para reconexão pelo Orca
    echo "{\"session\":\"$SESSION_NAME\",\"goal\":\"$GOAL\",\"started\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$ORCH_DIR/${NAME}.tmux.json"
}

spawn_python_agent() {
    local NAME=$1
    local SCRIPT_PATH=$2
    local ARGS=$3
    local PID_FILE="$ORCH_DIR/${NAME}.pid"
    local AGENT_LOG="$ORCH_DIR/${NAME}.log"

    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "[$(date -u)] $NAME já está rodando (PID $(cat $PID_FILE))" | tee -a "$LOG_FILE"
        return 0
    fi

    echo "[$(date -u)] Spawnando $NAME (Python Nativo)..." | tee -a "$LOG_FILE"
    nohup python3 -u "$SCRIPT_PATH" $ARGS > "$AGENT_LOG" 2>&1 &
    echo $! > "$PID_FILE"
}

rebuild_all() {
    stop_all
    mkdir -p "$ORCH_DIR"
    
    # Inicializar state.json se não existir
    if [ ! -f "$STATE_FILE" ]; then
        cat > "$STATE_FILE" << 'STATEJSON'
{
    "target_usd": 20000000,
    "accounts": ["wise", "bybit", "binance", "okx", "xm"],
    "status": "active",
    "subagents": {}
}
STATEJSON
    fi

    echo "[$(date -u)] === INICIANDO RECONSTRUÇÃO COMPLETA ===" | tee -a "$LOG_FILE"

    # Trading Futures (Codex)
    spawn_codex_agent "bybit_futures" "Você é o subagente bybit_futures ULTRA. Trading de futuros perpétuos USDT-M na ByBit. Meta: 8M USD. Coordene-se via $STATE_FILE."
    spawn_codex_agent "binance_futures" "Você é o subagente binance_futures ULTRA. Trading de futuros COIN-M/USDT-M na Binance. Meta: 8M USD."
    spawn_codex_agent "okx_futures" "Você é o subagente okx_futures ULTRA. Futuros e opções na OKX. Meta: 4M USD."

    # Trading Spot (Python Nativo - Baixa Latência)
    spawn_python_agent "bybit_spot" "$ORCH_DIR/subagent_trailing_unified.py" "bybit"
    spawn_python_agent "binance_spot" "$ORCH_DIR/subagent_trailing_unified.py" "binance"

    # Geração de Receita (Codex)
    spawn_codex_agent "bugbounty" "Caça automatizada de bugs. Meta: 2M USD."
    spawn_codex_agent "pr_freelance" "Execução de tarefas de programação high-ticket. Meta: 1M USD."
    spawn_codex_agent "wise_liquidity" "Arbitragem fiat-crypto e gestão de fluxo."

    # Daemons de Suporte (Python)
    spawn_python_agent "revenue_monitor" "$SCRIPTS_DIR/revenue_monitor.py" ""
    spawn_python_agent "scalper_daemon" "$SCRIPTS_DIR/scalper_daemon.py" ""
    spawn_python_agent "bounty_engine" "$SCRIPTS_DIR/bounty_engine.py" ""
    spawn_python_agent "high_ticket_sniper" "$SCRIPTS_DIR/high_ticket_sniper.py" ""

    show_status
}

show_status() {
    echo ""
    echo "=========================================="
    echo "[$(date -u)] STATUS DO ORQUESTRADOR"
    echo "=========================================="

    # Sessões tmux persistentes (Codex)
    echo "📡 SESSÕES PERSISTENTES (TMUX):"
    tmux list-sessions -F "  ✅ #{session_name} (ativa desde #{session_created_string})" 2>/dev/null | grep "codex_" || echo "  Nenhuma sessão Codex ativa."
    echo ""

    # Processos Python nativos
    echo "🐍 DAEMONS PYTHON:"
    for pidfile in $ORCH_DIR/*.pid; do
        [ -f "$pidfile" ] || continue
        name=$(basename "$pidfile" .pid)
        pid=$(cat "$pidfile" 2>/dev/null)
        if kill -0 "$pid" 2>/dev/null; then
            echo "  ✅ $name (PID $pid)"
        else
            echo "  ❌ $name (morto)"
        fi
    done

    echo ""
    echo "💡 Visualizar agente: tmux attach -t codex_<nome>"
    echo "💡 Desanexar sem parar: Ctrl+B D"
    echo "=========================================="
}

# ==============================================================================
# ROTEADOR DE COMANDOS (CLI)
# ==============================================================================
case "$1" in
    blueprint)
        show_blueprint
        ;;
    rebuild)
        rebuild_all
        ;;
    stop)
        stop_all
        ;;
    status)
        show_status
        ;;
    *)
        echo "Uso: $0 {blueprint|rebuild|stop|status}"
        exit 1
        ;;
esac
