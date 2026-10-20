"""Barrios populares (RENABAP) cerca del Paraná, el Paraguay y el Uruguay, con su altura sobre el río.

Para cada barrio:
  - terreno: los píxeles SRTM (mosaicos Terrarium de AWS, z12, ~30 m) que caen dentro de su contorno.
    Se guardan percentiles (10, 25, 50, 75, 90) para saber qué parte del barrio se mojaría primero.
  - río: el nivel del agua en el SRTM cerca del barrio, tomado como el percentil 1 de los píxeles en un
    círculo que llega hasta el río (el SRTM aplana el agua y la deja como lo más bajo de la zona).
  - altura sobre el río = terreno − río. Es la subida que necesitaría el río, respecto de feb-2000,
    para llegar a esa parte del barrio.
  - escalas: las dos de Prefectura que lo encierran sobre el mismo río, con el peso de cada una.

Necesita red hacia AWS (mosaicos) y datos.gob.ar o el archivo del RENABAP: se corre en GitHub Actions.
    python -m mapa.barrios
"""
from __future__ import annotations

import io
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath
from PIL import Image

from .comun import CACHE, NOMBRE_RIO, get_bytes, get_json, guardar, km, leer_cache

MAX_KM = 10.0
Z = 12
TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
RENABAP = [
    "https://archivo.infraestructura.gob.ar/dataset/ssisu/20231205_info_publica.geojson",
]
RESPALDO = "https://raw.githubusercontent.com/3-ppp/caudal/main/public/barrios.json"   # mismo RENABAP, ya recortado
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_rivers_lake_centerlines.geojson"


