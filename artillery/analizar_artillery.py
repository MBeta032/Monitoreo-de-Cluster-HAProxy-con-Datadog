#!/usr/bin/env python3
"""Lee JSON de Artillery y crea un CSV nuevo; no ejecuta pruebas de carga.

Uso: python artillery/analizar_artillery.py artillery/resultados
RPS calculado: solicitudes / ventana entre firstMetricAt y lastMetricAt.
La ventana de metricas no equivale a la duracion configurada de las fases.
Latencias: http.response_time (TTFB en ms), no tiempo de descarga completa.
No se promedian percentiles ni se suman contadores de plugins por endpoint.
Los campos ausentes quedan vacios. No sobrescribe resultados existentes.
"""
import argparse
import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path


def numero(valor):
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError("Metrica no numerica")
    if not math.isfinite(valor) or valor < 0:
        raise ValueError("Metrica negativa o no finita")
    return valor


def analizar(ruta):
    datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    if not isinstance(datos, dict) or not isinstance(datos.get("aggregate"), dict):
        raise ValueError("Falta el objeto aggregate")
    a = datos["aggregate"]
    c = a.get("counters", {})
    if not isinstance(c, dict) or not c:
        raise ValueError("Faltan counters")
    s = a.get("summaries", {}).get("http.response_time")
    if not s:
        s = a.get("histograms", {}).get("http.response_time", {})
    advertencias = []
    solicitudes = numero(c.get("http.requests"))
    respuestas = numero(c.get("http.responses"))
    inicio = numero(a.get("firstMetricAt"))
    fin = numero(a.get("lastMetricAt"))
    duracion = None
    if inicio is not None and fin is not None:
        if fin < inicio:
            raise ValueError("Fin anterior al inicio")
        duracion = (fin - inicio) / 1000
    rps = solicitudes / duracion if solicitudes is not None and duracion else None
    reportado = numero(a.get("rates", {}).get("http.request_rate"))
    if rps and reportado is not None and abs(rps - reportado) / rps > 0.1:
        advertencias.append("RPS reportado y media calculada difieren mas del 10%")
    codigos = {}
    for clave, valor in c.items():
        coincidencia = re.fullmatch(r"http\.codes\.([1-5][0-9]{2})", clave)
        if coincidencia:
            cantidad = numero(valor)
            if cantidad is None or cantidad != int(cantidad):
                raise ValueError("Contador HTTP invalido")
            codigos[int(coincidencia[1])] = cantidad
    codigos_completos = respuestas is not None and sum(codigos.values()) == respuestas
    if not codigos_completos:
        advertencias.append("Codigos HTTP incompletos o sin total verificable")
    fila = {
        "archivo": ruta.name,
        "inicio_metricas_epoch_ms": inicio,
        "fin_metricas_epoch_ms": fin,
        "ventana_metricas_s": duracion,
        "solicitudes": solicitudes,
        "respuestas": respuestas,
        "rps_reportado_artillery": reportado,
        "rps_media_ventana": rps,
    }
    for metrica in ("mean", "p50", "p95", "p99"):
        fila[f"ttfb_{metrica}_ms"] = numero(s.get(metrica))
    for grupo in range(1, 6):
        valores = [v for k, v in codigos.items() if k // 100 == grupo]
        fila[f"http_{grupo}xx"] = sum(valores) if valores else (0 if codigos_completos else None)
    for metrica in ("created", "completed", "failed"):
        fila[f"vusers_{metrica}"] = numero(c.get(f"vusers.{metrica}"))
    ausentes = [k for k, v in fila.items() if v is None]
    if ausentes:
        advertencias.append("Campos ausentes: " + ", ".join(ausentes))
    fila["advertencias"] = " | ".join(advertencias)
    return fila


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "entradas", nargs="+", type=Path,
        help="Archivos JSON o carpetas"
    )
    parser.add_argument(
        "--salida", type=Path,
        help="Ruta de un CSV nuevo"
    )
    args = parser.parse_args()

    try:
        archivos = set()

        for entrada in args.entradas:
            encontrados = (
                sorted(entrada.glob("*.json"))
                if entrada.is_dir()
                else [entrada]
            )

            if not encontrados or any(
                not p.is_file() for p in encontrados
            ):
                raise ValueError(
                    f"Sin archivos validos: {entrada}"
                )

            archivos.update(p.resolve() for p in encontrados)

        filas = []

        for ruta in sorted(archivos, key=str):
            try:
                filas.append(analizar(ruta))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"{ruta.name}: {exc}") from exc

        sello = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        salida = args.salida or (
            Path("artillery/analisis") / f"resumen-{sello}.csv"
        )
        salida.parent.mkdir(parents=True, exist_ok=True)

        with salida.open(
            "x", encoding="utf-8-sig", newline=""
        ) as archivo:
            escritor = csv.DictWriter(
                archivo,
                fieldnames=list(filas[0]),
                delimiter=";"
            )
            escritor.writeheader()
            escritor.writerows(filas)

    except (ValueError, OSError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")

    for fila in filas:
        print(
            f"{fila['archivo']}: "
            f"solicitudes={fila['solicitudes']}, "
            f"p95_ms={fila['ttfb_p95_ms']}, "
            f"HTTP_5xx={fila['http_5xx']}, "
            f"usuarios_fallidos={fila['vusers_failed']}"
        )

        if fila["advertencias"]:
            print("  AVISO: " + fila["advertencias"])

    print(f"CSV creado: {salida.resolve()}")


if __name__ == "__main__":
    main()