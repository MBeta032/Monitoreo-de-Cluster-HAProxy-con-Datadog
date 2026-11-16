#!/usr/bin/env python3
"""Analiza una corrida de pruebas con las métricas que Datadog guardó.

Compara tres momentos (antes, durante y después) de HAProxy, los backends, PostgreSQL y,
si se indica --test, de Artillery. Genera un informe en la consola, una página HTML con
gráficas, y archivos CSV y JSON. No usa bibliotecas externas.

Ejemplo (hora UTC, la que imprime falla.sh):
  python artillery/analizar_datadog.py --inicio 20:12:07 --fin 20:18:11 \
      --falla-desde 20:14:07 --falla-hasta 20:16:07 --test falla --titulo caida-backend1

Variables en .env (solo se leen estas tres, y nunca se escriben en los reportes):
  DD_API_KEY, DD_APP_KEY, DD_SITE
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parents[1]
CLAVES = ("DD_API_KEY", "DD_APP_KEY", "DD_SITE")
CALI = timezone(timedelta(hours=-5))  # Colombia no cambia de hora en el año


# --------------------------------------------------------------------------------------
# Métricas. Los nombres y filtros son los del dashboard del proyecto (README, sección 8)
# y los que Artillery publicó en Datadog (README, sección 10.5).
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Metrica:
    id: str
    seccion: str
    nombre: str
    consulta: str
    unidad: str
    etiqueta: str = ""      # etiqueta que separa las series ('backend', 'status', ...)
    factor: float = 1.0     # conversión de unidades
    interna: bool = False   # solo se usa para calcular indicadores, no se muestra


# HAProxy envía una fila por servidor y otra del grupo (backend:backend), que es la suma.
# Se excluye la del grupo para no contar doble (README, sección 7.3).
BE = "{haproxy_service:be_app,!backend:backend}"


def construir_metricas(test: str, codigos: list[str]) -> list[Metrica]:
    m = [
        Metrica("fe_rps", "Tráfico", "Peticiones por segundo en HAProxy (frontend)",
                "sum:haproxy.frontend.requests.tot_rate{haproxy_service:fe_web}", "req/s"),
        Metrica("be_rps", "Tráfico", "Peticiones por segundo por backend (HAProxy)",
                "sum:haproxy.backend.requests.tot_rate" + BE + " by {backend}", "req/s", "backend"),
        Metrica("be_ses", "Distribución", "Conexiones activas por backend",
                "sum:haproxy.backend.session.current" + BE + " by {backend}", "conexiones", "backend"),
        Metrica("be_cola", "Distribución", "Cola de HAProxy por backend",
                "sum:haproxy.backend.queue.current" + BE + " by {backend}", "pedidos", "backend"),
        Metrica("be_5xx", "Errores", "Respuestas 5xx por backend (HAProxy)",
                "sum:haproxy.backend.response.5xx" + BE + " by {backend}", "resp/s", "backend"),
        Metrica("fe_5xx", "Errores", "Respuestas 5xx entregadas al cliente (frontend de HAProxy)",
                "sum:haproxy.frontend.response.5xx{haproxy_service:fe_web}", "resp/s"),
        Metrica("grp_5xx", "Errores", "Respuestas 5xx del grupo be_app (fila agregada)",
                "sum:haproxy.backend.response.5xx{haproxy_service:be_app,backend:backend}", "resp/s"),
        Metrica("app_cod", "Errores", "Peticiones de la aplicación por código HTTP",
                "sum:backend.http_requests.count{*} by {status}.as_rate()", "req/s", "status"),
        Metrica("be_lat", "Latencia", "Tiempo de respuesta de los backends (HAProxy)",
                "avg:haproxy.backend.response.time" + BE + " by {backend}", "ms", "backend"),
        Metrica("dur_sum", "Latencia", "Duración acumulada en la aplicación",
                "sum:backend.http_request_duration_seconds.sum{*} by {backend}.as_count()",
                "s", "backend", interna=True),
        Metrica("dur_cnt", "Latencia", "Observaciones de duración en la aplicación",
                "sum:backend.http_request_duration_seconds.count{*} by {backend}.as_count()",
                "obs", "backend", interna=True),
        Metrica("cpu", "Recursos", "CPU por backend",
                "avg:container.cpu.usage{short_image:haproxy-telematicos-backend} by {container_name}",
                "núcleos (límite 1)", "container_name", 1e-9),
        Metrica("mem", "Recursos", "Memoria por backend",
                "avg:container.memory.usage{short_image:haproxy-telematicos-backend} by {container_name}",
                "MB (límite 384)", "container_name", 1 / 1048576),
        Metrica("pg_con", "PostgreSQL", "Conexiones usadas (del máximo de 100)",
                "max:postgresql.percent_usage_connections{project:haproxy-telematicos}", "%", "", 100),
        Metrica("pg_com", "PostgreSQL", "Commits por segundo",
                "sum:postgresql.commits{db:boleteria}", "commits/s"),
        Metrica("pg_loc", "PostgreSQL", "Bloqueos por tabla",
                "sum:postgresql.locks{db:boleteria,table:*} by {table}", "bloqueos", "table"),
        Metrica("pg_upd", "PostgreSQL", "Sillas actualizadas por segundo (tabla seats)",
                "sum:postgresql.rows_updated{db:boleteria,table:seats}", "filas/s"),
    ]
    if test:
        f = "{test:" + test + "}"
        art = [
            Metrica("art_req", "Artillery", "Peticiones por segundo",
                    "sum:artillery.http.requests" + f + ".as_rate()", "req/s"),
            Metrica("art_vu", "Artillery", "Usuarios virtuales creados por segundo",
                    "sum:artillery.vusers.created" + f + ".as_rate()", "usuarios/s"),
            Metrica("art_vuf", "Artillery", "Usuarios virtuales fallidos por segundo",
                    "sum:artillery.vusers.failed" + f + ".as_rate()", "usuarios/s"),
            Metrica("art_p50", "Artillery", "Latencia p50",
                    "avg:artillery.http.response_time.p50" + f, "ms"),
            Metrica("art_p95", "Artillery", "Latencia p95",
                    "avg:artillery.http.response_time.p95" + f, "ms"),
            Metrica("art_p99", "Artillery", "Latencia p99",
                    "avg:artillery.http.response_time.p99" + f, "ms"),
            Metrica("art_max", "Artillery", "Latencia máxima",
                    "max:artillery.http.response_time.max" + f, "ms"),
        ]
        art += [Metrica("art_c" + c, "Artillery", "Respuestas HTTP " + c + " por segundo",
                        "sum:artillery.http.codes." + c + f + ".as_rate()", "resp/s")
                for c in codigos]
        m = art + m
    return m


# --------------------------------------------------------------------------------------
# Acceso a la API de Datadog
# --------------------------------------------------------------------------------------
class ErrorDatadog(Exception):
    pass


class ErrorAutenticacion(ErrorDatadog):
    pass


def leer_claves(ruta_env: Path) -> dict[str, str]:
    """Lee solo DD_API_KEY, DD_APP_KEY y DD_SITE. El entorno tiene prioridad sobre .env."""
    valores = {k: os.environ.get(k, "").strip() for k in CLAVES}
    if ruta_env.exists():
        for linea in ruta_env.read_text(encoding="utf-8-sig").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            k, v = k.strip(), v.strip()
            if k in CLAVES and not valores[k]:
                if len(v) > 1 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                valores[k] = v
    return valores


def url_base(sitio: str) -> str:
    sitio = re.sub(r"^https?://", "", sitio).rstrip("/")
    if sitio.startswith("app."):
        sitio = sitio[4:]
    return "https://" + (sitio if sitio.startswith("api.") else "api." + sitio)


def pedir(base: str, claves: dict[str, str], ruta: str, params: dict) -> dict:
    req = Request(
        f"{base}{ruta}?{urlencode(params)}",
        headers={"DD-API-KEY": claves["DD_API_KEY"],
                 "DD-APPLICATION-KEY": claves["DD_APP_KEY"],
                 "Accept": "application/json"},
    )
    for intento in (1, 2):
        try:
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 429 and intento == 1:  # límite de consultas: una espera y un reintento
                try:
                    espera = int(e.headers.get("X-RateLimit-Reset", "10"))
                except ValueError:
                    espera = 10
                time.sleep(min(max(espera, 1), 60))
                continue
            if e.code in (401, 403):
                raise ErrorAutenticacion(
                    f"HTTP {e.code}: revisa DD_API_KEY, DD_APP_KEY y DD_SITE en .env "
                    "(la Application Key debe ser de la misma cuenta y región).")
            if e.code == 429:
                raise ErrorDatadog("HTTP 429: límite de consultas de la API; espera unos minutos.")
            raise ErrorDatadog(f"HTTP {e.code} al consultar {ruta}")
        except URLError as e:
            raise ErrorDatadog(f"No se pudo conectar con Datadog: {e.reason}")
    raise ErrorDatadog("Sin respuesta")


def nombre_serie(s: dict, m: Metrica) -> str:
    etiquetas = s.get("tag_set") or [t for t in str(s.get("scope", "")).split(",") if t]
    if m.etiqueta:
        for t in etiquetas:
            if t.startswith(m.etiqueta + ":"):
                return t.split(":", 1)[1]
    return "Total" if not m.etiqueta else (",".join(etiquetas) or "Total")


def consultar_metrica(base, claves, m: Metrica, a: int, b: int) -> list[dict]:
    resp = pedir(base, claves, "/api/v1/query", {"from": a, "to": b, "query": m.consulta})
    if resp.get("status") != "ok":
        raise ErrorDatadog(str(resp.get("error") or resp.get("message") or "respuesta inesperada")[:200])
    series, usados = [], {}
    for s in resp.get("series", []):
        puntos = [(int(p[0] / 1000), float(p[1]) * m.factor)
                  for p in s.get("pointlist", []) if p and len(p) >= 2 and p[1] is not None]
        if not puntos:
            continue
        nombre = nombre_serie(s, m)
        usados[nombre] = usados.get(nombre, 0) + 1
        if usados[nombre] > 1:
            nombre += f" ({usados[nombre]})"
        series.append({"nombre": nombre, "puntos": sorted(puntos)})
    return sorted(series, key=lambda s: s["nombre"])


def consultar_eventos(base, claves, a: int, b: int) -> list[dict]:
    resp = pedir(base, claves, "/api/v1/events", {"start": a, "end": b, "unaggregated": "true"})
    eventos = []
    for e in resp.get("events", []):
        etiquetas = e.get("tags") or []
        fuente = str(e.get("source_type_name") or e.get("source") or "")
        if e.get("monitor_id") or "monitor" in fuente.lower():
            cat = "Monitor"
        elif any(t.startswith("test:") for t in etiquetas):
            cat = "Artillery"
        elif "docker" in fuente.lower() or any(t.startswith("container_name:") for t in etiquetas):
            cat = "Docker"
        else:
            cat = "Otro"
        eventos.append({
            "ts": int(e.get("date_happened") or 0),
            "categoria": cat,
            "tipo": e.get("alert_type") or "",
            "titulo": str(e.get("title") or e.get("text") or "")[:120],
        })
    return sorted(eventos, key=lambda e: e["ts"])


# --------------------------------------------------------------------------------------
# Fases y estadísticas
# --------------------------------------------------------------------------------------
def instante(texto: str, dia: date) -> int:
    t = texto.strip().rstrip("Z")
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", t):
        h = [int(x) for x in t.split(":")] + [0]
        d = datetime(dia.year, dia.month, dia.day, h[0], h[1], h[2], tzinfo=timezone.utc)
    else:
        d = datetime.fromisoformat(t.replace(" ", "T"))
        d = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    return int(d.timestamp())


def definir_fases(ini, fin, margen, f_ini, f_fin, nombres=("Antes", "Durante", "Después")):
    colores = ("#e6edf7", "#fcefd2", "#e1f2e5")
    a, b, c = nombres
    if f_ini and f_fin:
        tramos = [(a, ini, f_ini), (b, f_ini, f_fin), (c, f_fin, fin)]
    else:
        tramos = [(a, ini - margen, ini), (b, ini, fin), (c, fin, fin + margen)]
    return [(n, a, b, c) for (n, a, b), c in zip(tramos, colores)]


def estadistica(puntos, a, b):
    v = [x for t, x in puntos if a <= t < b]
    if not v:
        return None
    return {"promedio": sum(v) / len(v), "min": min(v), "max": max(v), "n": len(v)}


def num(v, dec=None) -> str:
    if v is None:
        return "—"
    if dec is None:
        a = abs(v)
        dec = 0 if a >= 1000 else 1 if a >= 10 else 2 if a >= 1 else 3 if a >= 0.01 else 4
        if a == 0:
            dec = 0
    s = f"{v:,.{dec}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def hora(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")


def hora_doble(ts: int) -> str:
    return f"{hora(ts)} UTC ({datetime.fromtimestamp(ts, tz=CALI).strftime('%H:%M:%S')} Cali)"


def promedio_serie(resultado, id_metrica, fase):
    """Promedio de cada serie de una métrica en una fase: {nombre: promedio}."""
    out = {}
    for s in resultado.get(id_metrica, {}).get("series", []):
        e = estadistica(s["puntos"], fase[1], fase[2])
        if e:
            out[s["nombre"]] = e["promedio"]
    return out


def filas_resumen(series, fases):
    """Filas [serie, fase1, fase2, fase3, máx]. Marca con * las fases con menos de la mitad de
    muestras que otras series de la misma métrica (por ejemplo, un contenedor detenido)."""
    est = [[estadistica(s["puntos"], f[1], f[2]) for f in fases] for s in series]
    tope = [max((e[i]["n"] for e in est if e[i]), default=0) for i in range(len(fases))]
    filas, hay_marca = [], False
    for s, e in zip(series, est):
        celdas = []
        for i, x in enumerate(e):
            if not x:
                celdas.append("—")
                continue
            poco = bool(tope[i]) and x["n"] < 0.5 * tope[i]
            hay_marca = hay_marca or poco
            celdas.append(num(x["promedio"]) + ("*" if poco else ""))
        filas.append([s["nombre"]] + celdas + [num(max((x["max"] for x in e if x), default=None))])
    return filas, hay_marca


NOTA_MUESTRAS = ("* Pocas muestras en esa fase (menos de la mitad que otras series): el valor no es "
                 "representativo, por ejemplo cuando el contenedor estaba detenido.")


def total_serie(resultado, id_metrica, fase):
    """Suma de los valores de cada serie dentro de una fase: {nombre: total}."""
    return {s["nombre"]: sum(v for t, v in s["puntos"] if fase[1] <= t < fase[2])
            for s in resultado.get(id_metrica, {}).get("series", [])}


def indicadores(resultado, fases):
    """Cálculos que combinan varias métricas. Solo datos medidos, sin interpretaciones."""
    ind = {"reparto": {}, "error_5xx": [], "latencia_app": {}, "sin_trafico": []}
    por_fase = [promedio_serie(resultado, "be_rps", f) for f in fases]
    nombres = sorted({n for d in por_fase for n in d})
    for n in nombres:
        fila = []
        for d in por_fase:
            total = sum(d.values())
            fila.append(d.get(n, 0.0) / total * 100 if total > 0 else None)
        ind["reparto"][n] = fila
    for f, d in zip(fases, por_fase):
        e5 = sum(promedio_serie(resultado, "be_5xx", f).values())
        total = sum(d.values())
        ind["error_5xx"].append(e5 / total * 100 if total > 0 else None)
    s_sum = [total_serie(resultado, "dur_sum", f) for f in fases]
    s_cnt = [total_serie(resultado, "dur_cnt", f) for f in fases]
    for n in sorted({k for d in s_sum for k in d}):
        # Con menos de 30 observaciones el promedio no es confiable y se deja en blanco.
        ind["latencia_app"][n] = [
            (a.get(n, 0) / c[n] * 1000) if c.get(n, 0) >= 30 else None for a, c in zip(s_sum, s_cnt)]
    antes, durante = por_fase[0], por_fase[1]
    for n in nombres:
        if antes.get(n, 0) > 0 and durante.get(n, 0) < 0.05 * antes[n]:
            ind["sin_trafico"].append((n, antes[n], durante.get(n, 0.0)))
    return ind


# --------------------------------------------------------------------------------------
# Consola
# --------------------------------------------------------------------------------------
def tabla_texto(encabezado, filas, anchos):
    def fila(celdas):
        return "  " + "".join(str(c).ljust(w) if i == 0 else str(c).rjust(w)
                              for i, (c, w) in enumerate(zip(celdas, anchos)))
    return "\n".join([fila(encabezado), "  " + "-" * sum(anchos)] + [fila(f) for f in filas])


def imprimir_consola(ctx):
    fases, res, ind = ctx["fases"], ctx["resultado"], ctx["ind"]
    print("=" * 78)
    print(f"ANÁLISIS DE LA CORRIDA: {ctx['titulo']}")
    print("=" * 78)
    for n, a, b, _ in fases:
        print(f"  {n:<8} {hora_doble(a)} a {hora_doble(b)}  ({b - a} s)")
    nombres = [f[0] for f in fases]
    seccion = ""
    for m in ctx["metricas"]:
        if m.interna:
            continue
        r = res.get(m.id)
        if r is None:
            continue
        if m.seccion != seccion:
            seccion = m.seccion
            print(f"\n{'─' * 6} {seccion.upper()} {'─' * (70 - len(seccion))}")
        print(f"\n{m.nombre}  [{m.unidad}]")
        if r.get("error"):
            print(f"  ERROR: {r['error']}")
            continue
        if not r["series"]:
            print("  Sin datos en esta ventana.")
            continue
        filas, hay_marca = filas_resumen(r["series"], fases)
        print(tabla_texto([""] + nombres + ["Máx"], filas, [24, 12, 12, 12, 12]))
        if hay_marca:
            print("  " + NOTA_MUESTRAS)
    print(f"\n{'─' * 6} INDICADORES CALCULADOS {'─' * 47}")
    if ind["reparto"]:
        print("\nReparto de peticiones entre los backends [% del total]")
        print(tabla_texto([""] + nombres, [[n] + [num(v, 1) for v in vs] for n, vs in ind["reparto"].items()],
                          [24, 12, 12, 12]))
    print("\nRespuestas 5xx sobre peticiones totales de HAProxy [%]")
    print(tabla_texto([""] + nombres, [["5xx"] + [num(v, 2) for v in ind["error_5xx"]]], [24, 12, 12, 12]))
    if ind["latencia_app"]:
        print("\nDuración media de las peticiones en la aplicación [ms]")
        print(tabla_texto([""] + nombres, [[n] + [num(v) for v in vs] for n, vs in ind["latencia_app"].items()],
                          [24, 12, 12, 12]))
    for n, a, d in ind["sin_trafico"]:
        print(f"\n  Hecho medido: {n} pasó de {num(a)} a {num(d)} req/s en la fase «{nombres[1]}».")
    print(f"\n{'─' * 6} EVENTOS Y ALERTAS {'─' * 52}")
    if ctx["eventos_error"]:
        print(f"  No disponible: {ctx['eventos_error']}")
    elif not ctx["eventos"]:
        print("  Sin eventos en la ventana. Si el monitor se activó, el correo es la fuente\n"
              "  (README, sección 10.7 y 10.8).")
    for e in ctx["eventos"][:40]:
        print(f"  {hora_doble(e['ts'])}  [{e['categoria']}] {e['titulo']}")


# --------------------------------------------------------------------------------------
# Página HTML con gráficas SVG (sin bibliotecas externas)
# --------------------------------------------------------------------------------------
PALETA = {"backend1": "#2563eb", "backend2": "#ea580c", "backend3": "#16a34a"}
OTROS = ["#9333ea", "#0891b2", "#be123c", "#65a30d", "#ca8a04", "#475569"]

CSS = """
body{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;color:#1f2933;margin:0;background:#f5f7fa}
main{max-width:940px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:26px;margin:0 0 4px} h2{font-size:19px;margin:34px 0 8px;border-bottom:2px solid #d9e2ec;padding-bottom:4px}
h3{font-size:15px;margin:22px 0 4px} .sub{color:#52606d;margin:0 0 16px}
.tarjeta{background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:12px 14px;margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px} th,td{padding:4px 8px;text-align:right;border-bottom:1px solid #e4e7eb}
th:first-child,td:first-child{text-align:left} th{background:#f0f4f8;font-weight:600}
.leyenda{font-size:13px;margin:2px 0 6px} .leyenda span{margin-right:14px;white-space:nowrap}
.cuadro{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:-1px}
svg{width:100%;height:auto;display:block} .nota{color:#52606d;font-size:13px}
.hecho{background:#fff7e6;border-left:4px solid #f0a500;padding:6px 10px;margin:8px 0}
.cat{display:inline-block;font-size:12px;border-radius:4px;padding:0 6px;background:#e4e7eb}
"""


def marcas(maximo):
    if maximo <= 0:
        return [0, 1], 1
    bruto = maximo / 4
    pot = 10 ** math.floor(math.log10(bruto))
    paso = pot
    for k in (1, 2, 2.5, 5, 10):
        paso = k * pot
        if paso >= bruto:
            break
    n = math.ceil(maximo / paso - 1e-9)
    return [i * paso for i in range(n + 1)], n * paso


def color_de(nombre, orden):
    return PALETA.get(nombre) or OTROS[orden % len(OTROS)]


def grafica_svg(series, w0, w1, fases, ancho=880, alto=230):
    izq, der, arr, aba = 64, 14, 18, 28
    pw, ph = ancho - izq - der, alto - arr - aba
    maximo = max((v for s in series for _, v in s["puntos"]), default=0)
    ticks, tope = marcas(maximo)

    def x(t):
        return izq + (min(max(t, w0), w1) - w0) / (w1 - w0) * pw

    def y(v):
        return arr + ph - v / tope * ph

    p = [f'<svg viewBox="0 0 {ancho} {alto}" xmlns="http://www.w3.org/2000/svg" role="img">',
         f'<rect x="{izq}" y="{arr}" width="{pw}" height="{ph}" fill="#fff"/>']
    for nombre, a, b, col in fases:
        if b <= w0 or a >= w1:
            continue
        p.append(f'<rect x="{x(a):.1f}" y="{arr}" width="{x(b) - x(a):.1f}" height="{ph}" fill="{col}"/>')
        p.append(f'<text x="{(x(a) + x(b)) / 2:.1f}" y="{arr + 12}" font-size="11" fill="#52606d" '
                 f'text-anchor="middle">{html.escape(nombre)}</text>')
    for v in ticks:
        p.append(f'<line x1="{izq}" x2="{izq + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#d9e2ec"/>')
        p.append(f'<text x="{izq - 6}" y="{y(v) + 4:.1f}" font-size="11" fill="#52606d" '
                 f'text-anchor="end">{num(v)}</text>')
    for i in range(7):
        t = w0 + (w1 - w0) * i / 6
        p.append(f'<text x="{x(t):.1f}" y="{alto - 8}" font-size="11" fill="#52606d" '
                 f'text-anchor="middle">{datetime.fromtimestamp(t, tz=timezone.utc).strftime("%H:%M")}</text>')
    for _, a, b, _ in fases[1:]:
        p.append(f'<line x1="{x(a):.1f}" x2="{x(a):.1f}" y1="{arr}" y2="{arr + ph}" stroke="#9aa5b1" '
                 f'stroke-dasharray="4 3"/>')
    for i, s in enumerate(series):
        c = color_de(s["nombre"], i)
        pts = " ".join(f"{x(t):.1f},{y(v):.1f}" for t, v in s["puntos"] if w0 <= t <= w1)
        if pts:
            # Las primeras series más gruesas: si dos valen lo mismo, ninguna tapa del todo a la otra.
            ancho_linea = max(1.6, 4.0 - 1.1 * i)
            p.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="{ancho_linea}" '
                     f'stroke-linejoin="round"/>')
    p.append("</svg>")
    return "".join(p)


def generar_html(ctx) -> str:
    fases, res, ind = ctx["fases"], ctx["resultado"], ctx["ind"]
    nombres = [f[0] for f in fases]
    w0, w1 = ctx["ventana"]
    o = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
         f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Análisis: {html.escape(ctx['titulo'])}</title><style>{CSS}</style></head><body><main>",
         f"<h1>Análisis de la corrida: {html.escape(ctx['titulo'])}</h1>",
         "<p class='sub'>Proyecto 8 · Monitoreo de clúster HAProxy con Datadog · métricas consultadas a Datadog "
         f"el {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC</p>",
         "<div class='tarjeta'><table><tr><th>Fase</th><th>Desde</th><th>Hasta</th><th>Duración</th></tr>"]
    for n, a, b, c in fases:
        o.append(f"<tr><td><span class='cuadro' style='background:{c};border:1px solid #bcccdc'></span>{n}</td>"
                 f"<td>{hora_doble(a)}</td><td>{hora_doble(b)}</td><td>{b - a} s</td></tr>")
    o.append("</table></div>")
    if ctx["avisos"]:
        o.append("<div class='hecho'>" + "<br>".join(html.escape(a) for a in ctx["avisos"]) + "</div>")

    o.append("<h2>Indicadores calculados</h2>")
    if ind["reparto"]:
        o.append("<div class='tarjeta'><h3>Reparto de peticiones entre los backends (% del total)</h3><table>"
                 "<tr><th></th>" + "".join(f"<th>{n}</th>" for n in nombres) + "</tr>"
                 + "".join(f"<tr><td>{html.escape(k)}</td>" + "".join(f"<td>{num(v, 1)}</td>" for v in vs) + "</tr>"
                           for k, vs in ind["reparto"].items()) + "</table></div>")
    o.append("<div class='tarjeta'><h3>Respuestas 5xx sobre peticiones totales de HAProxy (%)</h3><table>"
             "<tr><th></th>" + "".join(f"<th>{n}</th>" for n in nombres) + "</tr><tr><td>5xx</td>"
             + "".join(f"<td>{num(v, 2)}</td>" for v in ind["error_5xx"]) + "</tr></table></div>")
    if ind["latencia_app"]:
        o.append("<div class='tarjeta'><h3>Duración media de las peticiones en la aplicación (ms)</h3><table>"
                 "<tr><th></th>" + "".join(f"<th>{n}</th>" for n in nombres) + "</tr>"
                 + "".join(f"<tr><td>{html.escape(k)}</td>" + "".join(f"<td>{num(v)}</td>" for v in vs) + "</tr>"
                           for k, vs in ind["latencia_app"].items()) + "</table></div>")
    for n, a, d in ind["sin_trafico"]:
        o.append(f"<div class='hecho'><b>Hecho medido:</b> {html.escape(n)} pasó de {num(a)} a {num(d)} req/s "
                 f"en la fase «{html.escape(nombres[1])}».</div>")

    seccion = ""
    for m in ctx["metricas"]:
        r = res.get(m.id)
        if m.interna or r is None:
            continue
        if m.seccion != seccion:
            seccion = m.seccion
            o.append(f"<h2>{html.escape(seccion)}</h2>")
        o.append(f"<div class='tarjeta'><h3>{html.escape(m.nombre)} <span class='nota'>[{html.escape(m.unidad)}]</span></h3>")
        if r.get("error"):
            o.append(f"<p class='nota'>Error al consultar: {html.escape(r['error'])}</p></div>")
            continue
        if not r["series"]:
            o.append("<p class='nota'>Sin datos en esta ventana.</p></div>")
            continue
        o.append("<div class='leyenda'>" + "".join(
            f"<span><i class='cuadro' style='background:{color_de(s['nombre'], i)}'></i>{html.escape(s['nombre'])}</span>"
            for i, s in enumerate(r["series"])) + "</div>")
        o.append(grafica_svg(r["series"], w0, w1, fases))
        o.append("<table><tr><th></th>" + "".join(f"<th>{n}</th>" for n in nombres) + "<th>Máx</th></tr>")
        filas, hay_marca = filas_resumen(r["series"], fases)
        for fila in filas:
            o.append(f"<tr><td>{html.escape(fila[0])}</td>" + "".join(f"<td>{c}</td>" for c in fila[1:]) + "</tr>")
        o.append("</table><p class='nota'>Promedio de cada fase; «Máx» es el mayor valor de las tres fases."
                 + (" " + html.escape(NOTA_MUESTRAS) if hay_marca else "") + "</p></div>")

    o.append("<h2>Eventos y alertas</h2><div class='tarjeta'>")
    if ctx["eventos_error"]:
        o.append(f"<p class='nota'>No disponible: {html.escape(ctx['eventos_error'])}</p>")
    elif not ctx["eventos"]:
        o.append("<p class='nota'>Sin eventos en la ventana. Si el monitor se activó, el correo es la fuente.</p>")
    else:
        o.append("<table><tr><th>Hora</th><th>Tipo</th><th>Evento</th></tr>" + "".join(
            f"<tr><td style='white-space:nowrap'>{hora_doble(e['ts'])}</td><td><span class='cat'>{e['categoria']}</span></td>"
            f"<td style='text-align:left'>{html.escape(e['titulo'])}</td></tr>" for e in ctx["eventos"][:60]) + "</table>")
    o.append("</div><h2>Consultas usadas</h2><div class='tarjeta'><p class='nota'>Cada gráfica sale de una consulta a la "
             "API de Datadog (<code>/api/v1/query</code>).</p><table>"
             + "".join(f"<tr><td style='text-align:left'><code>{html.escape(m.consulta)}</code></td></tr>"
                       for m in ctx["metricas"]) + "</table></div></main></body></html>")
    return "".join(o)


# --------------------------------------------------------------------------------------
# Archivos de salida
# --------------------------------------------------------------------------------------
def guardar(ctx, carpeta: Path):
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / f"{ctx['slug']}-{datetime.fromtimestamp(ctx['inicio'], tz=timezone.utc):%Y%m%dT%H%M%SZ}"
    fases, res = ctx["fases"], ctx["resultado"]

    ruta_series = base.with_name(base.name + "_series.csv")
    with ruta_series.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["seccion", "metrica", "unidad", "serie", "timestamp_utc", "valor"])
        for m in ctx["metricas"]:
            for s in res.get(m.id, {}).get("series", []):
                for t, v in s["puntos"]:
                    w.writerow([m.seccion, m.nombre, m.unidad, s["nombre"],
                                datetime.fromtimestamp(t, tz=timezone.utc).isoformat(), f"{v:.6g}"])

    ruta_fases = base.with_name(base.name + "_fases.csv")
    json_res = []
    with ruta_fases.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["seccion", "metrica", "unidad", "serie", "fase", "promedio", "minimo", "maximo", "muestras"])
        for m in ctx["metricas"]:
            r = res.get(m.id, {})
            entrada = {"seccion": m.seccion, "metrica": m.nombre, "unidad": m.unidad,
                       "consulta": m.consulta, "error": r.get("error"), "series": []}
            for s in r.get("series", []):
                por_fase = {}
                for n, a, b, _ in fases:
                    e = estadistica(s["puntos"], a, b)
                    por_fase[n] = e
                    if e:
                        w.writerow([m.seccion, m.nombre, m.unidad, s["nombre"], n, f"{e['promedio']:.6g}",
                                    f"{e['min']:.6g}", f"{e['max']:.6g}", e["n"]])
                entrada["series"].append({"nombre": s["nombre"], "fases": por_fase})
            json_res.append(entrada)

    ruta_json = base.with_name(base.name + ".json")
    ruta_json.write_text(json.dumps({
        "titulo": ctx["titulo"],
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "fases": [{"nombre": n, "desde_utc": datetime.fromtimestamp(a, tz=timezone.utc).isoformat(),
                   "hasta_utc": datetime.fromtimestamp(b, tz=timezone.utc).isoformat()} for n, a, b, _ in fases],
        "indicadores": ctx["ind"],
        "eventos": [{**e, "hora_utc": datetime.fromtimestamp(e["ts"], tz=timezone.utc).isoformat()}
                    for e in ctx["eventos"]],
        "metricas": json_res,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    ruta_html = base.with_name(base.name + ".html")
    ruta_html.write_text(generar_html(ctx), encoding="utf-8")
    return [ruta_html, ruta_fases, ruta_series, ruta_json]


# --------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Analiza una corrida de pruebas con las métricas de Datadog.")
    ap.add_argument("--inicio", required=True, help="Inicio de la carga, UTC: HH:MM:SS o AAAA-MM-DDTHH:MM:SS")
    ap.add_argument("--fin", required=True, help="Fin de la carga, UTC")
    ap.add_argument("--falla-desde", help="Inicio de la fase central dentro de la corrida (la falla, o el segundo tercio de una rampa)")
    ap.add_argument("--falla-hasta", help="Fin de la fase central (empieza la tercera fase)")
    ap.add_argument("--dia", default=None, help="Día UTC (AAAA-MM-DD) para las horas sin fecha; por defecto, hoy")
    ap.add_argument("--nombres-fases", default="Antes,Durante,Después",
                    help="Nombres de las tres fases, separados por comas (por ejemplo Baja,Media,Alta en una rampa)")
    ap.add_argument("--margen", type=int, default=180, help="Segundos antes y después de la carga (por defecto 180)")
    ap.add_argument("--test", default="", help="Etiqueta test:<nombre> de Artillery (agrega sus métricas)")
    ap.add_argument("--codigos", default="200,201,401,403,404,409,500,502,503",
                    help="Códigos HTTP de Artillery a consultar")
    ap.add_argument("--titulo", default="", help="Nombre de la corrida (por defecto, el de --test)")
    ap.add_argument("--salida", default="reportes_datadog", help="Carpeta de salida (relativa a la raíz del repo)")
    ap.add_argument("--url-api", default="", help=argparse.SUPPRESS)  # solo para pruebas del propio script
    args = ap.parse_args()

    try:
        dia = date.fromisoformat(args.dia) if args.dia else datetime.now(timezone.utc).date()
        ini, fin = instante(args.inicio, dia), instante(args.fin, dia)
        f_ini = instante(args.falla_desde, dia) if args.falla_desde else None
        f_fin = instante(args.falla_hasta, dia) if args.falla_hasta else None
    except ValueError as exc:
        print(f"ERROR: fecha u hora no válida ({exc}). Usa HH:MM:SS o AAAA-MM-DDTHH:MM:SS en UTC.")
        return 2
    if fin <= ini:
        print("ERROR: --fin debe ser posterior a --inicio.")
        return 2
    if bool(f_ini) != bool(f_fin) or (f_ini and not ini <= f_ini < f_fin <= fin):
        print("ERROR: --falla-desde y --falla-hasta van juntos y deben quedar dentro de la corrida.")
        return 2

    nombres_fases = [n.strip() for n in args.nombres_fases.split(",")]
    if len(nombres_fases) != 3 or not all(nombres_fases):
        print("ERROR: --nombres-fases necesita exactamente tres nombres separados por comas.")
        return 2

    claves = leer_claves(RAIZ / ".env")
    faltan = [k for k in CLAVES if not claves[k]] if not args.url_api else \
        [k for k in CLAVES[:2] if not claves[k]]
    if faltan:
        print("ERROR: faltan en .env o en el entorno: " + ", ".join(faltan))
        return 2
    base = args.url_api or url_base(claves["DD_SITE"])

    ahora = int(time.time())
    fases = definir_fases(ini, fin, args.margen, f_ini, f_fin, tuple(nombres_fases))
    w0, w1 = ini - args.margen, min(fin + args.margen, ahora)
    avisos = []
    if fin + args.margen > ahora:
        avisos.append("La ventana llega hasta ahora: las últimas métricas pueden tardar uno o dos minutos en "
                      "aparecer en Datadog. Vuelve a correr el análisis si faltan datos al final.")
    codigos = [c.strip() for c in args.codigos.split(",") if c.strip().isdigit()]
    metricas = construir_metricas(args.test.strip(), codigos)
    titulo = args.titulo or args.test or "corrida"
    slug = re.sub(r"[^a-z0-9_-]+", "-", titulo.lower()).strip("-") or "corrida"

    print(f"Consultando {len(metricas)} métricas a Datadog ({base.replace('https://', '')}) ...")
    resultado = {}
    errores = 0
    for m in metricas:
        try:
            resultado[m.id] = {"series": consultar_metrica(base, claves, m, w0, w1)}
        except ErrorAutenticacion as exc:
            print(f"ERROR: {exc}")
            return 1
        except ErrorDatadog as exc:
            errores += 1
            resultado[m.id] = {"series": [], "error": str(exc)}
    eventos, eventos_error = [], ""
    try:
        eventos = [e for e in consultar_eventos(base, claves, w0, min(fin + max(args.margen, 900), ahora))]
    except ErrorDatadog as exc:
        eventos_error = str(exc)

    ctx = {"titulo": titulo, "slug": slug, "inicio": ini, "fases": fases, "ventana": (w0, w1),
           "metricas": metricas, "resultado": resultado, "eventos": eventos, "eventos_error": eventos_error,
           "avisos": avisos, "ind": indicadores(resultado, fases)}
    imprimir_consola(ctx)
    archivos = guardar(ctx, RAIZ / args.salida)
    print("\n" + "=" * 78)
    print(f"Consultas: {len(metricas)} · con error: {errores} · sin datos: "
          f"{sum(1 for m in metricas if not resultado[m.id]['series'] and not resultado[m.id].get('error'))}")
    for a in archivos:
        print("  " + str(a.relative_to(RAIZ)).replace("\\", "/"))
    print("=" * 78)
    return 1 if errores == len(metricas) else 0


if __name__ == "__main__":
    sys.exit(main())