# ---------- mosaicos de elevación
class DEM:
    def __init__(self, z: int = Z):
        self.z = z
        self.n = 2 ** z
        self.mem: dict[tuple[int, int], np.ndarray] = {}
        self.dir = CACHE / f"terrarium{z}"
        self.dir.mkdir(parents=True, exist_ok=True)

    def px(self, lon, lat):
        x = (np.asarray(lon) + 180) / 360 * self.n * 256
        la = np.radians(np.asarray(lat))
        y = (1 - np.log(np.tan(la) + 1 / np.cos(la)) / math.pi) / 2 * self.n * 256
        return x, y

    def lonlat(self, x, y):
        lon = np.asarray(x) / (self.n * 256) * 360 - 180
        lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * np.asarray(y) / (self.n * 256)))))
        return lon, lat

    def _bajar(self, t):
        f = self.dir / f"{t[0]}_{t[1]}.npy"
        if f.exists():
            return
        try:
            png = get_bytes(TERRARIUM.format(z=self.z, x=t[0], y=t[1]))
            a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.float32)
            e = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
        except Exception as ex:  # noqa: BLE001
            print("mosaico", t, ex, file=sys.stderr)
            e = np.full((256, 256), np.nan, np.float32)
        np.save(f, e.astype(np.float32))

    def precargar(self, tiles: set):
        falta = [t for t in tiles if not (self.dir / f"{t[0]}_{t[1]}.npy").exists()]
        print(f"mosaicos: {len(tiles)} necesarios, {len(falta)} a bajar")
        with ThreadPoolExecutor(16) as ex:
            list(ex.map(self._bajar, falta))

    def tile(self, t):
        if t not in self.mem:
            f = self.dir / f"{t[0]}_{t[1]}.npy"
            if not f.exists():
                self._bajar(t)
            self.mem[t] = np.load(f)
            if len(self.mem) > 900:
                self.mem.pop(next(iter(self.mem)))
        return self.mem[t]

    def ventana(self, x0, y0, x1, y1):
        """Matriz de elevaciones entre los píxeles globales [x0,x1) × [y0,y1)."""
        x0, y0, x1, y1 = int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1))
        out = np.full((y1 - y0, x1 - x0), np.nan, np.float32)
        for ty in range(y0 // 256, (y1 - 1) // 256 + 1):
            for tx in range(x0 // 256, (x1 - 1) // 256 + 1):
                a = self.tile((tx, ty))
                gx0, gy0 = max(x0, tx * 256), max(y0, ty * 256)
                gx1, gy1 = min(x1, tx * 256 + 256), min(y1, ty * 256 + 256)
                out[gy0 - y0:gy1 - y0, gx0 - x0:gx1 - x0] = a[gy0 - ty * 256:gy1 - ty * 256, gx0 - tx * 256:gx1 - tx * 256]
        return out, x0, y0

    def tiles_de(self, lon0, lat0, lon1, lat1):
        xa, ya = self.px(lon0, lat1)
        xb, yb = self.px(lon1, lat0)
        return {(tx, ty) for tx in range(int(xa) // 256, int(xb) // 256 + 1) for ty in range(int(ya) // 256, int(yb) // 256 + 1)}

    def metros_px(self, lat):
        return 156543.034 * math.cos(math.radians(lat)) / self.n


# ---------- ríos
def lineas(puertos: list[dict]) -> dict[str, list[np.ndarray]]:
    """Trazas por río: Natural Earth (Paraná, Uruguay) + la cadena de escalas donde la traza no llega."""
    f = CACHE / "ne_rivers.geojson"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(get_bytes(NE))
    ne = json.loads(f.read_text())
    L: dict[str, list[np.ndarray]] = {"parana": [], "uruguay": [], "paraguay": []}
    for ft in ne["features"]:
        nm = ft["properties"].get("name") or ""
        cla = ft["properties"].get("featurecla") or ""
        rio = "parana" if nm == "Paraná" and cla == "River" else "uruguay" if nm == "Uruguay" else None
        if not rio:
            continue
        g = ft["geometry"]
        partes = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for p in partes:
            a = np.array(p)
            if rio == "parana":
                a = a[a[:, 1] < -25.2]   # aguas abajo de Itaipú
            if len(a) > 1:
                L[rio].append(a)
    for rio in L:
        cad = [p["c"] for p in sorted((p for p in puertos if p["rio"] == rio), key=lambda p: p["orden"])]
        if rio == "uruguay":
            cad = [c for c in cad if c[1] < -32.3]
        if rio == "parana":
            cad = [c for c in cad if c[1] < -33.6]   # Delta: Natural Earth termina antes
        if len(cad) > 1:
            L[rio].append(np.array(cad))
    return L


def dist_linea(pt, segs: list[np.ndarray]) -> tuple[float, tuple[float, float]]:
    """Distancia (km) y punto más cercano de pt a un conjunto de polilíneas."""
    lon0, lat0 = pt
    kx = 111.32 * math.cos(math.radians(lat0))
    mejor = (1e9, pt)
    for a in segs:
        X = (a[:, 0] - lon0) * kx
        Y = (a[:, 1] - lat0) * 110.57
        x0, y0, x1, y1 = X[:-1], Y[:-1], X[1:], Y[1:]
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        t = np.clip(np.where(L2 > 0, -(x0 * dx + y0 * dy) / np.where(L2 > 0, L2, 1), 0), 0, 1)
        px, py = x0 + t * dx, y0 + t * dy
        d = np.hypot(px, py)
        i = int(np.argmin(d))
        if d[i] < mejor[0]:
            mejor = (float(d[i]), (lon0 + px[i] / kx, lat0 + py[i] / 110.57))
    return mejor


# ---------- barrios
def renabap() -> list[dict]:
    """Lista de barrios con id, nombre, localidad, provincia, familias, viviendas y contorno (anillo exterior)."""
    f = CACHE / "renabap.geojson"
    if not f.exists():
        for u in RENABAP:
            try:
                f.write_bytes(get_bytes(u, timeout=300))
                break
            except Exception as e:  # noqa: BLE001
                print("RENABAP", u, e, file=sys.stderr)
    out = []
    if f.exists():
        src = json.loads(f.read_text(encoding="utf-8"))
        for ft in src["features"]:
            g, p = ft["geometry"], ft["properties"]
            if not g:
                continue
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            anillo = max((pp[0] for pp in polys), key=len)
            out.append(dict(id=p.get("id_renabap"), n=p.get("nombre_barrio"), loc=p.get("localidad"),
                            dep=p.get("departamento"), prov=p.get("provincia"),
                            fam=p.get("cantidad_familias_aproximada"), viv=p.get("cantidad_viviendas_aproximadas"),
                            anillo=anillo, origen="renabap"))
        print("RENABAP:", len(out), "barrios en el registro")
        return out
    print("RENABAP no disponible: uso el recorte publicado (mismo registro, contornos simplificados)", file=sys.stderr)
    d = json.loads(get_bytes(RESPALDO))
    for b in d["barrios"]:
        out.append(dict(id=b["id"], n=b["n"], loc=b["loc"], dep=b.get("dep"), prov=b["prov"], fam=b.get("fam"),
                        viv=b.get("viv"), anillo=b["p"] + [b["p"][0]], origen="respaldo"))
    return out


def centroide(r):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(r, r[1:]):
        f = x0 * y1 - x1 * y0
        a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
    if abs(a) < 1e-14:
        return [sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r)]
    return [cx / (3 * a), cy / (3 * a)]


def simplificar(r, tol=3e-5):
    """Douglas–Peucker sobre un anillo (sin cerrar)."""
    pts = r[:-1] if r[0] == r[-1] else r
    if len(pts) < 6:
        return pts

    def dp(a):
        if len(a) < 3:
            return a
        (x0, y0), (x1, y1) = a[0], a[-1]
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy) or 1e-12
        ds = [abs(dy * (x - x0) - dx * (y - y0)) / n for x, y in a[1:-1]]
        i = max(range(len(ds)), key=ds.__getitem__)
        if ds[i] <= tol:
            return [a[0], a[-1]]
        return dp(a[:i + 2])[:-1] + dp(a[i + 1:])
    k = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    return dp(pts[:k + 1])[:-1] + dp(pts[k:] + [pts[0]])[:-1]


def radio_km(d: float) -> float:
    """Radio del círculo donde se busca el agua: tiene que pasar holgado la traza del río."""
    return min(max(d + 2.5, 3.0), 12.5)


ZONAS = [  # donde no se estima: el nivel lo maneja otra cosa que el caudal
    ("represa", "parana", lambda lo, la: -56.75 < lo < -55.0 and la > -27.75,
     "Embalse de Yacyretá: el nivel lo fija la represa y subió desde 2000."),
    ("delta", "parana", lambda lo, la: la < -33.62 and lo > -59.55,
     "Delta: la altura cambia en horas con la marea y el viento."),
]


def escalas(c, rio, puertos):
    """Las dos escalas del mismo río que encierran al barrio y el peso de la primera."""
    ps = [p for p in puertos if p["rio"] == rio and p.get("ancla") is not None]
    if not ps:
        return None
    ps.sort(key=lambda p: km(c, p["c"]))
    a = ps[0]
    for b in ps[1:4]:
        kx = 111.32 * math.cos(math.radians(c[1]))
        ax, ay = (a["c"][0] - c[0]) * kx, (a["c"][1] - c[1]) * 110.57
        bx, by = (b["c"][0] - c[0]) * kx, (b["c"][1] - c[1]) * 110.57
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        if L2 == 0 or math.sqrt(L2) > 220:
            continue
        t = -(ax * vx + ay * vy) / L2
        if 0 < t < 1:
            return [a["id"], b["id"], round(1 - t, 2)]
    return [a["id"], a["id"], 1.0]


def construir() -> dict:
    from .niveles import anclas
    puertos = leer_cache("puertos.json")
    anclas(puertos)
    L = lineas(puertos)
    todos = renabap()
    dem = DEM()

    cand = []
    for b in todos:
        r = b["anillo"]
        if not r or len(r) < 4:
            continue
        c = centroide(r)
        mejor = None
        for rio, segs in L.items():
            d, q = dist_linea(c, segs)
            if mejor is None or d < mejor[0]:
                mejor = (d, rio, q)
        if mejor[0] <= MAX_KM:
            cand.append((b, c, mejor))
    print(f"a menos de {MAX_KM:.0f} km de un río: {len(cand)}")

    tiles = set()
    for b, c, (d, rio, q) in cand:
        rad = radio_km(d) / 111.0
        tiles |= dem.tiles_de(c[0] - rad * 1.2, c[1] - rad, c[0] + rad * 1.2, c[1] + rad)
    dem.precargar(tiles)

    out = []
    for i, (b, c, (d, rio, q)) in enumerate(cand):
        r = np.array(b["anillo"], dtype=float)
        xs, ys = dem.px(r[:, 0], r[:, 1])
        x0, x1, y0, y1 = xs.min() - 1, xs.max() + 2, ys.min() - 1, ys.max() + 2
        win, ox, oy = dem.ventana(x0, y0, x1, y1)
        gy, gx = np.mgrid[0:win.shape[0], 0:win.shape[1]]
        cen = np.column_stack([(gx + ox + 0.5).ravel(), (gy + oy + 0.5).ravel()])
        dentro = MPath(np.column_stack([xs, ys])).contains_points(cen).reshape(win.shape)
        vals = win[dentro]
        vals = vals[np.isfinite(vals)]
        if vals.size < 3:   # barrio chico: el píxel del centro y los vecinos
            cx, cy = dem.px(c[0], c[1])
            w2, _, _ = dem.ventana(cx - 1, cy - 1, cx + 2, cy + 2)
            vals = w2[np.isfinite(w2)].ravel()
        if vals.size == 0:
            continue
        terreno = np.percentile(vals, [10, 25, 50, 75, 90])

        # nivel del río en el SRTM: lo más bajo en un círculo que llega hasta la traza
        rad_m = radio_km(d) * 1000
        mp = dem.metros_px(c[1])
        rp = rad_m / mp
        cx, cy = dem.px(c[0], c[1])
        w, ox, oy = dem.ventana(cx - rp, cy - rp, cx + rp, cy + rp)
        gy, gx = np.mgrid[0:w.shape[0], 0:w.shape[1]]
        disco = (gx + ox + 0.5 - cx) ** 2 + (gy + oy + 0.5 - cy) ** 2 <= rp * rp
        agua = w[disco & np.isfinite(w)]
        if agua.size < 50:
            continue
        rio_e = float(np.percentile(agua, 1))
        h = [round(float(t - rio_e), 1) for t in terreno]

        zona, nota = None, None
        for zid, zr, fn, txt in ZONAS:
            if zr == rio and fn(*c):
                zona, nota = zid, txt
        esc = escalas(c, rio, puertos)
        if esc is None:
            zona, nota = zona or "sin_escala", nota or "No hay una escala de Prefectura cerca sobre este río."
        anillo = simplificar([[round(x, 5), round(y, 5)] for x, y in b["anillo"]])
        out.append({
            "id": b["id"], "n": b["n"], "loc": b["loc"], "dep": b["dep"], "prov": b["prov"],
            "fam": b["fam"], "viv": b["viv"], "c": [round(c[0], 5), round(c[1], 5)],
            "rio": rio, "d": round(d, 1), "h": h, "e": round(float(terreno[2])), "er": round(rio_e),
            "esc": esc, "z": zona, "p": anillo,
        })
        if i % 200 == 0:
            print(f"  {i}/{len(cand)} {b['n']} ({b['loc']}): h {h} · {NOMBRE_RIO[rio]} a {d:.1f} km")

    notas = {zid: txt for zid, _, _, txt in ZONAS}
    notas["sin_escala"] = "No hay una escala de Prefectura cerca sobre este río."
    doc = {
        "fuente": "Registro Nacional de Barrios Populares (RENABAP), Secretaría de Integración Socio Urbana, CC BY 4.0",
        "elevacion": "SRTM (NASA, febrero de 2000) vía mosaicos Terrarium de AWS Open Data, ~30 m por píxel",
        "origen": todos[0]["origen"] if todos else None, "max_km": MAX_KM, "zonas": notas, "barrios": out,
    }
    p = guardar("barrios.json", doc)
    print(f"barrios.json: {len(out)} barrios, {p.stat().st_size / 1024:.0f} KB")
    hs = sorted(b["h"][1] for b in out)
    if hs:
        print("altura sobre el río (p25 del barrio), p10/p50/p90:", hs[len(hs) // 10], hs[len(hs) // 2], hs[9 * len(hs) // 10])
    return doc


if __name__ == "__main__":
    construir()
