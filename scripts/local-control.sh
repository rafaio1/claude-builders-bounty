#!/usr/bin/env bash
set -euo pipefail

ROOT=/Agentic
PORTAL_RUNTIME=/opt/agentic-portal
PORTAL_STATE_DIR=/var/lib/agentic-portal
PORTAL_CRED_DIR=/etc/agentic-portal/credentials
PORTAL_USER=agentic-portal
PORTAL_GROUP=agentic-portal

UNIT_LOOP=agentic-loop.service
UNIT_IMPROVE_MAP=agentic-improve-map.service
UNIT_IMPROVE_MAP_TIMER=agentic-improve-map.timer
UNIT_IMPROVE_DEV=agentic-improve-dev.service
UNIT_IMPROVE_DEV_TIMER=agentic-improve-dev.timer
UNIT_IMPROVE_REVIEW=agentic-improve-review.service
UNIT_IMPROVE_REVIEW_TIMER=agentic-improve-review.timer
UNIT_INTEGRITY=agentic-integrity.service
UNIT_INTEGRITY_TIMER=agentic-integrity.timer
UNIT_PORTAL=agentic-portal.service
UNIT_PORTAL_SNAPSHOT=agentic-portal-snapshot.service
UNIT_PORTAL_SNAPSHOT_TIMER=agentic-portal-snapshot.timer

DEPLOY_UNITS=(
  "${UNIT_LOOP}"
  "${UNIT_IMPROVE_MAP}"
  "${UNIT_IMPROVE_MAP_TIMER}"
  "${UNIT_IMPROVE_DEV}"
  "${UNIT_IMPROVE_DEV_TIMER}"
  "${UNIT_IMPROVE_REVIEW}"
  "${UNIT_IMPROVE_REVIEW_TIMER}"
  "${UNIT_INTEGRITY}"
  "${UNIT_INTEGRITY_TIMER}"
  "${UNIT_PORTAL}"
  "${UNIT_PORTAL_SNAPSHOT}"
  "${UNIT_PORTAL_SNAPSHOT_TIMER}"
)
START_UNITS=(
  "${UNIT_LOOP}"
  "${UNIT_IMPROVE_MAP_TIMER}"
  "${UNIT_IMPROVE_DEV_TIMER}"
  "${UNIT_IMPROVE_REVIEW_TIMER}"
  "${UNIT_INTEGRITY_TIMER}"
  "${UNIT_PORTAL}"
  "${UNIT_PORTAL_SNAPSHOT_TIMER}"
)

die() {
  echo "erro: $*" >&2
  exit 1
}

has_systemd() {
  command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]
}

require_systemd() {
  has_systemd || die "systemd indisponível neste host"
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || die "este comando requer root"
}

unit_installed() {
  local unit="$1"
  has_systemd &&
    systemctl list-unit-files "${unit}" --no-legend --no-pager 2>/dev/null |
      awk -v expected="${unit}" '$1 == expected { found=1 } END { exit !found }'
}

provision_portal_identity() {
  local nologin_shell
  if ! getent group "${PORTAL_GROUP}" >/dev/null; then
    groupadd --system "${PORTAL_GROUP}"
  fi
  if ! id -u "${PORTAL_USER}" >/dev/null 2>&1; then
    nologin_shell="$(command -v nologin || true)"
    [[ -n "${nologin_shell}" ]] || nologin_shell=/usr/sbin/nologin
    useradd --system --gid "${PORTAL_GROUP}" --no-create-home \
      --home-dir /nonexistent --shell "${nologin_shell}" "${PORTAL_USER}"
  fi
  [[ "$(id -u "${PORTAL_USER}")" -ne 0 ]] || die "usuário do portal não pode ser root"
  install -d -o root -g "${PORTAL_GROUP}" -m 0750 "${PORTAL_STATE_DIR}"
  if [[ ! -f "${PORTAL_STATE_DIR}/inbox.jsonl" ]]; then
    install -o root -g "${PORTAL_GROUP}" -m 0660 /dev/null "${PORTAL_STATE_DIR}/inbox.jsonl"
  else
    chown root:"${PORTAL_GROUP}" "${PORTAL_STATE_DIR}/inbox.jsonl"
    chmod 0660 "${PORTAL_STATE_DIR}/inbox.jsonl"
  fi
}

write_secret_file() {
  local path="$1"
  local value="$2"
  local old_umask
  old_umask="$(umask)"
  umask 077
  printf '%s\n' "${value}" >"${path}"
  chown root:root "${path}"
  chmod 0600 "${path}"
  umask "${old_umask}"
}

