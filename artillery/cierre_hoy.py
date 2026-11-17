#!/usr/bin/env python3
"""Campaña de taquilla: preparar entorno, humo, cuatro criterios e informe.

Solo 'humo --con-reserva' y 'correr --operacion reserva' reservan sillas.
La campaña usa consultas autenticadas, conserva datos y restaura HAProxy.
"""
import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artillery'
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'), '--profile', 'tools']
CFG = ROOT / 'haproxy/haproxy.cfg'
RUNTIME = '/usr/local/etc/haproxy/haproxy.cfg'
ENV_NAMES = ('JJ_EMAIL', 'JJ_PASSWORD', 'JJ_EVENT_ID', 'JJ_OPERACION')


def utc():
    return datetime.now(timezone.utc).isoformat()


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, data, new=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if new else 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def env_values():
    values = {}
    p = ROOT / '.env'
    if p.exists():
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
            if match:
                value = match[2].strip()
                if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[match[1]] = value
    return values


def environment(operation='consulta'):
    # .env y variables privadas solo en memoria; no se guardan en evidencias.
    values = dict(os.environ)
    values.update(env_values())
    values['JJ_OPERACION'] = operation
    return values


def capture(command, check=True):
    p = subprocess.run(command, cwd=ROOT, env=environment(), capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=90)
    if check and p.returncode:
        # No propagar salidas que puedan contener valores interpolados de .env.
        raise RuntimeError('Fallo de comando ' + command[0] + '; comprueba Docker/Compose con config --quiet.')
    return p


def fingerprint():
    paths = ['docker-compose.yml', 'artillery/normal.yml', 'artillery/pico.yml',
             'artillery/taquilla.js', 'artillery/cierre_hoy.py']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'backends').rglob('*'))
              if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py', '.txt', '.html', '.js')]
    result = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
    values = environment()
    controls = {k: values.get(k, '2') for k in ('BACKEND1_WORKERS', 'BACKEND2_WORKERS', 'BACKEND3_WORKERS')}
    controls['JJ_EVENT_ID'] = values.get('JJ_EVENT_ID', '1')
    result['parametros_no_secretos'] = hashlib.sha256(json.dumps(controls, sort_keys=True).encode()).hexdigest()
    return result


def preparar(env_origen):
    dest = ROOT / '.env'
    if not dest.exists():
        if not env_origen or not env_origen.is_file():
            raise RuntimeError('Indica --env-origen con tu .env anterior; no se imprime su contenido.')
        shutil.copyfile(env_origen, dest)
    values = env_values()
    pending = {}
    missing_db = [k for k in ('POSTGRES_PASSWORD', 'DD_POSTGRES_PASSWORD') if not values.get(k)]
    if missing_db:
        exists = capture(['docker', 'volume', 'inspect', 'pg-data'], check=False)
        if exists.returncode == 0:
            raise RuntimeError('pg-data ya existe. Configura en .env las claves reales: ' + ', '.join(missing_db) + '; no borres el volumen.')
        # Distinguir volumen ausente de Docker inaccesible.
        capture(['docker', 'info', '--format', '{{.ServerVersion}}'])
    if not values.get('POSTGRES_PASSWORD'):
        pending['POSTGRES_PASSWORD'] = secrets.token_hex(24)
    for key in ('SECRET_KEY', 'DD_POSTGRES_PASSWORD'):
        if not values.get(key):
            pending[key] = secrets.token_hex(32)
    # Solo cuentas demo publicadas explícitamente para pruebas en el README revisado.
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    demo_line = next((line for line in text.splitlines() if 'Usuarios **solo para pruebas**' in line), '')
    demo = re.findall(r'`([^`]+)`', demo_line)
    if not values.get('JJ_EMAIL') or not values.get('JJ_PASSWORD'):
        if len(demo) != 4 or '@' not in demo[0]:
            raise RuntimeError('Configura JJ_EMAIL y JJ_PASSWORD en .env con una cuenta de prueba del README.')
        if not values.get('JJ_EMAIL'):
            pending['JJ_EMAIL'] = demo[0]
        if not values.get('JJ_PASSWORD'):
            pending['JJ_PASSWORD'] = demo[-1]
    if not values.get('JJ_EVENT_ID'):
        pending['JJ_EVENT_ID'] = '1'
    if pending:
        with dest.open('a', encoding='utf-8', newline='\n') as f:
            f.write('\n# Valores locales de integracion JJ (no publicar)\n')
            for key, value in pending.items():
                # Se usan valores simples; comillas simples evitan interpolación de $. 
                if "'" in value or '\n' in value:
                    raise RuntimeError('Configura manualmente un valor con caracteres especiales: ' + key)
                f.write(f"{key}='{value}'\n")
    capture(COMPOSE + ['config', '--quiet'])
    print('Entorno preparado. Credenciales conservadas en .env; no se muestran.')


