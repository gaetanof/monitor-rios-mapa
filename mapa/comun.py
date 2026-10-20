"""Utilidades compartidas del mapa de barrios: red, geometría y puertos.

El mapa es independiente del bot de Telegram y de X. Usa la misma API pública del INA.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("MAPA_CACHE", RAIZ / ".cache"))
SALIDA = Path(os.environ.get("MAPA_SALIDA", RAIZ / "datos"))
INA = "https://alerta.ina.gob.ar/a5"
UA = "monitor-rios-mapa/1.0 (+https://github.com/gaetanof/monitor-rios-mapa)"

# Escalas de Prefectura (vía INA) que entran en el mapa, por río, en orden aguas abajo.
# Se dejan afuera las auxiliares (caudales de represas, confluencias) y las de afluentes.
PUERTOS = {
    "parana": [9, 10, 11, 12, 131, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 33, 34, 35,
               36, 37, 38, 40, 41, 42, 45, 48],
    "paraguay": [55, 56, 57, 58, 59],
    "uruguay": [60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 84],
}
NOMBRE_RIO = {"parana": "Paraná", "paraguay": "Paraguay", "uruguay": "Uruguay"}

# SRTM voló del 11 al 22 de febrero de 2000: el agua que "ve" el modelo de elevación es la de esos días.
SRTM_DESDE, SRTM_HASTA = "2000-02-11", "2000-02-23"


def get_json(url: str, intentos: int = 4, timeout: int = 60):
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(3 * 2 ** i)
    raise RuntimeError(f"{url}: {ultimo}")


def get_bytes(url: str, intentos: int = 4, timeout: int = 120) -> bytes:
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            ultimo = e
        except Exception as e:  # noqa: BLE001
            ultimo = e
        time.sleep(3 * 2 ** i)
    raise RuntimeError(f"{url}: {ultimo}")


def observaciones(serie: int, desde: str, hasta: str) -> list[tuple[str, float]]:
    """Lecturas (fecha local AAAA-MM-DD, valor) de una serie de alturas del INA. Un valor por día (promedio)."""
    q = urllib.parse.urlencode({"timestart": desde + "T00:00:00Z", "timeend": hasta + "T23:59:59Z", "format": "json"})
    filas = get_json(f"{INA}/obs/puntual/series/{serie}/observaciones?{q}")
    if isinstance(filas, dict):
        filas = filas.get("rows", [])
    por_dia: dict[str, list[float]] = {}
    for f in filas:
        try:
            v = float(f["valor"])
        except (KeyError, TypeError, ValueError):
            continue
        # hora argentina (UTC-3): la lectura de Prefectura es de la mañana
        t = f["timestart"][:19].replace("Z", "")
        from datetime import datetime, timedelta
        d = (datetime.fromisoformat(t) - timedelta(hours=3)).date().isoformat()
        por_dia.setdefault(d, []).append(v)
    return sorted((d, sum(v) / len(v)) for d, v in por_dia.items())


def km(a, b) -> float:
    """Distancia en km entre dos puntos (lon, lat)."""
    R = 6371.0
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla, dlo = la2 - la1, math.radians(b[0] - a[0])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def guardar(nombre: str, obj) -> Path:
    SALIDA.mkdir(parents=True, exist_ok=True)
    p = SALIDA / nombre
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return p


def leer_cache(nombre: str):
    p = CACHE / nombre
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def escribir_cache(nombre: str, obj) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / nombre).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