provision_portal_credentials() {
  install -d -o root -g root -m 0700 "${PORTAL_CRED_DIR}"
  write_secret_file "${PORTAL_CRED_DIR}/portal_username" "rafaio"
  write_secret_file "${PORTAL_CRED_DIR}/portal_display_name" "Rafaio"
  if [[ -s "${PORTAL_CRED_DIR}/portal_password_hash" ]] &&
     grep -Eq '^\$argon2id\$' "${PORTAL_CRED_DIR}/portal_password_hash"; then
    echo "hash do portal já presente (não regenerado)"
    return 0
  fi
  [[ -n "${AGENTIC_PORTAL_BOOTSTRAP_PASSWORD:-}" ]] ||
    die "defina AGENTIC_PORTAL_BOOTSTRAP_PASSWORD só para criar o hash inicial"
  local hash
  hash="$(
    AGENTIC_PORTAL_BOOTSTRAP_PASSWORD="${AGENTIC_PORTAL_BOOTSTRAP_PASSWORD}" \
      "${ROOT}/.venv/bin/python" -I -c \
      'import os; from agentic.portal import hash_password; print(hash_password(os.environ["AGENTIC_PORTAL_BOOTSTRAP_PASSWORD"], algorithm="argon2id"))'
  )"
  unset AGENTIC_PORTAL_BOOTSTRAP_PASSWORD
  [[ "${hash}" == \$argon2id\$* ]] || die "falha a gerar Argon2id"
  write_secret_file "${PORTAL_CRED_DIR}/portal_password_hash" "${hash}"
  echo "credentials do portal gravadas (Argon2id; senha não persistida)"
}

provision_portal_runtime() {
  [[ -x "${ROOT}/.venv/bin/python" ]] || die "venv ausente em ${ROOT}/.venv"
  install -d -o root -g root -m 0755 "${PORTAL_RUNTIME}"
  python3 -m venv "${PORTAL_RUNTIME}/venv"
  PIP_DISABLE_PIP_VERSION_CHECK=1 "${PORTAL_RUNTIME}/venv/bin/pip" install \
    --no-input --upgrade --force-reinstall "${ROOT}"
  chmod 0755 "${PORTAL_RUNTIME}" "${PORTAL_RUNTIME}/venv"
  chmod -R a+rX "${PORTAL_RUNTIME}/venv"
  "${PORTAL_RUNTIME}/venv/bin/python" -I -c 'import argon2, jinja2, agentic.portal' >/dev/null ||
    die "runtime do portal incompleto"
  echo "runtime isolado do portal em ${PORTAL_RUNTIME}"
}

install_units() {
  local unit
  for unit in "${DEPLOY_UNITS[@]}"; do
    [[ -r "${ROOT}/deploy/${unit}" ]] || die "arquivo deploy ausente: ${ROOT}/deploy/${unit}"
    install -m 0644 "${ROOT}/deploy/${unit}" "/etc/systemd/system/${unit}"
  done
  systemctl daemon-reload
}

start_managed() {
  systemctl start "${UNIT_LOOP}"
  systemctl start "${UNIT_IMPROVE_MAP_TIMER}"
  systemctl start "${UNIT_IMPROVE_DEV_TIMER}"
  systemctl start "${UNIT_IMPROVE_REVIEW_TIMER}"
  systemctl start "${UNIT_INTEGRITY_TIMER}"
  systemctl start "${UNIT_INTEGRITY}" || true
  systemctl start "${UNIT_PORTAL_SNAPSHOT}"
  [[ "$(systemctl show "${UNIT_PORTAL_SNAPSHOT}" -p Result --value)" == success ]] ||
    echo "aviso: snapshot inicial do portal falhou" >&2
  systemctl start "${UNIT_PORTAL_SNAPSHOT_TIMER}"
  systemctl start "${UNIT_PORTAL}"
  systemctl is-active --quiet "${UNIT_LOOP}" || die "${UNIT_LOOP} não iniciou"
  systemctl is-active --quiet "${UNIT_PORTAL}" || die "${UNIT_PORTAL} não iniciou"
  systemctl is-active --quiet "${UNIT_PORTAL_SNAPSHOT_TIMER}" ||
    die "${UNIT_PORTAL_SNAPSHOT_TIMER} não iniciou"
  echo "ativos: ${UNIT_LOOP}, ${UNIT_PORTAL}"
  echo "improve: ${UNIT_IMPROVE_MAP_TIMER}, ${UNIT_IMPROVE_DEV_TIMER}, ${UNIT_IMPROVE_REVIEW_TIMER}"
  echo "integrity: ${UNIT_INTEGRITY_TIMER}"
  echo "portal: http://179.198.117.31:8767"
}

