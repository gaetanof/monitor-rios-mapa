"""Altura de cada escala día por día: medido (últimos 30 días) y pronóstico (próximos 30).

Orden de preferencia para cada día futuro, siempre empalmado con la última lectura medida:
  1. Pronóstico diario oficial del INA (Paraná cal 289, Uruguay medio cal 704): se usa su variación.
  2. Media semanal del INA (cal 434, 20 puertos del Paraná): variación, interpolada día a día.
  3. GloFAS (Copernicus, vía Open-Meteo): caudal pronosticado convertido a altura con la curva
     altura–caudal de cada puerto (h = a + b·ln Q, ajustada con 3 años de lecturas). Sólo si la curva
     ajusta bien (r >= 0,6). Es un modelo, no una medición.

    python -m mapa.niveles        # escribe site/data/niveles.json
"""
from __future__ import annotations

import json
import math
import statistics
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone

from .comun import (INA, PUERTOS, ULTIMA_HORA, escribir_cache, get_json, guardar, leer_cache, observaciones)

DIAS_ATRAS, DIAS_ADELANTE = 30, 30
R_MIN = 0.6

# series de pronóstico del INA -> escala de Prefectura (id de estación = id de serie en alturas_prefe)
INA_DIARIO = {
    289: {1540: 19, 3523: 20, 3524: 23, 3526: 24, 3527: 26, 3408: 29, 1542: 30, 3412: 34},
    704: {9644: 65, 9645: 68, 9646: 72},
}
INA_SEMANAL = {434: {26207: 18, 26208: 19, 26209: 20, 26210: 21, 26211: 22, 26212: 23, 26213: 24, 26214: 25,
                     26215: 26, 26216: 29, 26217: 30, 26218: 31, 26220: 33, 26221: 34, 26223: 36, 26224: 37,
                     26225: 38, 26226: 45}}
# tramos donde el desvío respecto del SRTM se interpola entre vecinos (no se mezcla río con embalse)
TRAMOS = [
    [9, 10, 11, 12], [131, 13, 14],
    [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37, 38, 40, 41, 42, 45, 48],
    [55, 56, 57, 58, 59],
    [60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74], [75, 76, 77], [78, 79, 80, 81, 82, 84],
]


def _local(ts: str) -> str:
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (t.astimezone(timezone.utc) - timedelta(hours=3)).date().isoformat()


def pronostico_ina(cal: int) -> dict[int, list[tuple[str, float]]]:
    d = get_json(f"{INA}/sim/calibrados/{cal}/corridas/last?format=json&includeProno=true")
    out: dict[int, list[tuple[str, float]]] = {}
    for s in d.get("series", []):
        filas: dict[str, float] = {}
        for p in s.get("pronosticos") or []:
            if (p.get("qualifier") or "main") in ("main", "medio"):
                filas[_local(p["timestart"])] = float(p["valor"])
        out[int(s["series_id"])] = sorted(filas.items())
    return out


def _interp(serie: list[tuple[str, float]], dia: str) -> float | None:
    if not serie or dia < serie[0][0] or dia > serie[-1][0]:
        return None
    for (d0, v0), (d1, v1) in zip(serie, serie[1:]):
        if d0 <= dia <= d1:
            a, b = date.fromisoformat(d0), date.fromisoformat(d1)
            f = (date.fromisoformat(dia) - a).days / max((b - a).days, 1)
            return v0 + (v1 - v0) * f
    return serie[-1][1] if dia == serie[-1][0] else None


def sin_saltos(obs: dict[str, float], tope: float = 1.0) -> dict[str, float]:
    """Saca lecturas sueltas que saltan más de 1 m respecto de los días vecinos (errores de carga)."""
    dias = sorted(obs)
    out = {}
    for k, d in enumerate(dias):
        vec = [obs[x] for x in dias[max(0, k - 3):k] + dias[k + 1:k + 4]]
        if len(vec) >= 2 and abs(obs[d] - statistics.median(vec)) > tope:
            continue
        out[d] = obs[d]
    return out


def anclas(puertos: list[dict]) -> None:
    """Completa el ancla SRTM de los puertos sin lecturas en feb-2000 con el desvío de sus vecinos del tramo."""
    by = {p["id"]: p for p in puertos}
    for tramo in TRAMOS:
        con = [(k, by[i]["ancla"] - by[i]["mediana"]) for k, i in enumerate(tramo)
               if i in by and by[i]["ancla"] is not None and by[i]["mediana"] is not None]
        for k, i in enumerate(tramo):
            p = by.get(i)
            if not p:
                continue
            p["ancla_est"] = False
            if p["ancla"] is not None or p["mediana"] is None or not con:
                continue
            ant = [c for c in con if c[0] < k]
            sig = [c for c in con if c[0] > k]
            if ant and sig:
                (k0, o0), (k1, o1) = ant[-1], sig[0]
                off = o0 + (o1 - o0) * (k - k0) / (k1 - k0)
            else:
                off = (ant[-1] if ant else sig[0])[1]
            p["ancla"] = round(p["mediana"] + off, 2)
            p["ancla_est"] = True


