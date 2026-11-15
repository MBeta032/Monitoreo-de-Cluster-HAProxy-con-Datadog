#!/usr/bin/env bash
# Guardar dentro de artillery/. Requiere Bash (Git Bash) y Python 3.9+.
# No inicia ni detiene HAProxy, los backends ni Datadog.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if python --version >/dev/null 2>&1; then
  PY=(python)
elif python3 --version >/dev/null 2>&1; then
  PY=(python3)
elif py -3 --version >/dev/null 2>&1; then
  PY=(py -3)
else
  printf '%s\n' 'ERROR: se requiere Python 3.' >&2
  exit 1
fi
exec "${PY[@]}" - "$@" <<'PYTHON_JJ'
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc():
    return datetime.now(timezone.utc).isoformat()


def phases(pattern, rate, base, seconds):
    if pattern == 'constante':
        return [{'name': 'Carga constante', 'duration': seconds, 'arrivalRate': rate}]
    if pattern == 'gradual':
        weights = [2, 1, 3, 1, 2]
        values = [(base, None), (base, rate), (rate, None), (rate, base), (base, None)]
        names = ['Calentamiento', 'Subida gradual', 'Meseta', 'Bajada gradual', 'Recuperacion']
    elif pattern == 'escalonado':
        weights = [2, 2, 3, 2]
        values = [(base, None), ((base + rate) // 2, None), (rate, None), (base, None)]
        names = ['Escalon inicial', 'Escalon intermedio', 'Escalon maximo', 'Recuperacion']
    else:
        weights = [4, 1, 4]
        values = [(base, None), (rate, None), (base, None)]
        names = ['Referencia', 'Pico repentino', 'Recuperacion']
    durations = [seconds * w // sum(weights) for w in weights]
    durations[-1] += seconds - sum(durations)
    result = []
    for name, duration, (arrival, ramp) in zip(names, durations, values):
        phase = {'name': name, 'duration': duration, 'arrivalRate': arrival}
        if ramp is not None:
            phase['rampTo'] = ramp
        result.append(phase)
    return result


def capture(command):
    p = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or 'Fallo: ' + command[0])
    return p.stdout


def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def check_compose(root, compose):
    # El JSON completo queda solo en memoria: no se imprime ni se guarda .env.
    config = json.loads(capture(compose + ['config', '--format', 'json']))
    service = config.get('services', {}).get('artillery')
    if not service or 'tools' not in service.get('profiles', []):
        raise RuntimeError('Artillery debe tener profiles: ["tools"] en docker-compose.yml.')
    for target, expected in [('/scripts', root / 'artillery'), ('/results', root / 'artillery/resultados')]:
        mounts = [v for v in service.get('volumes', []) if v.get('target') == target]
        if len(mounts) != 1 or mounts[0].get('type') != 'bind':
            raise RuntimeError('Falta el volumen bind ' + target)
        mount = mounts[0]
        if Path(mount.get('source', '')).resolve() != expected.resolve():
            raise RuntimeError('El volumen ' + target + ' apunta a otra carpeta.')
        if target == '/results' and mount.get('read_only', False):
            raise RuntimeError('/results debe permitir escritura.')
    if 'cluster-net' not in service.get('networks', {}):
        raise RuntimeError('Artillery debe estar en cluster-net.')
    running = set(capture(compose + ['ps', '--status', 'running', '--services']).split())
    missing = {'haproxy', 'backend1', 'backend2', 'backend3'} - running
    if missing:
        raise RuntimeError('Servicios no iniciados: ' + ', '.join(sorted(missing)))
    return service.get('image')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Carga JJ: conserva YAML y resultados anteriores.')
    parser.add_argument('escenario', choices=['normal', 'pico'])
    parser.add_argument('--tasa', type=int, help='Usuarios virtuales/s; maximo del patron')
    parser.add_argument('--duracion', type=int, help='Segundos totales de las fases, minimo 30')
    parser.add_argument('--patron', choices=['constante', 'gradual', 'escalonado', 'pico'])
    parser.add_argument('--base', type=int, help='Tasa baja; por defecto max(1, tasa // 5)')
    parser.add_argument('--solo-validar', action='store_true', help='Muestra el plan, sin Docker ni archivos nuevos')
    args = parser.parse_args(argv)
    rate = args.tasa if args.tasa is not None else (5 if args.escenario == 'normal' else 25)
    seconds = args.duracion if args.duracion is not None else (180 if args.escenario == 'normal' else 540)
    pattern = args.patron or ('constante' if args.escenario == 'normal' else 'gradual')
    base = args.base if args.base is not None else max(1, rate // 5)
    if rate < 1 or seconds < 30 or not 1 <= base <= rate:
        parser.error('tasa >= 1, duracion >= 30 y 1 <= base <= tasa')
    root = Path.cwd()
    source = root / 'artillery' / (args.escenario + '.yml')
    if not source.is_file() or not (root / 'docker-compose.yml').is_file():
        parser.error('Guarda este script dentro de artillery/ del proyecto.')
    overrides = {'config': {'target': 'http://haproxy:8080', 'phases': phases(pattern, rate, base, seconds)}}
    print(json.dumps(overrides, indent=2), flush=True)
    if args.solo_validar:
        print('PLAN VALIDADO. Sin Docker ni carga; la configuracion Compose aun no se ha comprobado.')
        return 0
    compose = ['docker', 'compose', '-f', str(root / 'docker-compose.yml'), '--profile', 'tools']
    try:
        image = check_compose(root, compose)
    except (RuntimeError, OSError, ValueError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_id = f'{args.escenario}-{pattern}-{rate}vu-{seconds}s-{stamp}-{uuid.uuid4().hex[:8]}'
    evidence = root / 'artillery/corridas' / run_id
    result = root / 'artillery/resultados' / (run_id + '.json')
    evidence.mkdir(parents=True, exist_ok=False)
    result.parent.mkdir(parents=True, exist_ok=True)
    if result.exists():
        raise RuntimeError('El resultado ya existe; no se sobrescribe.')
    shutil.copyfile(source, evidence / 'escenario.yml')
    write_new(evidence / 'overrides.json', overrides)
    container = 'jj-carga-' + uuid.uuid4().hex
    command = compose + ['run', '--rm', '--no-deps', '-T', '--name', container,
                         'artillery', 'run', f'/scripts/corridas/{run_id}/escenario.yml',
                         '--overrides', json.dumps(overrides, separators=(',', ':')),
                         '-o', '/results/' + result.name]
    fingerprints = {}
    for relative in [f'artillery/{source.name}', 'docker-compose.yml', 'haproxy/haproxy.cfg', 'backends/gunicorn.conf.py']:
        p = root / relative
        fingerprints[relative] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    meta = {'id': run_id, 'inicio_utc': utc(), 'escenario': args.escenario,
            'patron': pattern, 'tasa_vu_s': rate, 'base_vu_s': base,
            'duracion_fases_s': seconds, 'imagen_configurada': image,
            'sha256_archivos': fingerprints, 'resultado': result.name, 'comando': command,
            'nota': 'Configuracion local; no certifica configuracion efectiva ni salud del cluster.'}
    write_new(evidence / 'inicio.json', meta)
    print('INICIO: ' + meta['inicio_utc'] + '\nID: ' + run_id, flush=True)
    code, status, process = 1, 'error', None
    detail = None
    try:
        with (evidence / 'consola.log').open('x', encoding='utf-8') as log:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace')
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            code = process.wait()
        if code == 0:
            report = json.loads(result.read_text(encoding='utf-8-sig'))
            if not isinstance(report.get('aggregate', {}).get('counters'), dict):
                raise ValueError('El resultado no contiene aggregate.counters')
            status = 'proceso_completado'
            # HTTP 4xx/5xx y usuarios fallidos se evalúan con el analizador.
    except KeyboardInterrupt:
        code, status = 130, 'interrumpida'
        if process is not None:
            try:
                subprocess.run(['docker', 'stop', '--time', '10', container],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    except (OSError, ValueError, AttributeError) as exc:
        code, detail = 1, str(exc)
        print('ERROR: ' + detail, file=sys.stderr)
    finally:
        write_new(evidence / 'fin.json', {'id': run_id, 'fin_utc': utc(), 'estado': status,
                                        'codigo_salida': code, 'detalle': detail,
                                        'resultado_existe': result.is_file()})
    print('FIN: ' + status + '\nEvidencias: ' + str(evidence))
    if code == 0:
        print('JSON: ' + str(result))
        print('Proceso finalizado. Revisa codigos HTTP y usuarios fallidos con analizar_artillery.py.')
    return code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
PYTHON_JJ