stop_managed() {
  local unit
  local -a stop_order=(
    "${UNIT_PORTAL}"
    "${UNIT_PORTAL_SNAPSHOT_TIMER}"
    "${UNIT_INTEGRITY_TIMER}"
    "${UNIT_IMPROVE_REVIEW_TIMER}"
    "${UNIT_IMPROVE_DEV_TIMER}"
    "${UNIT_IMPROVE_MAP_TIMER}"
    "${UNIT_LOOP}"
    "${UNIT_PORTAL_SNAPSHOT}"
    "${UNIT_INTEGRITY}"
    "${UNIT_IMPROVE_REVIEW}"
    "${UNIT_IMPROVE_DEV}"
    "${UNIT_IMPROVE_MAP}"
  )
  for unit in "${stop_order[@]}"; do
    if unit_installed "${unit}"; then
      systemctl stop "${unit}" || true
    fi
  done
  echo "loop, portal e timers parados"
}

show_status() {
  local unit
  if has_systemd; then
    for unit in "${DEPLOY_UNITS[@]}"; do
      if unit_installed "${unit}"; then
        printf '\n[%s]\n' "${unit}"
        systemctl --no-pager --full status "${unit}" || true
      else
        printf '\n[%s]\n' "${unit} não instalada"
      fi
    done
  else
    echo "systemd indisponível"
  fi
  printf '\n[aplicação]\n'
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    "${ROOT}/.venv/bin/python" -m agentic status || echo "status indisponível" >&2
  else
    echo "venv ausente"
  fi
}

show_logs() {
  local lines="${1:-80}"
  [[ "${lines}" =~ ^[0-9]+$ ]] || die "linhas deve ser numérico"
  journalctl -u "${UNIT_LOOP}" -u "${UNIT_PORTAL}" -u "${UNIT_PORTAL_SNAPSHOT}" \
    -u "${UNIT_IMPROVE_MAP}" -u "${UNIT_IMPROVE_DEV}" \
    -u "${UNIT_IMPROVE_REVIEW}" -u "${UNIT_INTEGRITY}" -n "${lines}" --no-pager
}

case "${1:-status}" in
  start)
    require_systemd
    require_root
    start_managed
    ;;
  stop)
    require_systemd
    require_root
    stop_managed
    ;;
  restart)
    require_systemd
    require_root
    stop_managed
    start_managed
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs "${2:-80}"
    ;;
  install)
    require_systemd
    require_root
    [[ -x "${ROOT}/.venv/bin/python" ]] || die "venv ausente em ${ROOT}/.venv"
    provision_portal_identity
    provision_portal_credentials
    provision_portal_runtime
    install_units
    systemctl enable "${UNIT_LOOP}" \
      "${UNIT_INTEGRITY_TIMER}" \
      "${UNIT_PORTAL}" "${UNIT_PORTAL_SNAPSHOT_TIMER}"
    # Improve timers condicionais: só habilitar se AGENTIC_IMPROVE_TIMERS_ENABLED=1
    # e worktree isolado validado. Por padrão, permanecem masked para evitar
    # reativação acidental durante concorrência com agentes Codex.
    if [[ "${AGENTIC_IMPROVE_TIMERS_ENABLED:-0}" == "1" ]]; then
      systemctl unmask "${UNIT_IMPROVE_MAP_TIMER}" "${UNIT_IMPROVE_DEV_TIMER}" "${UNIT_IMPROVE_REVIEW_TIMER}" 2>/dev/null || true
      systemctl enable "${UNIT_IMPROVE_MAP_TIMER}" "${UNIT_IMPROVE_DEV_TIMER}" "${UNIT_IMPROVE_REVIEW_TIMER}"
    fi
    stop_managed
    start_managed
    echo "instalação concluída; AGENTIC_LIVE_TRADE permanece 0"
    ;;
  uninstall)
    require_root
    if has_systemd; then
      stop_managed
      systemctl disable "${UNIT_LOOP}" \
        "${UNIT_IMPROVE_MAP_TIMER}" "${UNIT_IMPROVE_DEV_TIMER}" \
        "${UNIT_IMPROVE_REVIEW_TIMER}" "${UNIT_INTEGRITY_TIMER}" \
        "${UNIT_PORTAL}" "${UNIT_PORTAL_SNAPSHOT_TIMER}" 2>/dev/null || true
      for unit in "${DEPLOY_UNITS[@]}"; do
        rm -f "/etc/systemd/system/${unit}"
      done
      systemctl daemon-reload
      systemctl reset-failed >/dev/null 2>&1 || true
    fi
    echo "units removidas (credentials e /opt/agentic-portal preservados)"
    ;;
  *)
    echo "uso: $0 {install|start|stop|restart|status|logs [linhas]|uninstall}" >&2
    exit 2
    ;;
esac