# ---------- GloFAS
FLOOD = "https://flood-api.open-meteo.com/v1/flood"


def _flood(lats, lons, **kw) -> list[dict]:
    q = {"latitude": ",".join(f"{x:.3f}" for x in lats), "longitude": ",".join(f"{x:.3f}" for x in lons),
         "daily": "river_discharge", **kw}
    r = get_json(FLOOD + "?" + urllib.parse.urlencode(q), timeout=120)
    return r if isinstance(r, list) else [r]


def curvas(puertos: list[dict]) -> dict:
    """Curva altura–caudal por puerto. Elige, entre 9 celdas vecinas de GloFAS, la de más caudal (el cauce)."""
    cache = leer_cache("curvas.json") or {}
    hoy = date.today()
    ini = (hoy - timedelta(days=365 * 3)).isoformat()
    fin = (hoy - timedelta(days=6)).isoformat()
    for p in puertos:
        k = str(p["id"])
        if k in cache and cache[k].get("hecho", "") >= (hoy - timedelta(days=60)).isoformat():
            continue
        lo, la = p["c"]
        offs = [(-0.05, -0.05), (0, -0.05), (0.05, -0.05), (-0.05, 0), (0, 0), (0.05, 0), (-0.05, 0.05), (0, 0.05), (0.05, 0.05)]
        try:
            res = _flood([la + b for a, b in offs], [lo + a for a, b in offs], start_date=ini, end_date=fin)
        except Exception as e:  # noqa: BLE001
            print("glofas", p["id"], e, file=sys.stderr)
            continue
        mejor, cel = None, None
        for (a, b), r in zip(offs, res):
            qs = [x for x in (r.get("daily", {}).get("river_discharge") or []) if x]
            if qs and (mejor is None or statistics.median(qs) > mejor[0]):
                mejor, cel = (statistics.median(qs), r["daily"]), (round(lo + a, 3), round(la + b, 3))
        if not mejor:
            continue
        Q = dict(zip(mejor[1]["time"], mejor[1]["river_discharge"]))
        pares = [(math.log(Q[d]), h) for d, h in p["hist"] if Q.get(d)]
        if len(pares) < 300:
            cache[k] = {"hecho": hoy.isoformat(), "ok": False}
            continue
        xs, ys = zip(*pares)
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in pares)
        syy = sum((y - my) ** 2 for y in ys)
        b = sxy / sxx if sxx else 0
        r = sxy / math.sqrt(sxx * syy) if sxx and syy else 0
        cache[k] = {"hecho": hoy.isoformat(), "ok": r >= R_MIN and b > 0, "b": round(b, 3), "r": round(r, 2),
                    "celda": cel, "n": len(pares), "qmed": round(statistics.median(math.exp(x) for x in xs))}
        print(f"curva {p['id']:4} {p['nombre'][:20]:20} b={b:.2f} r={r:.2f} n={len(pares)}")
    escribir_cache("curvas.json", cache)
    return cache


def glofas_pronostico(puertos: list[dict], cv: dict) -> dict[int, dict[str, float]]:
    pts = [(p["id"], cv[str(p["id"])]["celda"]) for p in puertos if cv.get(str(p["id"]), {}).get("ok")]
    out: dict[int, dict[str, float]] = {}
    for i in range(0, len(pts), 40):
        lote = pts[i:i + 40]
        try:
            res = _flood([c[1] for _, c in lote], [c[0] for _, c in lote], past_days=7, forecast_days=30)
        except Exception as e:  # noqa: BLE001
            print("glofas pronóstico", e, file=sys.stderr)
            continue
        for (pid, _), r in zip(lote, res):
            d = r.get("daily", {})
            out[pid] = {t: q for t, q in zip(d.get("time", []), d.get("river_discharge", [])) if q}
    return out


