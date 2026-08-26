#!/bin/bash
# ==============================================================================
# TMUX ORCHESTRATOR - PERSISTENT SESSIONS FOR CODEX AGENTS
# ==============================================================================
# Permite que agentes rodem no servidor independentemente do Orca/cliente.
# O Orca pode reconectar a qualquer momento para visualizar ou interagir.
# Uso: ./tmux_orchestrator.sh {start|attach|list|stop} [agent_name]
# ==============================================================================

SESSION_PREFIX="codex"
ORCH_DIR="/Agentic/orchestrator"
CODEX_BIN="/root/.codex/packages/standalone/current/bin/codex"

start_agent() {
    local NAME=$1
    local GOAL=$2
    local SESSION_NAME="${SESSION_PREFIX}_${NAME}"
    
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "✅ Sessão $SESSION_NAME já existe."
        return 0
    fi
    
    echo "🚀 Iniciando sessão persistente: $SESSION_NAME"
    tmux new-session -d -s "$SESSION_NAME"
    tmux send-keys -t "$SESSION_NAME" "\"$CODEX_BIN\" --dangerously-bypass-approvals-and-sandbox -p fable-ultra -c model_provider=\"ghostcli\" -c model=\"claude-fable-5[1m]\" -c model_reasoning_effort=\"ultra\" \"$GOAL\"" C-m
    
    # Salvar metadata para reconexão pelo Orca
    echo "{\"session\":\"$SESSION_NAME\",\"goal\":\"$GOAL\",\"started\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$ORCH_DIR/${NAME}.tmux.json"
}

attach_agent() {
    local NAME=$1
    local SESSION_NAME="${SESSION_PREFIX}_${NAME}"
    
    if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "❌ Sessão $SESSION_NAME não encontrada."
        exit 1
    fi
    
    # Se estiver dentro do tmux, switch; senão attach
    if [ -n "$TMUX" ]; then
        tmux switch-client -t "$SESSION_NAME"
    else
        tmux attach-session -t "$SESSION_NAME"
    fi
}

list_sessions() {
    echo "=========================================="
    echo "📋 SESSÕES PERSISTENTES DO ORQUESTRADOR"
    echo "=========================================="
    tmux list-sessions -F "#{session_name} #{session_created_string} #{session_windows}" 2>/dev/null | grep "^${SESSION_PREFIX}_" || echo "Nenhuma sessão ativa."
    echo "=========================================="
    echo "💡 Para visualizar: ./tmux_orchestrator.sh attach <nome>"
    echo "💡 Ctrl+B D para desanexar sem parar o agente"
}

stop_agent() {
    local NAME=$1
    local SESSION_NAME="${SESSION_PREFIX}_${NAME}"
    
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        tmux kill-session -t "$SESSION_NAME"
        rm -f "$ORCH_DIR/${NAME}.tmux.json"
        echo "🛑 Sessão $SESSION_NAME encerrada."
    else
        echo "⚠️  Sessão $SESSION_NAME não encontrada."
    fi
}

case "$1" in
    start)
        start_agent "$2" "$3"
        ;;
    attach)
        attach_agent "$2"
        ;;
    list)
        list_sessions
        ;;
    stop)
        stop_agent "$2"
        ;;
    *)
        echo "Uso: $0 {start|attach|list|stop} [agent_name] [goal]"
        exit 1
        ;;
esac
