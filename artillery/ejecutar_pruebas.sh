#!/usr/bin/env bash
# Ejecutor parametrizable: requiere Python 3 en el host.
# Alternativa sin Python: docker compose run --rm artillery run /scripts/pico.yml -o /results/pico.json
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if python --version >/dev/null 2>&1; then
  PY=(python)
elif python3 --version >/dev/null 2>&1; then
  PY=(python3)
else
  PY=(py -3)
fi
escenario="${1:-normal}"
if [ "$#" -gt 0 ]; then shift; fi
exec "${PY[@]}" artillery/cierre_hoy.py correr --escenario "$escenario" "$@"
