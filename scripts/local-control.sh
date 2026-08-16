#!/usr/bin/env bash
set -euo pipefail

ROOT=/Agentic

UNIT_LOOP=agentic-loop.service
UNIT_IMPROVE_MAP=agentic-improve-map.service
UNIT_IMPROVE_MAP_TIMER=agentic-improve-map.timer
UNIT_IMPROVE_DEV=agentic-improve-dev.service
UNIT_IMPROVE_DEV_TIMER=agentic-improve-dev.timer
UNIT_IMPROVE_REVIEW=agentic-improve-review.service
UNIT_IMPROVE_REVIEW_TIMER=agentic-improve-review.timer
UNIT_INTEGRITY=agentic-integrity.service
UNIT_INTEGRITY_TIMER=agentic-integrity.timer

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
)
START_UNITS=(
  "${UNIT_LOOP}"
  "${UNIT_IMPROVE_MAP_TIMER}"
  "${UNIT_IMPROVE_DEV_TIMER}"
  "${UNIT_IMPROVE_REVIEW_TIMER}"
  "${UNIT_INTEGRITY_TIMER}"
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
  systemctl is-active --quiet "${UNIT_LOOP}" || die "${UNIT_LOOP} não iniciou"
  systemctl is-active --quiet "${UNIT_IMPROVE_MAP_TIMER}" || die "${UNIT_IMPROVE_MAP_TIMER} não iniciou"
  systemctl is-active --quiet "${UNIT_IMPROVE_DEV_TIMER}" || die "${UNIT_IMPROVE_DEV_TIMER} não iniciou"
  systemctl is-active --quiet "${UNIT_IMPROVE_REVIEW_TIMER}" || die "${UNIT_IMPROVE_REVIEW_TIMER} não iniciou"
  systemctl is-active --quiet "${UNIT_INTEGRITY_TIMER}" || die "${UNIT_INTEGRITY_TIMER} não iniciou"
  if [[ "$(systemctl show "${UNIT_INTEGRITY}" -p Result --value)" != success ]]; then
    echo "aviso: checagem de integridade falhou; veja data/integrity.json" >&2
  fi
  echo "ativos: ${UNIT_LOOP}"
  echo "improve: ${UNIT_IMPROVE_MAP_TIMER}, ${UNIT_IMPROVE_DEV_TIMER}, ${UNIT_IMPROVE_REVIEW_TIMER}"
  echo "integrity: ${UNIT_INTEGRITY_TIMER}"
}

stop_managed() {
  local unit
  local -a stop_order=(
    "${UNIT_INTEGRITY_TIMER}"
    "${UNIT_IMPROVE_REVIEW_TIMER}"
    "${UNIT_IMPROVE_DEV_TIMER}"
    "${UNIT_IMPROVE_MAP_TIMER}"
    "${UNIT_LOOP}"
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
  echo "loop e timers parados"
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
    printf '\n[timers]\n'
    systemctl list-timers --all --no-pager \
      "${UNIT_IMPROVE_MAP_TIMER}" \
      "${UNIT_IMPROVE_DEV_TIMER}" \
      "${UNIT_IMPROVE_REVIEW_TIMER}" \
      "${UNIT_INTEGRITY_TIMER}" || true
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
  journalctl -u "${UNIT_LOOP}" -u "${UNIT_IMPROVE_MAP}" -u "${UNIT_IMPROVE_DEV}" \
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
    install_units
    systemctl enable "${UNIT_LOOP}" \
      "${UNIT_IMPROVE_MAP_TIMER}" "${UNIT_IMPROVE_DEV_TIMER}" \
      "${UNIT_IMPROVE_REVIEW_TIMER}" "${UNIT_INTEGRITY_TIMER}"
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
        "${UNIT_IMPROVE_REVIEW_TIMER}" "${UNIT_INTEGRITY_TIMER}" 2>/dev/null || true
      for unit in "${DEPLOY_UNITS[@]}"; do
        rm -f "/etc/systemd/system/${unit}"
      done
      systemctl daemon-reload
      systemctl reset-failed >/dev/null 2>&1 || true
    fi
    echo "units removidas"
    ;;
  *)
    echo "uso: $0 {install|start|stop|restart|status|logs [linhas]|uninstall}" >&2
    exit 2
    ;;
esac
