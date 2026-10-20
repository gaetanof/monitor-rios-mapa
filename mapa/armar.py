"""Arma el sitio en mapa/dist/: portada (mapa interactivo, con el resumen ya escrito en el HTML), datos,
tramos de río por escala, íconos y manifiesto. Las páginas de ríos y puertos las hace mapa.paginas.

    python -m mapa.armar        # después: python -m mapa.paginas && python -m mapa.og
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import shutil

from .comun import CACHE, RAIZ, SALIDA, km
from .web import (BASE, RIO_NOMBRE, cargar, estado_puerto, estados_barrios, fecha_txt, generado_local, nombre_puerto,
                  num, slug_puerto, titulo)

DIST = RAIZ / "dist"
SITE = RAIZ / "site"
E = html.escape


def tramos(base: dict, puertos: list[dict]) -> dict:
    """Corta cada río en tramos según la escala más cercana (del mismo río, a menos de 90 km)."""
    rio_de = {"Paraná": "parana", "Uruguay": "uruguay", "Paraguay": "paraguay"}
    feats, i = [], 0
    for f in base["rios"]["features"]:
        rio = rio_de.get((f["properties"] or {}).get("name"))
        if not rio:
            continue
        ps = [p for p in puertos if p["rio"] == rio and any(v is not None for v in p["H"])]
        g = f["geometry"]
        partes = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for linea in partes:
            # densificar a ~2 km para que los cortes caigan cerca de cada escala
            pts = [linea[0]]
            for a, b in zip(linea, linea[1:]):
                n = max(1, int(km(a, b) / 2))
                pts += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n] for k in range(1, n + 1)]
            actual, seg = None, []
            for a, b in zip(pts, pts[1:]):
                m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
                cerca = min(ps, key=lambda p: km(m, p["c"])) if ps else None
                pid = cerca["id"] if cerca and km(m, cerca["c"]) <= 90 else 0
                if pid != actual and seg:
                    feats.append({"type": "Feature", "id": i, "properties": {"i": i, "p": actual},
                                  "geometry": {"type": "LineString", "coordinates": [[round(x, 4), round(y, 4)] for x, y in seg]}})
                    i += 1
                    seg = [seg[-1]]
                actual = pid
                if not seg:
                    seg = [a]
                seg.append(b)
            if len(seg) > 1:
                feats.append({"type": "Feature", "id": i, "properties": {"i": i, "p": actual},
                              "geometry": {"type": "LineString", "coordinates": [[round(x, 4), round(y, 4)] for x, y in seg]}})
                i += 1
    return {"type": "FeatureCollection", "features": feats}


def datos_web(B: dict, N: dict) -> tuple[dict, dict, dict]:
    """Barrios livianos (sin contorno), contornos aparte y niveles con slug."""
    pts, cont = [], []
    for b in B["barrios"]:
        pts.append({k: b[k] for k in ("id", "n", "c", "rio", "d", "esc", "z", "fam") if k in b} |
                   {"loc": titulo(b.get("loc") or b.get("dep")), "prov": titulo(b.get("prov")), "h": b["h"][1:3]})
        if b.get("p") and len(b["p"]) > 2:
            cont.append({"type": "Feature", "id": b["id"], "properties": {"id": b["id"]},
                         "geometry": {"type": "Polygon", "coordinates": [b["p"] + [b["p"][0]]]}})
    for p in N["puertos"]:
        p["slug"] = slug_puerto(p)
        p["nom"] = nombre_puerto(p)
        if p["id"] == 77:   # Salto Grande arriba y abajo comparten coordenadas: se corre una para que no se tapen
            p["c"] = [p["c"][0], p["c"][1] + 0.025]
    return ({"zonas": B["zonas"], "max_km": B.get("max_km"), "barrios": pts},
            {"type": "FeatureCollection", "features": cont}, N)


def prerender(B: dict, N: dict, hoy: int) -> dict[str, str]:
    """El mismo resumen y las mismas listas que dibuja el JavaScript, ya escritos en el HTML."""
    estados_barrios(B, N)
    bs = B["barrios"]
    r2, r1 = [b for b in bs if b["S"][hoy] == 2], [b for b in bs if b["S"][hoy] == 1]
    fam = lambda l: num(sum(b["fam"] or 0 for b in l), 0)
    resumen = (f'<span class="lin"><b class="t-evac">{len(r2)} barrios</b> con agua probable</span>'
               f'<span class="lin"><b class="t-alerta">{len(r1)} barrios</b> cerca del agua</span>')
    filas = sorted(r2 + r1, key=lambda b: (-b["S"][hoy], -(b["R"][hoy] - b["h25"])))[:15]
    lista = "".join(
        f'<a class="fila" href="#b{b["id"]}"><span class="t"><b>{E(b["n"])}</b><span>{E(b["loc"])}, {E(b["prov"])} · '
        f'río {RIO_NOMBRE[b["rio"]]}</span></span><span class="m">'
        f'{"agua " + num(b["R"][hoy] - b["h25"], 1) + " m arriba" if b["S"][hoy] == 2 else "faltan " + num(b["h25"] - b["R"][hoy], 1) + " m"}</span></a>'
        for b in filas)
    pts = []
    for rio in RIO_NOMBRE:
        pts.append(f'<h3 class="grupo">Río {RIO_NOMBRE[rio]}</h3>')
        for p in N["puertos"]:
            if p["rio"] != rio or p["H"][hoy] is None or not p.get("activo", True):
                continue
            e = estado_puerto(p, hoy)
            est = "~" if p["src"][hoy] != "m" else ""
            pts.append(f'<a class="fila" href="{BASE}/puerto/{slug_puerto(p)}/"><span class="t"><b>{E(nombre_puerto(p))}</b>'
                       f'<span>{e.replace("_", " ")}</span></span><span class="m">{est}{num(p["H"][hoy])} m</span></a>')
    ev = sum(1 for p in N["puertos"] if p["H"][hoy] is not None and estado_puerto(p, hoy) == "evacuacion")
    al = sum(1 for p in N["puertos"] if p["H"][hoy] is not None and estado_puerto(p, hoy) == "alerta")
    return {"FECHA": f"Hoy, {fecha_txt(N['hoy'], True)}", "RESUMEN": resumen,
            "LISTA": f'<h3 class="grupo">Barrios más cerca del agua</h3>{lista}', "PUERTOS": "".join(pts),
            "SUB1": f"{len(r2)} con agua probable · {len(r1)} cerca", "SUB2": f'<span class="lin"><b class="t-evac">{ev} en evacuación</b> · <b class="t-alerta">{al} en alerta</b></span>',
            "_r2": len(r2), "_f2": fam(r2), "_r1": len(r1)}


def head_portada(N: dict, pre: dict) -> str:
    gen = generado_local(N)
    desc = (f"Altura de los ríos Paraná, Paraguay y Uruguay hoy y barrios populares en riesgo: {pre['_r2']} con agua probable "
            f"({pre['_f2']} familias). Datos de Prefectura e INA cada 4 horas.")
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Organization", "@id": f"{BASE}/#org", "name": "Monitor de Ríos", "url": f"{BASE}/",
         "logo": f"{BASE}/apple-touch-icon.png", "sameAs": ["https://x.com/MonitorDeRios"]},
        {"@type": "WebSite", "@id": f"{BASE}/#web", "name": "¿Llega el agua?", "alternateName": "Monitor de Ríos",
         "url": f"{BASE}/", "inLanguage": "es-AR", "publisher": {"@id": f"{BASE}/#org"}},
        {"@type": "Dataset", "name": "Altura de los ríos Paraná, Paraguay y Uruguay y barrios populares en riesgo de crecida",
         "description": "Altura diaria de las escalas de Prefectura Naval Argentina, pronósticos del INA, caudal estimado con GloFAS "
                        "y una estimación propia de qué barrios populares del RENABAP tendrían agua, día por día. Se actualiza cada 4 horas.",
         "url": f"{BASE}/", "creator": {"@id": f"{BASE}/#org"}, "isAccessibleForFree": True,
         "dateModified": gen.isoformat(timespec="minutes"), "temporalCoverage": f"{N['dias'][0]}/{N['dias'][-1]}",
         "spatialCoverage": {"@type": "Place", "name": "Ríos Paraná, Paraguay y Uruguay, Argentina"},
         "variableMeasured": [{"@type": "PropertyValue", "name": "Altura hidrométrica", "unitText": "m"},
                              {"@type": "PropertyValue", "name": "Estado estimado del barrio frente a la crecida"}],
         "isBasedOn": ["https://alerta.ina.gob.ar/", "https://contenidosweb.prefecturanaval.gob.ar/alturas/",
                       "https://www.argentina.gob.ar/habitat/integracion-socio-urbana/renabap", "https://www.globalfloods.eu/"],
         "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{BASE}/datos/puertos.csv"}]}]}
    tit = "Altura de los ríos Paraná y Uruguay hoy | ¿Llega el agua?"
    return f"""<title>{tit}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{BASE}/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="website"><meta property="og:site_name" content="Monitor de Ríos"><meta property="og:locale" content="es_AR">