def ready():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8404/stats;csv', timeout=5) as f:
                text = f.read().decode('utf-8-sig').lstrip('# ')
            rows = list(csv.DictReader(text.splitlines()))
            servers = {r['svname']: r['status'] for r in rows if r['pxname'] == 'be_app'}
            if all(servers.get(b) == 'UP' for b in ('backend1', 'backend2', 'backend3')):
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(2)
    raise RuntimeError('Los tres backends no están UP en HAProxy; revisa servicios antes de cargar.')


def preflight():
    values = environment()
    if not all(values.get(k) for k in ('JJ_EMAIL', 'JJ_PASSWORD')):
        raise RuntimeError('Faltan credenciales de prueba; ejecuta preparar.')
    capture(COMPOSE + ['config', '--quiet'])
    running = set(capture(COMPOSE + ['ps', '--services', '--status', 'running']).stdout.split())
    missing = {'haproxy', 'backend1', 'backend2', 'backend3', 'db', 'datadog-agent'} - running
    if missing:
        raise RuntimeError('Servicios no iniciados: ' + ', '.join(sorted(missing)))
    ready()


def effective_config():
    return capture(COMPOSE + ['exec', '-T', 'haproxy', 'cat', RUNTIME]).stdout.encode('utf-8')


def algorithm(data):
    match = re.search(rb'(?m)^\s*balance\s+(roundrobin|leastconn)\s*$', data)
    if not match:
        raise RuntimeError('No se identifica un único algoritmo compatible en HAProxy.')
    return match[1].decode()


def set_algorithm(name, original):
    changed, n = re.subn(rb'(?m)^(\s*balance\s+)(roundrobin|leastconn)(\s*)$',
                        lambda m: m[1] + name.encode() + m[3], original)
    if n != 1:
        raise RuntimeError('Se esperaba una sola directiva balance; no se modifica HAProxy.')
    CFG.write_bytes(changed)
    capture(COMPOSE + ['run', '--rm', '--no-deps', '-T', 'haproxy', 'haproxy', '-c', '-f', RUNTIME])
    capture(COMPOSE + ['up', '-d', '--no-deps', '--force-recreate', 'haproxy'])
    ready()
    if algorithm(effective_config()) != name:
        raise RuntimeError('La configuración montada de HAProxy no coincide con el algoritmo solicitado.')


