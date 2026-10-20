"""Puertos del mapa: ubicación, umbrales, ancla SRTM e historial de 3 años.

Ancla SRTM: la altura que marcaba cada escala mientras volaba el SRTM (11 al 22/2/2000). El modelo de
elevación "congeló" el agua de esos días, así que la altura de un barrio sobre el río (que sale del
mismo SRTM) se traduce a la escala del puerto: el agua llega al barrio cuando la escala marca
ancla + altura del barrio. Así el cálculo queda atado a lo que mide Prefectura, no a un modelo.

    python -m mapa.puertos       # escribe .cache/puertos.json
"""
from __future__ import annotations

import statistics
import sys
from datetime import date, timedelta

from .comun import INA, NOMBRE_RIO, PUERTOS, SRTM_DESDE, SRTM_HASTA, escribir_cache, get_json, leer_cache, observaciones

ANIOS = 3


def construir(forzar: bool = False) -> list[dict]:
    viejo = {p["id"]: p for p in (leer_cache("puertos.json") or [])}
    est = {e["id"]: e for e in get_json(f"{INA}/obs/puntual/estaciones?tabla=alturas_prefe")}
    hoy = date.today()
    desde = (hoy - timedelta(days=365 * ANIOS)).isoformat()
    out = []
    for rio, ids in PUERTOS.items():
        for orden, i in enumerate(ids):
            e = est.get(i)
            if not e:
                print("falta la estación", i, file=sys.stderr)
                continue
            p = viejo.get(i) if not forzar else None
            if p is None or p.get("hist_hasta", "") < (hoy - timedelta(days=20)).isoformat():
                try:
                    srtm = [v for _, v in observaciones(i, SRTM_DESDE, SRTM_HASTA)]
                except Exception as ex:  # noqa: BLE001
                    print("ancla", i, ex, file=sys.stderr)
                    srtm = []
                try:
                    hist = observaciones(i, desde, hoy.isoformat())
                except Exception as ex:  # noqa: BLE001
                    print("historial", i, ex, file=sys.stderr)
                    hist = []
                vals = [v for _, v in hist]
                p = {
                    "id": i, "nombre": e["nombre"], "rio": rio, "orden": orden,
                    "c": [round(e["geom"]["coordinates"][0], 5), round(e["geom"]["coordinates"][1], 5)],
                    "alerta": e.get("nivel_alerta"), "evac": e.get("nivel_evacuacion"),
                    "ancla": round(statistics.median(srtm), 2) if len(srtm) >= 4 else None,
                    "n_ancla": len(srtm),
                    "mediana": round(statistics.median(vals), 2) if len(vals) > 200 else None,
                    "hist": hist, "hist_hasta": hoy.isoformat(),
                }
                print(f"{NOMBRE_RIO[rio]:9} {i:4} {e['nombre'][:22]:22} ancla {p['ancla']} ({len(srtm)} d) "
                      f"mediana {p['mediana']} ({len(vals)} d)")
            out.append(p)
    escribir_cache("puertos.json", out)
    return out


if __name__ == "__main__":
    construir("--forzar" in sys.argv)
