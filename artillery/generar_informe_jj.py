#!/usr/bin/env python3
"""Informe de la campaña JJ del 14/11/2026. Lee evidencias; no ejecuta Docker.

Requiere analizar_artillery.py en el repositorio y matplotlib para las figuras.
La salida debe ser una carpeta nueva. No modifica resultados ni configuraciones.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


HASH_ALGORITMOS = {
    'cead4197d6754c29cd4857a6c3a23c98ab2a57a1914a02200ccb08fbf6f230bb': 'Round Robin',
    'a545fa2f005aa8fa166d6f1b62e11af0dd20e084d630b15931a3b35e3d8e6df6': 'Least Connections',
}
# Selección explícita de corridas: excluye calibración, humo y errores forzados.
GRUPOS = {
    'Intensidad': [('10 VU/s', '0b8808ae'), ('20 VU/s', '1b14c26f'),
                   ('40 VU/s', '00d6c633'), ('60 VU/s', 'b0e73b0e')],
    'Patrón': [('Constante', '1b14c26f'), ('Escalonado', 'df551a1f'), ('Pico', '538df79c')],
    'Duración': [('5 min', '1b14c26f'), ('10 min', '29b5c9ff'), ('15 min', 'a260e98f')],
    'Algoritmo': [('RR 1', '2903f136'), ('RR 2', 'f99b0918'), ('RR 3', 'e760d098'),
                  ('LC 1', '6cb95610'), ('LC 2', '8e3ff9fe'), ('LC 3', 'aef019d1')],
}


def leer(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valor(value):
    if value is None:
        return 'ND'
    return f'{value:.3f}'.rstrip('0').rstrip('.') if isinstance(value, float) else str(value)


def tabla(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(map(valor, row)) + ' |' for row in rows])


def cargar(repo):
    spec = importlib.util.spec_from_file_location('analizador_jj', repo / 'artillery/analizar_artillery.py')
    analizador = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analizador)
    registros = {}
    fuentes = []
    for token in dict.fromkeys(t for grupo in GRUPOS.values() for _, t in grupo):
        matches = list((repo / 'artillery/resultados').glob('*-' + token + '.json'))
        if len(matches) != 1:
            raise ValueError(f'Esperado un único resultado para {token}; encontrados {len(matches)}')
        path = matches[0]
        carpeta = repo / 'artillery/corridas' / path.stem
        inicio = leer(carpeta / 'inicio.json')
        fin = leer(carpeta / 'fin.json')
        overrides = leer(carpeta / 'overrides.json')
        if inicio['id'] != path.stem or inicio['resultado'] != path.name or fin['id'] != path.stem:
            raise ValueError(f'Identidad de evidencia inconsistente: {path.name}')
        if fin['codigo_salida'] != 0 or fin['estado'] != 'proceso_completado':
            raise ValueError(f'Corrida incompleta: {path.name}')
        if digest(carpeta / 'escenario.yml') != inicio['sha256_archivos']['artillery/normal.yml']:
            raise ValueError(f'Escenario copiado no coincide con su huella: {path.name}')
        config = overrides['config']
        if config['target'] != 'http://haproxy:8080':
            raise ValueError(f'Target inesperado: {path.name}')
        phases = config['phases']
        if sum(p['duration'] for p in phases) != inicio['duracion_fases_s']:
            raise ValueError(f'Duración inconsistente: {path.name}')
        if any('rampTo' in p for p in phases):
            raise ValueError('Esta selección usa fases constantes; no calcula integrales de rampas')
        expected = sum(p['duration'] * p['arrivalRate'] for p in phases)
        fila = analizador.analizar(path)
        for field in ('solicitudes', 'respuestas', 'ttfb_mean_ms', 'ttfb_p50_ms',
                      'ttfb_p95_ms', 'ttfb_p99_ms', 'http_2xx', 'http_4xx',
                      'http_5xx', 'vusers_completed', 'vusers_failed'):
            if fila[field] is None:
                raise ValueError(f'Falta {field} en {path.name}')
        fila.update({
            'id': path.stem,
            'algoritmo_segun_config_local': HASH_ALGORITMOS.get(
                inicio['sha256_archivos']['haproxy/haproxy.cfg'], 'No identificado'),
            'patron': inicio['patron'], 'tasa_vu_s': inicio['tasa_vu_s'],
            'duracion_fases_s': inicio['duracion_fases_s'],
            'solicitudes_esperadas_un_get_por_vu': expected,
            'inicio_ejecutor_utc': inicio['inicio_utc'], 'fin_ejecutor_utc': fin['fin_utc'],
        })
        registros[token] = {'fila': fila, 'inicio': inicio, 'overrides': overrides}
        fuentes.append({'id': path.stem, 'algoritmo_segun_config_local': fila['algoritmo_segun_config_local'],
                        'sha256_resultado': digest(path),
                        'sha256_inicio': digest(carpeta / 'inicio.json'),
                        'sha256_fin': digest(carpeta / 'fin.json'),
                        'sha256_overrides': digest(carpeta / 'overrides.json'),
                        'sha256_config_local_registrados': inicio['sha256_archivos']})
    algoritmos = [registros[t] for _, t in GRUPOS['Algoritmo']]
    for relative in ('artillery/normal.yml', 'docker-compose.yml', 'backends/gunicorn.conf.py'):
        if len({r['inicio']['sha256_archivos'][relative] for r in algoritmos}) != 1:
            raise ValueError(f'Cambia {relative} entre las seis repeticiones')
    if len({json.dumps(r['overrides'], sort_keys=True) for r in algoritmos}) != 1:
        raise ValueError('Las seis repeticiones no usan el mismo plan de carga')
    for label, token in GRUPOS['Algoritmo']:
        esperado = 'Round Robin' if label.startswith('RR') else 'Least Connections'
        if registros[token]['fila']['algoritmo_segun_config_local'] != esperado:
            raise ValueError(f'Algoritmo local inesperado para {label}')
    return registros, fuentes


def graficas(registros, salida):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none'})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    for ax, (grupo, condiciones) in zip(axes.flat, GRUPOS.items()):
        valores = [registros[t]['fila']['ttfb_p95_ms'] for _, t in condiciones]
        colores = ['#167d8d' if not label.startswith('LC') else '#b75c21' for label, _ in condiciones]
        barras = ax.bar([label for label, _ in condiciones], valores, color=colores, width=.58)
        ax.bar_label(barras, labels=[valor(v) for v in valores], padding=4)
        ax.set_ylim(0, max(valores) * 1.35)
        ax.set_ylabel('p95 TTFB (ms)')
        ax.set_title(grupo + (' — 3 corridas por algoritmo' if grupo == 'Algoritmo' else ' — 1 corrida por condición'), loc='left')
        ax.set_axisbelow(True)
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Campaña JJ · 14 noviembre 2026\nPercentil por corrida; no se combinan percentiles', fontsize=15)
    for extension in ('png', 'svg'):
        fig.savefig(salida / ('comparaciones_p95.' + extension), dpi=160)
    plt.close(fig)


def informe(registros):
    lineas = ['# Pruebas de carga — campaña JJ del 14 de noviembre de 2026', '',
              'Fuente: JSON reales de Artillery y metadatos del ejecutor. '
              'Los algoritmos se identifican mediante las huellas SHA-256 de las configuraciones locales registradas. '
              'Esas huellas no certifican por sí solas la configuración efectiva del proceso HAProxy en ejecución.', '',
              '## Método', '',
              'Un GET `/` por usuario virtual, dirigido a `http://haproxy:8080`. '
              'La tasa configurada representa usuarios nuevos por segundo, no concurrencia fija. '
              'Se varía un factor por grupo; las comparaciones de intensidad, patrón y duración tienen una sola corrida por condición. '
              'Para algoritmos se hicieron tres corridas consecutivas de Round Robin y luego tres de Least Connections: '
              '20 VU/s, 300 segundos y carga constante. El orden no fue aleatorizado.', '',
              'Las seis repeticiones tienen las mismas huellas del escenario, Compose y Gunicorn, '
              'y el mismo plan de carga. No se registraron huellas históricas de la imagen construida de los backends '
              'ni del estado de recursos del equipo; no se afirma equivalencia total del entorno.', '',
              '## Resultados', '', '![Comparaciones de p95](comparaciones_p95.png)', '']
    for grupo, condiciones in GRUPOS.items():
        lineas += ['### ' + grupo, '', tabla(
            ['Condición', 'Solicitudes', 'Respuestas 2xx', 'Media ms', 'p50 ms', 'p95 ms', 'p99 ms', '4xx', '5xx', 'VU fallidos'],
            [[label] + [registros[t]['fila'][key] for key in ('solicitudes', 'http_2xx',
              'ttfb_mean_ms', 'ttfb_p50_ms', 'ttfb_p95_ms', 'ttfb_p99_ms', 'http_4xx', 'http_5xx', 'vusers_failed')]
             for label, t in condiciones]), '']
    lineas += ['## Interpretación y límites', '',
        '- En las seis corridas comparativas se registraron 36.000 solicitudes, 36.000 respuestas HTTP 200 '
        'y cero usuarios fallidos. Round Robin obtuvo p95 de 3, 3 y 4 ms; Least Connections de 3, 2 y 2 ms. '
        'Son percentiles de cada corrida, no un percentil global de las 18.000 solicitudes por algoritmo.',
        '- Least Connections tuvo un p95 menor en dos repeticiones y el mismo valor en otra. '
        'La diferencia absoluta de 1–2 ms, la carga ligera, tres repeticiones y el orden fijo '
        'no permiten afirmar superioridad general ni atribuir causalidad exclusivamente al algoritmo.',
        '- Hasta 60 VU/s durante 300 s no se observaron fallos de usuarios ni respuestas 5xx en las corridas seleccionadas. '
        'Esto no determina la capacidad máxima ni demuestra saturación.',
        '- A 20 VU/s, las ejecuciones de 5, 10 y 15 minutos no mostraron deterioro del p95 agregado. '
        'Un agregado no descarta picos breves de latencia.',
        '- Los patrones no generan el mismo volumen: constante 6.000; escalonado 3.328; pico 1.728. '
        'Se comparte máximo de 20 VU/s y duración de 300 s, pero no carga media. '
        'El escalonado usa 66 s a 4, 66 s a 12, 100 s a 20 y 68 s a 4 VU/s. '
        'El pico usa 133 s a 4, 33 s a 20 y 134 s a 4 VU/s.',
        '- `http.response_time` es tiempo hasta el primer byte (TTFB), en ms; no es tiempo completo de descarga. '
        'No se confunde con duración de sesión del usuario ni con tiempo de procesamiento del backend.',
        '- El CSV conserva la tasa reportada por Artillery y la media calculada como solicitudes / '
        '((lastMetricAt − firstMetricAt) / 1000). La ventana de métricas no equivale a la duración de fases. '
        'La discrepancia de tasas requiere interpretar ambas definiciones; no implica automáticamente fallo.',
        '- Las corridas antiguas de calibración, errores forzados, recuperación y humo se conservan, '
        'pero no se mezclan con estas condiciones. Los 195 HTTP 500 de la prueba de errores no se atribuyen a esta campaña.',
        '- No se recibieron exportaciones o capturas de Datadog para este informe. '
        'No se deducen CPU, memoria, reparto por backend ni exactitud de OpenMetrics a partir de Artillery. '
        'El README del proyecto registra una limitación pendiente de contadores Prometheus con dos workers.', '',
        '## Trazabilidad y ventanas para Datadog', '',
        'Cada fila del CSV identifica el JSON de origen. `trazabilidad.json` conserva sus hashes '
        'y los de los metadatos revisados. Una misma corrida base aparece en varios grupos, '
        'pero en el CSV se guarda una sola vez. Los horarios siguientes son del ejecutor '
        '(incluyen preparación y cierre), en Colombia UTC−05:00. '
        'El CSV también contiene la ventana exacta de métricas en epoch ms.', '',
        tabla(['Corrida', 'Inicio Colombia', 'Fin Colombia', 'ID'], [
            [label, *[datetime.fromisoformat(registros[t]['fila'][k]).astimezone(
                timezone(timedelta(hours=-5))).strftime('%Y-%m-%d %H:%M:%S')
                for k in ('inicio_ejecutor_utc', 'fin_ejecutor_utc')], registros[t]['fila']['id']]
            for label, t in GRUPOS['Algoritmo']]), '',
        '## Pendientes para entrega', '',
        '- Restaurar `balance roundrobin`, validar y aplicar la configuración; comprobar que el diff de HAProxy quede vacío.',
        '- Incorporar evidencias de Datadog para los intervalos documentados, con zona horaria visible y unidades.',
        '- Revisar el diff de Compose y guardar en Git únicamente cambios de JJ y evidencias seleccionadas. '
        'Excluir `.env`, respaldos, entornos virtuales y archivos temporales.',
        '- Integrar el enlace al manual de carga en la sección 9 del README. '
        'Si la rúbrica exige tres repeticiones de todas las condiciones, las de intensidad, patrón y duración '
        'todavía tienen una sola; las tres repeticiones se completaron únicamente por algoritmo.', '',
        '## Referencias de interpretación', '',
        '- [Métricas HTTP de Artillery](https://www.artillery.io/docs/reference/engines/http)',
        '- [Prometheus Python: modo multiproceso](https://prometheus.github.io/client_python/multiprocess/)', '']
    return '\n'.join(lineas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--salida', type=Path, required=True, help='Carpeta NUEVA para informe, CSV y gráficas')
    args = parser.parse_args()
    if args.salida.exists():
        parser.exit(1, 'ERROR: la carpeta de salida ya existe; elige otra para no sobrescribir.\n')
    try:
        registros, fuentes = cargar(args.repo.resolve())
        # Verificar los resultados usados por las conclusiones antes de escribirlas.
        for r in registros.values():
            f = r['fila']
            if f['solicitudes'] != f['solicitudes_esperadas_un_get_por_vu']:
                raise ValueError('El informe de esta campaña requiere revisar el total esperado: ' + f['id'])
            if not (f['solicitudes'] == f['respuestas'] == f['http_2xx'] == f['vusers_completed']
                    and f['http_4xx'] == f['http_5xx'] == f['vusers_failed'] == 0):
                raise ValueError('Resultado distinto de las conclusiones revisadas: ' + f['id'])
        import matplotlib  # Fallar antes de crear la salida si falta esta dependencia.
        args.salida.mkdir(parents=True, exist_ok=False)
        with (args.salida / 'resumen_campana.csv').open('x', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(next(iter(registros.values()))['fila']), delimiter=';')
            writer.writeheader()
            writer.writerows(r['fila'] for r in registros.values())
        with (args.salida / 'trazabilidad.json').open('x', encoding='utf-8') as stream:
            json.dump({'seleccion': GRUPOS, 'fuentes': fuentes,
                       'nota': 'Clasificación por configuración local registrada; no certifica el proceso activo.'},
                      stream, ensure_ascii=False, indent=2)
        graficas(registros, args.salida)
        (args.salida / 'informe.md').write_text(informe(registros), encoding='utf-8')
    except (OSError, ValueError, KeyError, ImportError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')
    print(f'Informe creado con {len(registros)} corridas únicas: {args.salida.resolve()}')


if __name__ == '__main__':
    main()
