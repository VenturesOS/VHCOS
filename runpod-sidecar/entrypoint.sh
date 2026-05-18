#!/usr/bin/env bash
# VHC unified entrypoint — start vLLM + BGE sidecar under supervisord.
# Both processes are auto-restarted on failure. Logs land at /var/log/.
set -euo pipefail

echo "[vhc-runpod] starting supervisord (vLLM:${VHC_VLLM_PORT:-8000} + BGE:${VHC_SIDECAR_PORT:-8001})"
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/vhc.conf