def phases(pattern, rate, base, seconds):
    if pattern == 'constante':
        return [{'duration': seconds, 'arrivalRate': rate, 'name': 'Carga constante'}]
    if pattern == 'gradual':
        weights, values = [2, 1, 3, 1, 2], [base, base, rate, rate, base]
    else:
        weights, values = ([2, 2, 3, 2], [base, (base + rate) // 2, rate, base]) if pattern == 'escalonado' else ([4, 1, 4], [base, rate, base])
    lengths = [seconds * w // sum(weights) for w in weights]
    lengths[-1] += seconds - sum(lengths)
    result = [{'duration': n, 'arrivalRate': v, 'name': f'{pattern} fase {i+1}'} for i, (n, v) in enumerate(zip(lengths, values))]
    if pattern == 'gradual':
        result[1]['rampTo'] = rate
        result[3]['rampTo'] = base
    return result


def plan(base):
    jobs = [{'label': f'intensidad-{n}', 'grupos': ['intensidad'] + (['patron'] if n == 10 else []),
             'rate': n, 'seconds': 300, 'pattern': 'constante', 'algorithm': 'roundrobin'} for n in (10, 20, 40, 60)]
    jobs += [{'label': p, 'grupos': ['patron'], 'rate': 10, 'seconds': 300,
              'pattern': p, 'algorithm': 'roundrobin'} for p in ('escalonado', 'pico')]
    jobs += [{'label': f'duracion-{s}', 'grupos': ['duracion'], 'rate': base,
              'seconds': s, 'pattern': 'constante', 'algorithm': 'roundrobin'} for s in (600, 900)]
    jobs += [{'label': f'{a}-{n}', 'grupos': ['algoritmo'] + (['duracion'] if a == 'roundrobin' and n == 1 else []),
              'rate': base, 'seconds': 300, 'pattern': 'constante', 'algorithm': a}
             for a in ('roundrobin', 'leastconn') for n in (1, 2, 3)]
    return jobs


def run_one(folder, job, operation='consulta', single=False):
    run_id = job['label'] + '-' + stamp() + '-' + uuid.uuid4().hex[:6]
    evidence = folder / run_id
    evidence.mkdir()
    results = ART / 'resultados/taquilla' / folder.name
    results.mkdir(parents=True, exist_ok=True)
    output = results / (run_id + '.json')
    source = ART / (job.get('escenario', 'pico' if job['pattern'] in ('pico', 'gradual') else 'normal') + '.yml')
    script = read(source)  # JSON es un subconjunto de YAML; evita otra dependencia.
    script['config']['phases'] = ([{'duration': 1, 'arrivalCount': 1, 'name': 'Un usuario funcional'}] if single
        else phases(job['pattern'], job['rate'], job.get('base', 2) if job['pattern'] != 'constante' else job['rate'], job['seconds']))
    script['config']['processor'] = './taquilla.js'
    if operation == 'reserva':
        script['scenarios'][0]['flow'].insert(-1, {'post': {
            'url': '/api/events/{{ event_id }}/seats/{{ seat_id }}/reserve',
            'headers': {'X-CSRF-Token': '{{ csrf_token }}'}, 'afterResponse': 'reserva', 'name': 'reservar_silla'}})
    write(evidence / 'escenario.json', script, new=True)
    shutil.copyfile(ART / 'taquilla.js', evidence / 'taquilla.js')
    cfg = effective_config()
    if algorithm(cfg) != job['algorithm']:
        raise RuntimeError('Algoritmo montado distinto del plan. No se inicia la corrida.')
    (evidence / 'haproxy-montado.cfg').write_bytes(cfg)
    expected_vu = 1 if single else sum(p['duration'] * p['arrivalRate'] for p in script['config']['phases'])
    if any('rampTo' in p for p in script['config']['phases']):
        expected_vu = None
    image_ids = {service: capture(['docker', 'inspect', '--format', '{{.Image}}', service]).stdout.strip()
                 for service in ('haproxy', 'backend1', 'backend2', 'backend3', 'db', 'datadog-agent')}
    meta = {'id': run_id, 'inicio_utc': utc(), 'plan': job, 'operacion': operation,
            'vu_programados': expected_vu, 'peticiones_por_flujo_completo': 5 if operation == 'reserva' else 4,
            'resultado': output.relative_to(ROOT).as_posix(), 'imagenes': image_ids,
            'sha256_archivos': fingerprint(), 'sha256_config_montada': hashlib.sha256(cfg).hexdigest()}
    write(evidence / 'inicio.json', meta, new=True)
    container = 'jj-taquilla-' + uuid.uuid4().hex[:12]
    command = COMPOSE + ['run', '--rm', '--no-deps', '-T', '--name', container]
    for name in ENV_NAMES:
        command += ['-e', name]
    command += ['artillery', 'run', '/scripts/' + (evidence / 'escenario.json').relative_to(ART).as_posix(),
                '-o', '/results/taquilla/' + folder.name + '/' + output.name]
    process = None
    code, error = None, None
    print(f"INICIO {job['label']} ({operation}), {job['seconds']} s | {run_id}", flush=True)
    try:
        with (evidence / 'consola.log').open('x', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=environment(operation), stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            code = process.wait()
        if code != 0:
            raise RuntimeError('Artillery terminó con código ' + str(code))
        data = read(output)
        counters = data.get('aggregate', {}).get('counters', {})
        if 'http.requests' not in counters:
            raise RuntimeError('Resultado sin aggregate.counters.http.requests')
    except BaseException as exc:
        error = type(exc).__name__
        if process is not None and process.poll() is None:
            subprocess.run(['docker', 'stop', '--time', '10', container], capture_output=True, timeout=25)
            process.wait(timeout=30)
        raise
    finally:
        write(evidence / 'fin.json', {'fin_utc': utc(), 'codigo_salida': code, 'interrupcion': error,
                                      'resultado_existe': output.exists()}, new=True)
    record = {'id': run_id, 'label': job['label'], 'grupos': job['grupos'], 'algorithm': job['algorithm'],
              'rate': job['rate'], 'seconds': job['seconds'], 'pattern': job['pattern'],
              'resultado': output.relative_to(ROOT).as_posix(), 'inicio_utc': meta['inicio_utc'],
              'fin_utc': utc(), 'vu_programados': expected_vu, 'operacion': operation}
    print('FIN ' + run_id, flush=True)
    return record, counters


def check_auth(counters):
    if counters.get('http.codes.401', 0) or counters.get('http.codes.403', 0):
        raise RuntimeError('Se detectó 401/403: detener y corregir sesión/CSRF; no interpretar como saturación.')


def smoke(with_booking):
    preflight()
    folder = ART / 'campanas' / ('humo-' + stamp())
    folder.mkdir(parents=True)
    manifest = {'id': folder.name, 'tipo': 'humo', 'estado': 'en_curso', 'corridas': [], 'huellas': fingerprint()}
    write(folder / 'manifest.json', manifest)
    for operation in (['consulta', 'reserva'] if with_booking else ['consulta']):
        job = {'label': operation, 'grupos': ['humo'], 'algorithm': algorithm(effective_config()),
               'pattern': 'constante', 'rate': 1, 'seconds': 1}
        result, c = run_one(folder, job, operation, single=True)
        manifest['corridas'].append(result)
        write(folder / 'manifest.json', manifest)
        if c.get('vusers.failed', 0) or c.get('jj.flujo_ok', 0) != 1:
            raise RuntimeError('Humo fallido; no iniciar campaña. Revisa el resultado y consola de esta corrida.')
        if operation == 'reserva' and c.get('jj.reserva_ok', 0) != 1:
            raise RuntimeError('No se confirmó la reserva funcional.')
    manifest['estado'] = 'completada'
    write(folder / 'manifest.json', manifest)
    write(ART / 'campanas/ultimo_humo.json', {'manifest': (folder / 'manifest.json').relative_to(ROOT).as_posix()})
    print('HUMO CORRECTO. ' + ('Se creó UNA reserva; los datos se conservan.' if with_booking else 'Solo consultas.'))


def campaign(base, resume):
    preflight()
    humo = read(ROOT / read(ART / 'campanas/ultimo_humo.json')['manifest'])
    if humo['estado'] != 'completada' or humo['huellas'] != fingerprint() or not any(r['operacion'] == 'reserva' for r in humo['corridas']):
        raise RuntimeError('Ejecuta humo --con-reserva con esta versión antes de la campaña.')
    if resume:
        folder = ART / 'campanas' / resume
        manifest = read(folder / 'manifest.json')
        if manifest['tipo'] != 'campana' or manifest['huellas'] != fingerprint():
            raise RuntimeError('La versión cambió desde la campaña; conserva la anterior y crea otra.')
        original = (folder / 'haproxy-original.cfg').read_bytes()
        if CFG.read_bytes() != original:
            raise RuntimeError('Restaura primero haproxy.cfg desde el respaldo de esta campaña y valida/recrea HAProxy.')
    else:
        folder = ART / 'campanas' / ('taquilla-' + stamp())
        folder.mkdir(parents=True)
        original = CFG.read_bytes()
        if algorithm(original) != 'roundrobin':
            raise RuntimeError('La campaña debe comenzar desde roundrobin.')
        (folder / 'haproxy-original.cfg').write_bytes(original)
        manifest = {'id': folder.name, 'tipo': 'campana', 'estado': 'en_curso', 'base_vu_s': base,
                    'huellas': fingerprint(), 'plan': plan(base), 'corridas': [], 'inicio_utc': utc(),
                    'perfil': 'Un login y tres consultas por VU. Reserva validada separadamente en humo.'}
    write(folder / 'manifest.json', manifest)
    write(ART / 'campanas/ultima_campana.json', {'manifest': (folder / 'manifest.json').relative_to(ROOT).as_posix()})
    done = {r['label'] for r in manifest['corridas'] if r.get('valida', True)}
    print('Campaña: ' + folder.name + '\nReanudar: python artillery/cierre_hoy.py campana --reanudar ' + folder.name, flush=True)
    current = None
    try:
        for job in manifest['plan']:
            if job['label'] in done:
                continue
            if current != job['algorithm']:
                print('Aplicando HAProxy ' + job['algorithm'], flush=True)
                set_algorithm(job['algorithm'], original)
                current = job['algorithm']
            ready()
            result, c = run_one(folder, job)
            result['valida'] = not (c.get('http.codes.401', 0) or c.get('http.codes.403', 0))
            manifest['corridas'].append(result)
            write(folder / 'manifest.json', manifest)
            check_auth(c)
            # La carga alta puede producir fallos: se registran, no se maquillan como éxito.
            print(f"Resumen: solicitudes={c.get('http.requests')}, flujos_ok={c.get('jj.flujo_ok', 0)}, VU_fallidos={c.get('vusers.failed', 0)}", flush=True)
        manifest['estado'] = 'completada'
    except BaseException as exc:
        manifest['estado'] = 'interrumpida'
        manifest['motivo'] = type(exc).__name__
        raise
    finally:
        manifest['fin_utc'] = utc()
        CFG.write_bytes(original)
        try:
            capture(COMPOSE + ['run', '--rm', '--no-deps', '-T', 'haproxy', 'haproxy', '-c', '-f', RUNTIME])
            capture(COMPOSE + ['up', '-d', '--no-deps', '--force-recreate', 'haproxy'])
            ready()
            manifest['restauracion_haproxy'] = 'aplicada'
        except Exception:
            manifest['restauracion_haproxy'] = 'archivo_restaurado_aplicacion_pendiente'
            print('ATENCION: archivo restaurado; falta validar/recrear HAProxy desde terminal.', flush=True)
        write(folder / 'manifest.json', manifest)
        report(folder)


def report(folder):
    from analizar_artillery import analizar
    manifest = read(folder / 'manifest.json')
    rows = []
    for run in manifest['corridas']:
        if not run.get('valida', True):
            continue  # Se conserva el intento inválido en manifiesto y archivos originales.
        row = analizar(ROOT / run['resultado'])
        c = read(ROOT / run['resultado'])['aggregate']['counters']
        row.update({k: run[k] for k in ('label', 'algorithm', 'rate', 'seconds', 'pattern', 'inicio_utc', 'fin_utc', 'vu_programados', 'operacion')})
        row['flujos_ok'] = c.get('jj.flujo_ok', 0)
        row['reservas_ok'] = c.get('jj.reserva_ok', 0)
        rows.append(row)
    if not rows:
        print('Sin corridas completadas para el informe. Evidencias parciales en ' + str(folder))
        return
    dest = ROOT / 'docs/evidencias' / manifest['id'] / stamp()
    dest.mkdir(parents=True)
    with (dest / 'resumen.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# Campaña de taquilla', '', 'Estado de ejecución: **' + manifest['estado'] + '**.', '',
             'Esta campaña corresponde a la aplicación con PostgreSQL. No mezclar con la campaña histórica del backend simple.', '',
             'Perfil: un inicio de sesión por VU, cartelera, sillas y mis reservas. Son cuatro peticiones por flujo completo; '
             'un VU que falla puede enviar menos. La reserva real y el CSRF se validan en una prueba funcional separada de un usuario. '
             'El perfil de rendimiento es de consultas autenticadas; no mide una mezcla de compras ni la contención de reservas.', '',
             '| Corrida | Algoritmo | VU/s | Fases s | Solicitudes | RPS ventana | Media ms | p50 | p95 | p99 | 4xx | 5xx | VU fallidos | Flujos OK |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        vals = [r[k] for k in ('label','algorithm','rate','seconds','solicitudes','rps_media_ventana',
                'ttfb_mean_ms','ttfb_p50_ms','ttfb_p95_ms','ttfb_p99_ms','http_4xx','http_5xx','vusers_failed','flujos_ok')]
        lines.append('| ' + ' | '.join('ND' if v is None else f'{v:.3f}' if isinstance(v, float) else str(v) for v in vals) + ' |')
    lines += ['', '## Lectura de los resultados', '']
    intensity = [r for r in rows if r['label'].startswith('intensidad-')]
    failures = [r for r in intensity if (r['http_5xx'] or 0) or (r['vusers_failed'] or 0)]
    if len(intensity) == 4 and not failures:
        lines += ['En las cuatro intensidades ensayadas no se observaron respuestas 5xx ni usuarios fallidos. '
                  'No se encontró el punto de quiebre por esos indicadores; no equivale a demostrar capacidad ilimitada.', '']
    elif failures:
        lines += ['Se observaron errores o usuarios fallidos en: ' + ', '.join(r['label'] for r in failures) +
                  '. Correlacionar las ventanas con CPU, colas y latencias antes de atribuir la causa a saturación.', '']
    for alg in ('roundrobin', 'leastconn'):
        reps = [r for r in rows if r['label'].startswith(alg + '-')]
        if reps:
            lines += [alg + ': p95 por repetición = ' + ', '.join(str(r['ttfb_p95_ms']) for r in reps) +
                      ' ms. No constituye un percentil combinado ni una prueba de superioridad general.', '']
    lines += ['## Evidencia y límites', '',
              '- Latencia HTTP de Artillery: TTFB en ms. No se promedian percentiles para presentar un percentil global.',
              '- RPS ventana = solicitudes / ventana de métricas. El CSV conserva también la tasa reportada por Artillery.',
              '- Las intensidades son tasas de llegada de VU. Los fallos bajo carga se conservan como resultados, no se descartan.',
              '- Patrones: referencia constante a 10 VU/s; escalonado y pico tienen máximo 10 VU/s y base 2. Sus volúmenes difieren.',
              '- Duración y algoritmos usan la tasa base del manifiesto. Se mantienen las mismas consultas y workers.',
              '- Orden fijo y equipo compartido: no atribuir diferencias pequeñas exclusivamente al algoritmo.',
              '- El inicio de sesión puede dominar el coste. Para afirmar saturación correlacionar errores/latencia con CPU, memoria y colas.',
              '- La campaña anterior se conserva como histórica. Los ensayos de proporciones de operaciones, pausas, contención y workers se coordinan con Gargamel.',
              '- Pendiente incorporar capturas/exportaciones del dashboard en las ventanas indicadas abajo.', '',
              '## Ventanas UTC para Datadog', '', '| Corrida | Inicio UTC | Fin UTC |', '|---|---|---|']
    lines += [f"| {r['label']} | {r['inicio_utc']} | {r['fin_utc']} |" for r in rows]
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 1, figsize=(12, 9), layout='constrained')
        for ax, key, title in [(axes[0], 'ttfb_p95_ms', 'p95 TTFB (ms)'), (axes[1], 'rps_media_ventana', 'Solicitudes/s sobre ventana de métricas')]:
            selected = [r for r in rows if r[key] is not None]
            ax.barh([r['label'] for r in selected], [r[key] for r in selected])
            ax.invert_yaxis()
            ax.set_xlabel(title)
            ax.grid(axis='x', alpha=.2)
        fig.savefig(dest / 'comparacion.png', dpi=150)
        plt.close(fig)
        lines += ['', '![Comparación por corrida](comparacion.png)', '']
    except ImportError:
        lines += ['', 'Gráficas pendientes: instalar requirements-informe-jj.txt y ejecutar informe --ultima.', '']
    (dest / 'informe.md').write_text('\n'.join(lines), encoding='utf-8')
    write(dest / 'manifest.json', manifest, new=True)
    print('INFORME: ' + str(dest), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    prep = sub.add_parser('preparar')
    prep.add_argument('--env-origen', type=Path)
    h = sub.add_parser('humo')
    h.add_argument('--con-reserva', action='store_true', help='Crea una reserva real con un único VU')
    c = sub.add_parser('campana')
    c.add_argument('--base', type=int, default=2)
    c.add_argument('--reanudar')
    c.add_argument('--solo-plan', action='store_true')
    q = sub.add_parser('informe')
    q.add_argument('--ultima', action='store_true', required=True)
    one = sub.add_parser('correr')
    one.add_argument('--escenario', choices=['normal','pico'], default='normal')
    one.add_argument('--tasa', type=int, default=2)
    one.add_argument('--duracion', type=int, default=30)
    one.add_argument('--patron', choices=['constante','escalonado','pico','gradual'])
    one.add_argument('--base', type=int, default=1)
    one.add_argument('--solo-validar', action='store_true')
    one.add_argument('--operacion', choices=['consulta','reserva'], default='consulta')
    args = p.parse_args()
    if args.cmd == 'preparar':
        preparar(args.env_origen)
    elif args.cmd == 'humo':
        smoke(args.con_reserva)
    elif args.cmd == 'campana':
        if not 1 <= args.base <= 10:
            p.error('--base debe estar entre 1 y 10 VU/s')
        if args.reanudar and Path(args.reanudar).name != args.reanudar:
            p.error('--reanudar requiere solo el ID, no una ruta')
        if args.solo_plan:
            jobs = plan(args.base)
            print(json.dumps(jobs, indent=2))
            print('Duración de fases (minutos):', sum(j['seconds'] for j in jobs) / 60)
        else:
            campaign(args.base, args.reanudar)
    elif args.cmd == 'informe':
        report((ROOT / read(ART / 'campanas/ultima_campana.json')['manifest']).parent)
    else:
        args.patron = args.patron or ('gradual' if args.escenario == 'pico' else 'constante')
        if args.tasa < 1 or args.duracion < 30 or not 1 <= args.base <= args.tasa:
            p.error('Tasa >= 1, duración >= 30 y 1 <= base <= tasa')
        if args.operacion == 'reserva' and args.tasa * args.duracion > 30:
            p.error('Para reservas, máximo 30 VU por prueba: coordina datasets con Gargamel para ensayos mayores.')
        if args.solo_validar:
            print(json.dumps({'escenario': args.escenario, 'operacion': args.operacion,
                              'phases': phases(args.patron,args.tasa,args.base,args.duracion)},indent=2))
            print('Solo plan; sin Docker ni carga.')
            return
        preflight()
        folder = ART / 'campanas' / ('manual-' + stamp());folder.mkdir(parents=True)
        job = {'label': 'manual', 'grupos': ['manual'], 'rate': args.tasa, 'seconds': args.duracion,
               'pattern': args.patron, 'algorithm': algorithm(effective_config()), 'base': args.base, 'escenario': args.escenario}
        r, counters = run_one(folder, job, args.operacion)
        write(folder / 'manifest.json', {'id': folder.name, 'estado': 'completada', 'corridas': [r]})
        report(folder)
        check_auth(counters)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nInterrumpido. Conserva las evidencias y el ID para reanudar.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
