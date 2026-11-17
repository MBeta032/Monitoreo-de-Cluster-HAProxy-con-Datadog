#!/usr/bin/env bash
# Corre un escenario de Artillery en su contenedor (servicio "artillery" del perfil tools) y
# guarda el JSON en artillery/resultados/. Solo necesita Docker y Git Bash: nada de Python en el host.
#   bash artillery/ejecutar_pruebas.sh [escenario] [opciones extra de "artillery run"]
#   Ejemplos: bash artillery/ejecutar_pruebas.sh smoke-datadog
#             bash artillery/ejecutar_pruebas.sh pico-datadog
# normal, pico y pico-datadog inician sesión: necesitan JJ_EMAIL y JJ_PASSWORD en .env (ver .env.example).
# Para resumir el JSON en un CSV, el script imprime al final el comando de analizar_artillery.py en contenedor.
# Antes este archivo llamaba a cierre_hoy.py (Python en el host); esa campaña quedó como histórica
# (docs/cierre-jj-hoy.md) y no hace falta correrla para reproducir nada.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

escenario="${1:-normal}"
if [ "$#" -gt 0 ]; then shift; fi
escenario="${escenario%.yml}"
case "$escenario" in
  ''|*/*|*..*) echo "ERROR: escenario inválido: $escenario" >&2; exit 2 ;;
esac
[ -f "artillery/$escenario.yml" ] || { echo "ERROR: no existe artillery/$escenario.yml" >&2; exit 2; }

# Opciones de la campaña histórica (cierre_hoy.py): ya no aplican; se avisa en vez de pasárselas a Artillery.
for opcion in "$@"; do
  case "$opcion" in
    --tasa|--tasa=*|--duracion|--duracion=*|--patron|--patron=*|--base|--base=*|--solo-validar)
      echo "La opción $opcion era de la campaña histórica (docs/historico-jj/) y ya no se usa." >&2
      echo "Uso: bash artillery/ejecutar_pruebas.sh <escenario> [opciones de 'artillery run']" >&2
      echo "     Ej.: bash artillery/ejecutar_pruebas.sh smoke-datadog" >&2
      exit 2 ;;
  esac
done

# Git Bash en Windows convierte las rutas de Linux de los argumentos; se desactiva para docker.
export MSYS_NO_PATHCONV=1
mkdir -p artillery/resultados
salida="$escenario-$(date -u +%Y%m%dT%H%M%SZ).json"

echo "Escenario: artillery/$escenario.yml -> artillery/resultados/$salida"
docker compose --profile tools run --rm artillery run "$@" -o "/results/$salida" "/scripts/$escenario.yml"

echo
echo "Para resumirlo en CSV (Python dentro de un contenedor):"
echo "MSYS_NO_PATHCONV=1 docker run --rm -v \"\$(pwd -W 2>/dev/null || pwd):/repo\" -w /repo python:3.14-slim python artillery/analizar_artillery.py artillery/resultados/$salida"