<meta property="og:title" content="¿Llega el agua? Crecida de los ríos, barrio por barrio"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{BASE}/"><meta property="og:image" content="{BASE}/og/portada.png?v={gen.strftime('%Y%m%d%H')}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@MonitorDeRios">
<link rel="icon" href="{BASE}/favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="{BASE}/apple-touch-icon.png">
<link rel="manifest" href="{BASE}/manifest.webmanifest">
<meta name="theme-color" content="#F7F5EF" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#11181E" media="(prefers-color-scheme: dark)">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>"""


FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#F7F5EF"/>'
           '<path d="M8 40c6 0 6-5 12-5s6 5 12 5 6-5 12-5 6 5 12 5" fill="none" stroke="#1677B8" stroke-width="6" stroke-linecap="round"/>'
           '<path d="M8 52c6 0 6-5 12-5s6 5 12 5 6-5 12-5 6 5 12 5" fill="none" stroke="#1677B8" stroke-width="6" stroke-linecap="round" opacity=".45"/>'
           '<rect x="29" y="8" width="6" height="24" rx="3" fill="#1D2933"/></svg>')


def construir() -> None:
    B, N = cargar(SALIDA)
    hoy = N["dias"].index(N["hoy"]) if N["hoy"] in N["dias"] else 30
    base = json.loads((RAIZ / "base.json").read_text(encoding="utf-8"))
    DIST.mkdir(exist_ok=True)
    (DIST / "data").mkdir(exist_ok=True)
    (DIST / "vendor").mkdir(exist_ok=True)

    pre = prerender(json.loads(json.dumps(B)), json.loads(json.dumps(N)), hoy)
    bw, cont, nw = datos_web(B, N)
    tr = tramos(base, nw["puertos"])
    sep = (",", ":")
    for nombre, obj in (("barrios", bw), ("contornos", cont), ("niveles", nw), ("tramos", tr), ("base", base)):
        (DIST / "data" / f"{nombre}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=sep), encoding="utf-8")
    for f in ("maplibre-gl.js", "maplibre-gl.css"):
        shutil.copy(SITE / "vendor" / f, DIST / "vendor" / f)

    h = (SITE / "plantilla.html").read_text(encoding="utf-8")
    h = h.replace("<!--HEAD-->", head_portada(N, pre))
    for k, v in pre.items():
        if not k.startswith("_"):
            h = h.replace("{{" + k + "}}", v)
    version = hashlib.sha1(json.dumps([N["generado"]]).encode()).hexdigest()[:8]
    h = h.replace("{{V}}", version).replace("{{BASE}}", BASE)
    (DIST / "index.html").write_text(h, encoding="utf-8")
    (DIST / "404.html").write_text(
        f'<!doctype html><html lang="es-AR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Página no encontrada | Monitor de Ríos</title><meta name="robots" content="noindex"></head>'
        f'<body style="font:16px/1.5 system-ui;background:#F7F5EF;color:#1D2933;padding:40px 20px;max-width:640px;margin:auto">'
        f'<h1>No encontramos esa página</h1><p><a href="{BASE}/">Ir al mapa de barrios</a> · <a href="{BASE}/rio/parana/">Altura del río Paraná</a> · '
        f'<a href="{BASE}/rio/uruguay/">Altura del río Uruguay</a></p></body></html>', encoding="utf-8")
    (DIST / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    (DIST / "manifest.webmanifest").write_text(json.dumps({
        "name": "¿Llega el agua? · Monitor de Ríos", "short_name": "Llega el agua", "lang": "es-AR",
        "start_url": f"{BASE}/", "display": "standalone", "background_color": "#F7F5EF", "theme_color": "#1677B8",
        "icons": [{"src": f"{BASE}/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
                  {"src": f"{BASE}/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"}]}, ensure_ascii=False), encoding="utf-8")
    try:   # ícono para iOS y para el logo del JSON-LD
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (180, 180), "#F7F5EF")
        d = ImageDraw.Draw(im)
        for y, op in ((112, "#1677B8"), (146, "#8CBBDC")):
            pts = [(22 + k * 2, y - 12 * math.sin(k * 2 * math.pi / 34)) for k in range(0, 69)]
            d.line(pts, fill=op, width=14, joint="curve")
        d.rounded_rectangle([82, 22, 98, 90], 8, fill="#1D2933")
        im.save(DIST / "apple-touch-icon.png")
    except Exception as e:  # noqa: BLE001
        print("ícono:", e)
    CACHE.mkdir(parents=True, exist_ok=True)
    hu = json.loads((CACHE / "huellas.json").read_text()) if (CACHE / "huellas.json").exists() else {}
    hh = hashlib.sha1(json.dumps([pre["RESUMEN"], pre["PUERTOS"]]).encode()).hexdigest()
    if hu.get("/", {}).get("h") != hh:
        hu["/"] = {"h": hh, "lastmod": generado_local(N).isoformat(timespec="minutes")}
    (CACHE / "huellas.json").write_text(json.dumps(hu))
    print(f"dist: portada {len(h)//1024} KB · barrios {len(json.dumps(bw))//1024} KB · contornos {len(json.dumps(cont))//1024} KB · "
          f"tramos {len(tr['features'])}")


if __name__ == "__main__":
    construir()
