"""Páginas en HTML que Google puede leer sin JavaScript: ríos, puertos, contenido, sitemap y CSV.

Cada número sale de los datos del build, con su fuente y su fecha. Si no hay dato, la página lo dice.
    python -m mapa.paginas      # escribe en mapa/dist/ (después de mapa.armar)
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from pathlib import Path

from .comun import CACHE, RAIZ, SALIDA
from .web import (BASE, ESTADO_TXT, RIO_NOMBRE, cargar, estado_puerto, estados_barrios, fecha_txt, generado_local,
                  nombre_puerto, num, slug_puerto, ultimo_medido, variacion)

DIST = RAIZ / "dist"
E = html.escape
COLOR = {"normal": "#287D45", "atencion": "#F2C94C", "alerta": "#E67E22", "evacuacion": "#C0392B",
         "sin_umbral": "#FFFFFF", "sin_dato": "#9AA5AD"}
FORMA = {"normal": "c", "atencion": "t", "alerta": "d", "evacuacion": "o", "sin_umbral": "c", "sin_dato": "c"}


def icono(est: str, hueco=False, px=14) -> str:
    col = COLOR[est]
    borde = "#425466" if est == "sin_umbral" else col
    fill = "none" if hueco or est == "sin_dato" else col
    sw = 2.2 if (hueco or est in ("sin_dato", "sin_umbral")) else 0
    dash = ' stroke-dasharray="2 2"' if est == "sin_dato" else ""
    st = f'fill="{fill}" stroke="{borde}" stroke-width="{sw}"{dash}'
    f = FORMA[est]
    if f == "o":
        g = f'<polygon points="4.2,1 9.8,1 13,4.2 13,9.8 9.8,13 4.2,13 1,9.8 1,4.2" {st}/>'
    elif f == "d":
        g = f'<polygon points="7,1 13,7 7,13 1,7" {st}/>'
    elif f == "t":
        g = f'<polygon points="7,1.5 13,12.5 1,12.5" {st} stroke="#1D2933" stroke-width="{sw or 0.8}"/>'
    else:
        g = f'<circle cx="7" cy="7" r="5.6" {st}/>'
    return f'<svg class="ic" width="{px}" height="{px}" viewBox="0 0 14 14" aria-hidden="true">{g}</svg>'


# ---------------------------------------------------------------- armazón
CSS = """
:root{--bg:#F7F5EF;--surface:#fff;--surface-2:#EFECE3;--line:#DCD7CA;--ink:#1D2933;--ink-2:#425466;--ink-3:#5E6870;
--water:#1677B8;--water-text:#0F5F96;--water-soft:#D3E7F4;--evac:#B03A2E;--alerta:#A3500B;--normal:#287D45;
--f:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#11181E;--surface:#18222A;--surface-2:#202C35;--line:#2C3943;--ink:#E8EDF1;
--ink-2:#B4C0CA;--ink-3:#93A3B0;--water:#4BA3DE;--water-text:#7CC0EC;--water-soft:#1C3A50;--evac:#F08276;--alerta:#F5AA6B;
--normal:#6CC48A;color-scheme:dark}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--f);-webkit-font-smoothing:antialiased}
a{color:var(--water-text);text-underline-offset:2px}
.wrap{max-width:860px;margin:0 auto;padding:0 max(16px,env(safe-area-inset-right,0px)) 0 max(16px,env(safe-area-inset-left,0px))}
header.top{background:var(--surface);border-bottom:1px solid var(--line)}
header.top .wrap{display:flex;align-items:center;gap:12px;min-height:56px;flex-wrap:wrap}
.marca{display:flex;align-items:center;gap:8px;font-weight:700;color:var(--ink);text-decoration:none}
nav.menu{margin-left:auto;display:flex;gap:16px;font-size:14px;flex-wrap:wrap}
nav.menu a{color:var(--ink-2);text-decoration:none;padding:12px 0}nav.menu a:hover{color:var(--ink)}
.migas{font-size:13px;color:var(--ink-3);margin:20px 0 4px}.migas a{color:var(--ink-3)}
h1{font-size:clamp(26px,5vw,34px);line-height:1.15;letter-spacing:-.02em;margin:4px 0 12px;text-wrap:balance}
h2{font-size:20px;letter-spacing:-.01em;margin:36px 0 10px;text-wrap:balance}
p{max-width:68ch}
.dato{display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:var(--surface);border:1px solid var(--line);
border-radius:14px;padding:16px 18px;margin:16px 0}
.dato .v{font-size:44px;font-weight:800;letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1}
.dato .q{display:grid;gap:2px;font-size:14px;color:var(--ink-2)}
.pill{display:inline-flex;align-items:center;gap:6px;font-weight:700;font-size:14px;border-radius:999px;padding:3px 10px;background:var(--surface-2)}
.ic{vertical-align:-2px;flex:none}
table{border-collapse:collapse;width:100%;font-size:15px;background:var(--surface);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:13px;color:var(--ink-3);font-weight:600;background:var(--surface-2)}
td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
.tabla{overflow-x:auto;border:1px solid var(--line);border-radius:12px}
.grafico{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px}
.grafico svg{width:100%;height:auto;display:block}
.aviso{background:var(--surface-2);border-radius:12px;padding:12px 16px;font-size:14px;color:var(--ink-2);margin:28px 0}
.cta{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}
.cta a{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:10px;background:var(--water);color:#fff;
text-decoration:none;font-weight:600}.cta a.sec{background:var(--surface);color:var(--ink);border:1px solid var(--line)}
footer{margin-top:48px;border-top:1px solid var(--line);background:var(--surface);font-size:13px;color:var(--ink-3)}
footer .wrap{padding-block:20px}
.sub{color:var(--ink-2)}
dl.faq dt{font-weight:700;margin-top:14px}dl.faq dd{margin:4px 0 0}
"""

LOGO = ('<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 15c2.5 0 2.5-2 5-2s2.5 2 5 2 '
        '2.5-2 5-2 2.5 2 5 2" fill="none" stroke="#1677B8" stroke-width="2.4" stroke-linecap="round"/><path d="M2 20c2.5 0 '
        '2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2" fill="none" stroke="#1677B8" stroke-width="2.4" stroke-linecap="round" '
        'opacity=".45"/><rect x="11" y="3" width="2" height="9" rx="1" fill="currentColor"/></svg>')


def head(titulo: str, desc: str, ruta: str, og: str, jsonld: list | None = None, robots="index,follow,max-image-preview:large") -> str:
    url = BASE + ruta
    ld = f'<script type="application/ld+json">{json.dumps({"@context": "https://schema.org", "@graph": jsonld}, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(titulo)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{url}">
<meta name="robots" content="{robots}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Monitor de Ríos"><meta property="og:locale" content="es_AR">
<meta property="og:title" content="{E(titulo)}"><meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}{og}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@MonitorDeRios">
<link rel="icon" href="{BASE}/favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="{BASE}/apple-touch-icon.png">
<link rel="manifest" href="{BASE}/manifest.webmanifest">
<meta name="theme-color" content="#F7F5EF" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#11181E" media="(prefers-color-scheme: dark)">
{ld}"""


def pagina(titulo, desc, ruta, og, cuerpo, jsonld=None, gen="") -> str:
    return f"""<!doctype html>
<html lang="es-AR"><head>
{head(titulo, desc, ruta, og, jsonld)}
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap">
<style>{CSS}</style></head>
<body>
<header class="top"><div class="wrap"><a class="marca" href="{BASE}/">{LOGO} Monitor de Ríos</a>
<nav class="menu" aria-label="Secciones"><a href="{BASE}/">Mapa de barrios</a><a href="{BASE}/rio/parana/">Paraná</a>
<a href="{BASE}/rio/uruguay/">Uruguay</a><a href="{BASE}/rio/paraguay/">Paraguay</a><a href="{BASE}/como-se-calcula/">Cómo se calcula</a></nav></div></header>
<main class="wrap">
{cuerpo}
<div class="aviso">Monitor de Ríos es un proyecto independiente. No reemplaza los avisos de Defensa Civil ni del INA. Ante una emergencia llamá al <a href="tel:103">103</a>.</div>
</main>
<footer><div class="wrap">Datos: Prefectura Naval Argentina e INA (API alerta5), GloFAS (Copernicus) vía Open-Meteo, RENABAP (CC BY 4.0), SRTM (NASA).
{gen} · <a href="https://x.com/MonitorDeRios">@MonitorDeRios en X</a> · <a href="https://github.com/gaetanof/monitor-rios-mapa">Código abierto</a></div></footer>
</body></html>"""


# ---------------------------------------------------------------- gráfico
def grafico(p: dict, N: dict, hoy: int) -> str:
    H, T = p["H"], len(p["H"])
    vals = [v for v in H if v is not None] + [x for x in (p.get("al"), p.get("ev")) if x is not None]
    if not [v for v in H if v is not None]:
        return '<p class="sub">No hay lecturas en los últimos 30 días.</p>'
    lo, hi = int(min(vals) - 0.6), int(max(vals) + 1.6)
    W, Hh, l, r, tp, bt = 720, 260, 40, 12, 12, 30

    def x(k): return l + k / (T - 1) * (W - l - r)
    def y(v): return tp + (hi - v) / (hi - lo) * (Hh - tp - bt)
    s = [f'<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="Altura en {E(nombre_puerto(p))}: últimos 30 días y pronóstico">']
    paso = 2 if hi - lo > 8 else 1
    for v in range(lo, hi + 1, paso):
        s.append(f'<line x1="{l}" x2="{W-r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="currentColor" opacity=".12"/>'
                 f'<text x="{l-6}" y="{y(v)+4:.1f}" text-anchor="end" font-size="12" fill="currentColor" opacity=".6">{v}</text>')
    s.append(f'<rect x="{x(hoy):.1f}" y="{tp}" width="{W-r-x(hoy):.1f}" height="{Hh-tp-bt}" fill="#1677B8" opacity=".08"/>')
    s.append(f'<text x="{x(hoy)+6:.1f}" y="{tp+14}" font-size="12" fill="currentColor" opacity=".7">pronóstico</text>')
    for k, col, nom in ((p.get("al"), "#E67E22", "alerta"), (p.get("ev"), "#C0392B", "evacuación")):
        if k is not None:
            s.append(f'<line x1="{l}" x2="{W-r}" y1="{y(k):.1f}" y2="{y(k):.1f}" stroke="{col}" stroke-dasharray="5 4" stroke-width="1.5"/>'
                     f'<text x="{W-r}" y="{y(k)-5:.1f}" text-anchor="end" font-size="12" fill="{col}">{nom} {num(k)}</text>')

    def linea(desde, hasta):
        d, on = "", False
        for k in range(desde, hasta + 1):
            v = H[k]
            if v is None:
                on = False
                continue
            d += ("L" if on else "M") + f"{x(k):.1f} {y(v):.1f}"
            on = True
        return d
    s.append(f'<path d="{linea(0, hoy)}" fill="none" stroke="#1677B8" stroke-width="2.6" stroke-linejoin="round"/>')
    s.append(f'<path d="{linea(hoy, T-1)}" fill="none" stroke="#1677B8" stroke-width="2.2" stroke-dasharray="6 5"/>')
    if H[hoy] is not None:
        s.append(f'<circle cx="{x(hoy):.1f}" cy="{y(H[hoy]):.1f}" r="5" fill="#1677B8" stroke="#fff" stroke-width="2"/>')
    d = N["dias"]
    s.append(f'<text x="{l}" y="{Hh-8}" font-size="12" fill="currentColor" opacity=".6">{fecha_txt(d[0])}</text>'
             f'<text x="{x(hoy):.1f}" y="{Hh-8}" font-size="12" text-anchor="middle" font-weight="700" fill="currentColor">hoy</text>'
             f'<text x="{W-r}" y="{Hh-8}" font-size="12" text-anchor="end" fill="currentColor" opacity=".6">{fecha_txt(d[-1])}</text></svg>')
    return '<div class="grafico">' + "".join(s) + "</div>"


# ---------------------------------------------------------------- contenido
def resumen_puerto(p: dict, N: dict, hoy: int) -> dict:
    t = ultimo_medido(p, hoy)
    est = estado_puerto(p, t) if t is not None else "sin_dato"
    out = {"t": t, "h": p["H"][t] if t is not None else None, "est": est, "fecha": N["dias"][t] if t is not None else None,
           "d1": variacion(p, t, 1) if t is not None else None, "d7": variacion(p, t, 7) if t is not None else None}
    # si no hay medición reciente pero sí estimación del modelo para hoy
    if (t is None or hoy - t > 3) and p["H"][hoy] is not None:
        out.update(estimado=p["H"][hoy], est_src=p["src"][hoy])
    return out


def frase_variacion(d1, d7) -> str:
    if d1 is None:
        return ""
    if abs(d1) < 0.03:
        txt = "Está estable respecto de ayer"
    else:
        txt = f"{'Subió' if d1 > 0 else 'Bajó'} {num(abs(d1))} m en las últimas 24 horas"
    if d7 is not None:
        txt += f" y {'sube' if d7 > 0 else 'baja'} {num(abs(d7))} m en 7 días" if abs(d7) >= 0.03 else " y en 7 días quedó casi igual"
    return txt + "."


def construir() -> None:
    B, N = cargar(SALIDA)
    estados_barrios(B, N)
    hoy = N["dias"].index(N["hoy"]) if N["hoy"] in N["dias"] else 30
    gen = generado_local(N)
    gen_txt = f"Datos actualizados el {gen.strftime('%d/%m/%Y a las %H:%M')}"
    P = [p for p in N["puertos"] if any(v is not None for v in p["H"])]
    por_rio = {r: sorted([p for p in P if p["rio"] == r], key=lambda p: p.get("orden", 0)) for r in RIO_NOMBRE}
    orden_global = {p["id"]: i for i, p in enumerate(N["puertos"])}
    for r in por_rio:
        por_rio[r].sort(key=lambda p: orden_global[p["id"]])
    huellas = json.loads((CACHE / "huellas.json").read_text()) if (CACHE / "huellas.json").exists() else {}
    ahora = gen.isoformat(timespec="minutes")
    urls: list[tuple[str, str]] = []

    def escribir(ruta: str, contenido: str, clave_cambio: str):
        destino = DIST / ruta.strip("/") / "index.html" if ruta != "/" else DIST / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
        h = hashlib.sha1(clave_cambio.encode()).hexdigest()
        pr = huellas.get(ruta)
        lm = pr["lastmod"] if pr and pr["h"] == h else ahora
        huellas[ruta] = {"h": h, "lastmod": lm}
        urls.append((ruta, lm))

    org = {"@type": "Organization", "@id": f"{BASE}/#org", "name": "Monitor de Ríos", "url": f"{BASE}/",
           "logo": f"{BASE}/apple-touch-icon.png", "sameAs": ["https://x.com/MonitorDeRios"]}

    # ---- puertos
    for rio, lista in por_rio.items():
        for i, p in enumerate(lista):
            nom, sl, rp = nombre_puerto(p), slug_puerto(p), resumen_puerto(p, N, hoy)
            ruta = f"/puerto/{sl}/"
            rio_n = RIO_NOMBRE[rio]
            barrios = [b for b in B["barrios"] if b.get("esc") and p["id"] in b["esc"][:2] and not b["motivo"]]
            barrios.sort(key=lambda b: -((b["R"][hoy] or -99) - b["h25"]))
            con_agua = [b for b in barrios if b["S"][hoy] == 2]
            cerca = [b for b in barrios if b["S"][hoy] == 1]
            if rp["h"] is not None:
                valor = f'<span class="v">{num(rp["h"])} m</span>'
                quien = f'Lectura de Prefectura Naval del {fecha_txt(rp["fecha"], True)}'
                desc = (f'{nom} marca {num(rp["h"])} m ({fecha_txt(rp["fecha"])}, Prefectura): '
                        f'{ESTADO_TXT[rp["est"]].lower()}{f" (alerta {num(p["al"])} m, evacuación {num(p["ev"])} m)" if p.get("al") else ""}. '
                        f'{frase_variacion(rp["d1"], None)} Pronóstico y barrios cerca del agua.')
            else:
                valor = '<span class="v">sin dato</span>'
                quien = "No hay lecturas recientes de Prefectura para esta escala"
                desc = f"Altura del río {rio_n} en {nom}: lecturas de Prefectura, pronóstico y barrios cerca del agua. Se actualiza cada 4 horas."
            est_txt = ""
            if rp.get("estimado") is not None:
                fuente = "el pronóstico del INA" if rp["est_src"] == "i" else "el modelo GloFAS (Copernicus)"
                est_txt = f'<p>Para hoy hay un valor estimado con {fuente}: <b>~{num(rp["estimado"])} m</b>. Es una estimación, no una lectura.</p>'
            # umbrales
            if p.get("al") is not None and rp["h"] is not None:
                if p.get("ev") is not None and rp["h"] >= p["ev"]:
                    rel = f'Está {num(rp["h"] - p["ev"])} m por encima del nivel de evacuación.'
                elif rp["h"] >= p["al"]:
                    rel = f'Está {num(rp["h"] - p["al"])} m por encima del nivel de alerta y le faltan {num(p["ev"] - rp["h"])} m para la evacuación.' if p.get("ev") else ""
                else:
                    rel = f'Le faltan {num(p["al"] - rp["h"])} m para llegar al nivel de alerta.'
                umbrales = (f'<p>Para la escala de {E(nom)}, Prefectura fija la <b>alerta en {num(p["al"])} m</b> y la '
                            f'<b>evacuación en {num(p["ev"])} m</b>. {rel}</p>'
                            f'<p class="sub">Cada escala tiene su propio cero: estos números no se comparan con los de otros puertos. '
                            f'<a href="{BASE}/alerta-y-evacuacion/">Qué significan la alerta y la evacuación</a>.</p>')
            elif p.get("al") is None:
                umbrales = f"<p>Esta escala no tiene niveles de alerta y evacuación oficiales publicados.</p>"
            else:
                umbrales = (f'<p>Alerta: {num(p["al"])} m. Evacuación: {num(p["ev"])} m. No hay una lectura reciente para compararlas.</p>')
            # pronóstico
            filas = []
            for t in range(hoy + 1, min(hoy + 8, len(N["dias"]))):
                v, s = p["H"][t], p["src"][t]
                if v is None:
                    continue
                fu = "INA (oficial)" if s == "i" else "GloFAS (modelo)" if s == "g" else "Prefectura"
                e = estado_puerto(p, t)
                filas.append(f'<tr><td>{fecha_txt(N["dias"][t], True)}</td><td class="n">~{num(v)} m</td>'
                             f'<td>{icono(e, True)} {ESTADO_TXT[e]}</td><td>{fu}</td></tr>')
            pron = (f'<div class="tabla"><table><thead><tr><th>Día</th><th>Altura esperada</th><th>Estado</th><th>Fuente</th></tr></thead>'
                    f'<tbody>{"".join(filas)}</tbody></table></div><p class="sub">El pronóstico se empalma con la última lectura de Prefectura. '
                    f'Puede cambiar en la próxima actualización.</p>') if filas else "<p>No hay pronóstico para esta escala.</p>"
            # barrios
            if barrios:
                li = "".join(
                    f'<tr><td><a href="{BASE}/#b{b["id"]}">{E(b["n"])}</a></td><td>{E(b["loc"])}</td><td class="n">{b["fam"] or "s/d"}</td>'
                    f'<td>{"Agua probable" if b["S"][hoy] == 2 else "Cerca del agua" if b["S"][hoy] == 1 else "Lejos del agua" if b["S"][hoy] == 0 else "Sin estimación"}</td></tr>'
                    for b in barrios[:25])
                bar = (f'<p>{len(barrios)} barrios populares usan esta escala en la estimación. Hoy, '
                       f'<b>{len(con_agua)}</b> tendrían agua en su parte baja y <b>{len(cerca)}</b> quedarían a menos de 1 m.</p>'
                       f'<div class="tabla"><table><thead><tr><th>Barrio</th><th>Localidad</th><th>Familias</th><th>Hoy</th></tr></thead>'
                       f'<tbody>{li}</tbody></table></div><p class="sub">Es una estimación con un modelo de elevación que puede errar varios metros. '
                       f'<a href="{BASE}/como-se-calcula/">Cómo se calcula</a>.</p>')
            else:
                bar = "<p>No hay barrios populares estimados con esta escala.</p>"
            maxi = (f'<p>El máximo de los últimos 3 años fue <b>{num(p["max"][1])} m</b>, el {fecha_txt(p["max"][0])}/{p["max"][0][:4]}.</p>'
                    if p.get("max") else "")
            vec = []
            if i > 0:
                vec.append(f'<a class="sec" href="{BASE}/puerto/{slug_puerto(lista[i-1])}/">↑ {E(nombre_puerto(lista[i-1]))} (aguas arriba)</a>')
            if i + 1 < len(lista):
                vec.append(f'<a class="sec" href="{BASE}/puerto/{slug_puerto(lista[i+1])}/">↓ {E(nombre_puerto(lista[i+1]))} (aguas abajo)</a>')
            crece = ("No hay lecturas suficientes para saberlo." if rp["d1"] is None else frase_variacion(rp["d1"], rp["d7"]))
            cuerpo = f"""<div class="migas"><a href="{BASE}/">Inicio</a> › <a href="{BASE}/rio/{rio}/">Río {rio_n}</a> › {E(nom)}</div>
<h1>Altura del río {rio_n} en {E(nom)} hoy</h1>
<div class="dato">{valor}<div class="q"><span class="pill">{icono(rp["est"])} {ESTADO_TXT[rp["est"]]}</span><span>{quien}</span>
<span>{frase_variacion(rp["d1"], rp["d7"])}</span></div></div>
{est_txt}
{grafico(p, N, hoy)}
<div class="cta"><a href="{BASE}/#p{p["id"]}">Ver en el mapa con los barrios</a></div>
<h2>Pronóstico para {E(nom)}</h2>{pron}
<h2>Alerta y evacuación en {E(nom)}</h2>{umbrales}
<h2>Barrios que dependen de esta escala</h2>{bar}
<h2>Máximo reciente</h2>{maxi or "<p>Sin historial suficiente.</p>"}
<h2>Puertos cercanos</h2><div class="cta">{"".join(vec) or "<p>Es la única escala de este río.</p>"}</div>
<h2>Preguntas sobre la altura en {E(nom)}</h2>
<dl class="faq"><dt>¿Está creciendo el río en {E(nom)}?</dt><dd>{crece}</dd>
<dt>¿De dónde salen estos datos?</dt><dd>De la escala de Prefectura Naval Argentina en {E(nom)}, publicada por el INA. El pronóstico es del INA y, donde no hay, del modelo GloFAS. Se actualiza cada 4 horas.</dd>
<dt>¿La altura es la profundidad del río?</dt><dd>No. Es lo que marca la regla de Prefectura respecto de su propio cero. Sirve para comparar con días anteriores y con los niveles de alerta de esa misma escala.</dd></dl>"""
            ld = [org, {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Inicio", "item": f"{BASE}/"},
                {"@type": "ListItem", "position": 2, "name": f"Río {rio_n}", "item": f"{BASE}/rio/{rio}/"},
                {"@type": "ListItem", "position": 3, "name": nom, "item": f"{BASE}{ruta}"}]},
                {"@type": "Dataset", "name": f"Altura del río {rio_n} en {nom}",
                 "description": f"Lecturas diarias de la escala de Prefectura Naval Argentina en {nom} (últimos 30 días) y pronóstico. "
                                f"{('Última lectura: ' + num(rp['h']) + ' m el ' + fecha_txt(rp['fecha']) + '.') if rp['h'] is not None else ''}",
                 "url": f"{BASE}{ruta}", "creator": {"@id": f"{BASE}/#org"}, "isAccessibleForFree": True,
                 "dateModified": ahora, "temporalCoverage": f"{N['dias'][0]}/{N['dias'][-1]}",
                 "spatialCoverage": {"@type": "Place", "name": f"{nom}, río {rio_n}",
                                     "geo": {"@type": "GeoCoordinates", "latitude": p["c"][1], "longitude": p["c"][0]}},
                 "variableMeasured": {"@type": "PropertyValue", "name": "Altura hidrométrica", "unitText": "m"},
                 "isBasedOn": ["https://alerta.ina.gob.ar/", "https://contenidosweb.prefecturanaval.gob.ar/alturas/"]}]
            tit = f"Altura del río {rio_n} en {nom} hoy | Monitor de Ríos"
            if len(tit) > 62:
                tit = f"Altura del río {rio_n} en {nom} hoy"
            escribir(ruta, pagina(tit, desc[:158], ruta, f"/og/puerto/{sl}.png?v={gen.strftime('%Y%m%d%H')}", cuerpo, ld, gen_txt),
                     json.dumps([p["H"], p["src"]]))

    # ---- ríos
    for rio, lista in por_rio.items():
        rio_n = RIO_NOMBRE[rio]
        res = [(p, resumen_puerto(p, N, hoy)) for p in lista]
        ev = [p for p, r in res if r["est"] == "evacuacion"]
        al = [p for p, r in res if r["est"] == "alerta"]
        filas = "".join(
            f'<tr><td><a href="{BASE}/puerto/{slug_puerto(p)}/">{E(nombre_puerto(p))}</a></td>'
            f'<td class="n">{num(r["h"]) + " m" if r["h"] is not None else ("~" + num(r["estimado"]) + " m (estimado)" if r.get("estimado") is not None else "sin dato")}</td>'
            f'<td class="n">{("+" if (r["d1"] or 0) > 0 else "") + num(r["d1"]) + " m" if r["d1"] is not None else "s/d"}</td>'
            f'<td>{icono(r["est"])} {ESTADO_TXT[r["est"]]}</td><td class="n">{fecha_txt(r["fecha"]) if r["fecha"] else "s/d"}</td></tr>'
            for p, r in res)
        destacados = sorted([(p, r) for p, r in res if r["h"] is not None and p.get("al")], key=lambda x: -(x[1]["h"] - x[0]["al"]))[:2]
        crecida = ""
        if ev or al:
            crecida = (f'<h2>La crecida hoy</h2><p>Hoy {len(ev)} {"escala está" if len(ev) == 1 else "escalas están"} en evacuación'
                       f'{" (" + ", ".join(nombre_puerto(p) for p in ev) + ")" if ev else ""} y {len(al)} en alerta'
                       f'{" (" + ", ".join(nombre_puerto(p) for p in al) + ")" if al else ""}, según las lecturas de Prefectura.</p>')
        bs = [b for b in B["barrios"] if b["rio"] == rio]
        r2, r1 = [b for b in bs if b["S"][hoy] == 2], [b for b in bs if b["S"][hoy] == 1]
        fam = lambda l: sum(b["fam"] or 0 for b in l)
        primer = (f"{', '.join(nombre_puerto(p) + ' ' + num(r['h']) + ' m (' + ESTADO_TXT[r['est']].lower() + ')' for p, r in destacados)}. "
                  if destacados else "")
        desc = f"{primer}Altura, tendencia y pronóstico en {len(lista)} puertos del río {rio_n}. Datos de Prefectura e INA, cada 4 horas."
        cuerpo = f"""<div class="migas"><a href="{BASE}/">Inicio</a> › Río {rio_n}</div>
<h1>Altura del río {rio_n} hoy</h1>
<p>Lecturas de las {len(lista)} escalas de Prefectura Naval sobre el río {rio_n}, de aguas arriba a aguas abajo. {gen_txt}.</p>
<div class="tabla"><table><thead><tr><th>Puerto</th><th>Altura</th><th>24 h</th><th>Estado</th><th>Lectura</th></tr></thead><tbody>{filas}</tbody></table></div>
<p class="sub">Cada escala tiene su propio cero: no compares los metros de un puerto con los de otro. El estado se mide contra la alerta y la evacuación de cada escala.</p>
{crecida}
<h2>¿Llega el agua a los barrios?</h2>
<p>Según nuestra estimación, hoy {len(r2)} barrios populares junto al río {rio_n} ({num(fam(r2), 0)} familias) tendrían agua en su parte baja y {len(r1)} ({num(fam(r1), 0)} familias) quedarían a menos de 1 m.</p>
<div class="cta"><a href="{BASE}/#{rio}">Ver el mapa de barrios del {rio_n}</a><a class="sec" href="{BASE}/como-se-calcula/">Cómo se calcula</a></div>"""
        ld = [org, {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Inicio", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": f"Río {rio_n}", "item": f"{BASE}/rio/{rio}/"}]}]
        escribir(f"/rio/{rio}/", pagina(f"Altura del río {rio_n} hoy: todos los puertos | Monitor de Ríos", desc[:158], f"/rio/{rio}/",
                                        f"/og/rio/{rio}.png?v={gen.strftime('%Y%m%d%H')}", cuerpo, ld, gen_txt),
                 json.dumps([[p["H"], p["src"]] for p in lista]))

    # ---- contenido fijo
    umb = "".join(f'<tr><td><a href="{BASE}/puerto/{slug_puerto(p)}/">{E(nombre_puerto(p))}</a></td><td>{RIO_NOMBRE[p["rio"]]}</td>'
                  f'<td class="n">{num(p["al"])} m</td><td class="n">{num(p["ev"])} m</td></tr>'
                  for r in RIO_NOMBRE for p in por_rio[r] if p.get("al") is not None)
    cuerpo = f"""<div class="migas"><a href="{BASE}/">Inicio</a> › Alerta y evacuación</div>
<h1>Qué significan la alerta y la evacuación en los ríos</h1>
<p>Prefectura Naval Argentina fija, para cada escala, dos alturas de referencia. Cuando el río llega a la <b>alerta</b>, empiezan los problemas en las zonas más bajas y conviene estar atento a los avisos. Cuando llega a la <b>evacuación</b>, el agua afecta viviendas y las autoridades pueden pedir que la gente deje su casa.</p>
<p>Los valores cambian de un puerto a otro porque cada escala tiene su propio cero. Por eso 5 m en Rosario no es lo mismo que 5 m en Corrientes: lo que importa es cuánto le falta a cada escala para su propia alerta.</p>
<h2>Qué hacer</h2>
<p>Seguí las indicaciones de Defensa Civil de tu localidad (teléfono <a href="tel:103">103</a>). Monitor de Ríos muestra datos y estimaciones, pero no es un aviso oficial.</p>
<h2>Alerta y evacuación de cada escala</h2>
<div class="tabla"><table><thead><tr><th>Escala</th><th>Río</th><th>Alerta</th><th>Evacuación</th></tr></thead><tbody>{umb}</tbody></table></div>
<p class="sub">Valores publicados por Prefectura Naval a través de la API del INA.</p>"""
    escribir("/alerta-y-evacuacion/", pagina("Qué significan alerta y evacuación en los ríos | Monitor de Ríos",
             "Qué significan los niveles de alerta y evacuación de Prefectura, por qué cambian entre puertos y la tabla de umbrales de cada escala del Paraná, Paraguay y Uruguay.",
             "/alerta-y-evacuacion/", "/og/portada.png", cuerpo, [org], gen_txt), umb)

    cuerpo = f"""<div class="migas"><a href="{BASE}/">Inicio</a> › Cómo se calcula</div>
<h1>Cómo se calcula si llega el agua a un barrio</h1>
<p><b>En corto:</b> es una estimación, no un aviso oficial. El modelo de terreno puede errar varios metros. No estimamos en el Delta ni en el embalse de Yacyretá.</p>
<h2>1. Qué tan alto está el barrio</h2>
<p>Para cada barrio del Registro Nacional de Barrios Populares (RENABAP) a menos de 10 km del Paraná, el Paraguay o el Uruguay, miramos el terreno dentro de su contorno en el modelo de elevación SRTM de la NASA (unos 30 m por píxel) y lo comparamos con el nivel del agua cercano en el mismo modelo. Usamos la cuarta parte más baja del barrio, que es la que se moja primero.</p>
<h2>2. La foto de febrero de 2000</h2>
<p>El SRTM se tomó entre el 11 y el 22 de febrero de 2000, así que el agua que muestra es la de esos días. Buscamos qué marcaba cada escala de Prefectura en esa fecha. Así la altura del barrio se traduce a un número de la escala: el agua llega cuando la escala marca lo que marcaba en febrero de 2000 más la altura del barrio. Por ejemplo: "se mojaría cuando Barranqueras marque 7,1 m".</p>
<h2>3. El río día por día</h2>
<p>Los días pasados usan la lectura de Prefectura. Los futuros siguen el pronóstico oficial del INA, siempre desde la última lectura. Donde el INA no pronostica, usamos el caudal de GloFAS (Copernicus) convertido a altura con la relación que tuvo cada escala en los últimos 3 años. Entre dos escalas, la subida se reparte según la distancia.</p>
<h2>4. Los colores</h2>
<p><b>Agua probable</b>: el río supera la parte baja del barrio. <b>Cerca del agua</b>: le falta menos de 1 m. <b>Lejos del agua</b>: le falta más. <b>No lo estimamos</b>: el barrio está en una zona donde el método no sirve o el modelo da algo imposible.</p>
<h2>Qué no tiene en cuenta</h2>
<p>El SRTM ve techos y árboles y puede errar varios metros. No conoce defensas, terraplenes ni desagües, ni la lluvia local. En el embalse de Yacyretá el nivel lo fija la represa y en el Delta la altura cambia en horas con la marea y el viento: ahí no estimamos. Marcamos como dudosos los barrios que el modelo pondría bajo el agua en un día normal.</p>
<h2>Fuentes</h2>
<p>Barrios: RENABAP, Secretaría de Integración Socio Urbana, CC BY 4.0. Elevación: SRTM (NASA) vía Terrain Tiles de AWS Open Data. Alturas y pronósticos: Prefectura Naval Argentina e INA (API alerta5). Caudal: GloFAS, Copernicus Emergency Management Service, vía Open-Meteo. Mapa: OpenStreetMap y OpenFreeMap; foto satelital de Esri. La idea de cruzar la crecida con los barrios populares es de <a href="https://github.com/3-ppp/caudal">caudal</a>, de Pedro (@pppp_edro); el método y la interfaz de este mapa son propios.</p>
<div class="cta"><a href="{BASE}/">Ir al mapa</a><a class="sec" href="https://github.com/gaetanof/monitor-rios-mapa">Ver el código</a></div>"""
    escribir("/como-se-calcula/", pagina("Cómo se calcula si llega el agua a un barrio | Monitor de Ríos",
             "Método de ¿Llega el agua?: altura de cada barrio popular con el SRTM, anclada a la escala de Prefectura de febrero de 2000, y pronóstico del INA y GloFAS.",
             "/como-se-calcula/", "/og/portada.png", cuerpo, [org], gen_txt), "metodo-v1")

    # ---- CSV
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["puerto", "rio", "fecha", "altura_m", "fuente", "alerta_m", "evacuacion_m"])
    for p in P:
        for t, d in enumerate(N["dias"]):
            if p["H"][t] is not None:
                w.writerow([nombre_puerto(p), RIO_NOMBRE[p["rio"]], d, p["H"][t],
                            {"m": "Prefectura (medido)", "i": "INA (pronóstico)", "g": "GloFAS (modelo)"}.get(p["src"][t], ""),
                            p.get("al"), p.get("ev")])
    (DIST / "datos").mkdir(parents=True, exist_ok=True)
    (DIST / "datos" / "puertos.csv").write_text(buf.getvalue(), encoding="utf-8")

    # ---- sitemap (la portada la agrega armar con su propia huella)
    portada = huellas.get("/", {}).get("lastmod", ahora)
    todas = [("/", portada)] + urls
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml += [f"<url><loc>{BASE}{r}</loc><lastmod>{lm}</lastmod></url>" for r, lm in todas]
    xml.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(xml), encoding="utf-8")
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "huellas.json").write_text(json.dumps(huellas))
    print(f"páginas: {len(urls)} + portada; sitemap con {len(todas)} URLs")


if __name__ == "__main__":
    construir()