# ---------- armado
def construir(con_glofas: bool = True) -> dict:
    puertos = leer_cache("puertos.json")
    if not puertos:
        from .puertos import construir as cp
        puertos = cp()
    anclas(puertos)
    hoy = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    dias = [(hoy + timedelta(days=k)).isoformat() for k in range(-DIAS_ATRAS, DIAS_ADELANTE + 1)]

    # lecturas recientes
    rec: dict[int, dict[str, float]] = {}
    for p in puertos:
        try:
            rec[p["id"]] = dict(observaciones(p["id"], dias[0], hoy.isoformat()))
        except Exception as e:  # noqa: BLE001
            print("lecturas", p["id"], e, file=sys.stderr)
            rec[p["id"]] = {}

    diario: dict[int, list] = {}
    emision: dict[int, str] = {}
    for cal, mapa in INA_DIARIO.items():
        try:
            pr = pronostico_ina(cal)
            for sid, pid in mapa.items():
                if pr.get(sid):
                    diario[pid] = pr[sid]
        except Exception as e:  # noqa: BLE001
            print("INA", cal, e, file=sys.stderr)
    semanal: dict[int, list] = {}
    for cal, mapa in INA_SEMANAL.items():
        try:
            pr = pronostico_ina(cal)
            for sid, pid in mapa.items():
                if pr.get(sid):
                    semanal[pid] = pr[sid]
        except Exception as e:  # noqa: BLE001
            print("INA", cal, e, file=sys.stderr)

    cv, gq = {}, {}
    if con_glofas:
        try:
            cv = curvas(puertos)
            gq = glofas_pronostico(puertos, cv)
        except Exception as e:  # noqa: BLE001
            print("GloFAS no disponible:", e, file=sys.stderr)

    salida = []
    for p in puertos:
        obs = sin_saltos(rec.get(p["id"], {}))
        H, S = [], []
        ult = max((d for d in obs if d <= hoy.isoformat()), default=None)
        base = obs[ult] if ult else None
        fuentes = []
        for d in dias:
            if d in obs:
                H.append(round(obs[d], 2)); S.append("m")
                continue
            v, s = None, None
            if base is not None and ult and d > ult:
                # empalme continuo: cada serie arranca desde el último valor ya calculado (medido o pronóstico),
                # así no hay saltos cuando termina el pronóstico diario y sigue el semanal
                k = len(H) - 1
                while k >= 0 and H[k] is None:
                    k -= 1
                ref_d, ref_v = (dias[k], H[k]) if k >= 0 else (ult, base)
                for serie, tag in ((diario.get(p["id"]), "i"), (semanal.get(p["id"]), "s")):
                    f1 = _interp(serie or [], d)
                    f0 = _interp(serie or [], ref_d)
                    if f1 is not None and f0 is not None:
                        v, s = ref_v + f1 - f0, "i"
                        fuentes.append(tag)
                        break
                if v is None and p["id"] in gq and d in gq[p["id"]]:
                    q = gq[p["id"]]
                    # empalme: desde el último valor conocido (medido o INA)
                    k = len(H) - 1
                    while k >= 0 and H[k] is None:
                        k -= 1
                    ref_d = dias[k] if k >= 0 else None
                    if ref_d and q.get(ref_d):
                        v, s = H[k] + cv[str(p["id"])]["b"] * math.log(q[d] / q[ref_d]), "g"
                        fuentes.append("g")
            H.append(round(v, 2) if v is not None else None); S.append(s)
        c = cv.get(str(p["id"]), {})
        limpio = sin_saltos(dict(p.get("hist") or []), tope=1.5)
        if p.get("evac") is not None:   # lecturas imposibles (otra escala mezclada, error de carga)
            limpio = {d: v for d, v in limpio.items() if v <= p["evac"] + 6}
        hv = sorted(limpio.values())
        q = [round(hv[min(len(hv) - 1, int(k / 100 * (len(hv) - 1) + .5))], 2) for k in range(101)] if len(hv) > 200 else None
        mx = max(limpio.items(), key=lambda x: x[1]) if limpio else ("", None)
        salida.append({
            "id": p["id"], "n": p["nombre"], "rio": p["rio"], "c": p["c"], "al": p["alerta"], "ev": p["evac"],
            "ancla": p["ancla"], "ancla_est": p.get("ancla_est", False), "med": p["mediana"],
            "H": H, "src": "".join(x or "-" for x in S),
            "curva": {"b": c["b"], "r": c["r"]} if c.get("ok") else None,
            "fuentes": sorted(set(fuentes)),
            "hora": ULTIMA_HORA.get(p["id"]), "q": q, "max": [mx[0], round(mx[1], 2)] if mx[1] is not None else None,
        })
    doc = {"generado": datetime.now(timezone.utc).isoformat(timespec="minutes"), "hoy": hoy.isoformat(),
           "dias": dias, "puertos": salida}
    guardar("niveles.json", doc)
    n_g = sum(1 for p in salida if "g" in p["src"])
    print(f"niveles.json: {len(salida)} puertos, {len(dias)} días, {len(diario)} con INA diario, "
          f"{len(semanal)} con INA semanal, {n_g} con GloFAS")
    return doc


if __name__ == "__main__":
    construir(con_glofas="--sin-glofas" not in sys.argv)
