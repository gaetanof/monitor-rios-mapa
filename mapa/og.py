"""Imágenes para compartir (1200 x 630): portada, ríos y puertos, con el dato del día.

    python -m mapa.og
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .comun import RAIZ, SALIDA
from .paginas import DIST, resumen_puerto
from .web import ESTADO_TXT, RIO_NOMBRE, cargar, estados_barrios, fecha_txt, generado_local, nombre_puerto, num, slug_puerto

FUENTE = RAIZ / "site" / "fuentes" / "Inter.ttf"
BG, INK, INK2, WATER = "#F7F5EF", "#1D2933", "#425466", "#1677B8"
COL = {"normal": "#287D45", "atencion": "#F2C94C", "alerta": "#E67E22", "evacuacion": "#C0392B",
       "sin_umbral": "#FFFFFF", "sin_dato": "#9AA5AD"}


def f(px, peso="Regular"):
    x = ImageFont.truetype(str(FUENTE), px)
    try:
        x.set_variation_by_name(peso)
    except Exception:  # noqa: BLE001
        pass
    return x


def forma(d: ImageDraw.ImageDraw, est: str, cx, cy, r):
    col = COL[est]
    if est == "evacuacion":
        k = r * 0.41
        pts = [(cx - k, cy - r), (cx + k, cy - r), (cx + r, cy - k), (cx + r, cy + k), (cx + k, cy + r), (cx - k, cy + r), (cx - r, cy + k), (cx - r, cy - k)]
        d.polygon(pts, fill=col)
    elif est == "alerta":
        d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=col)
    elif est == "atencion":
        d.polygon([(cx, cy - r), (cx + r, cy + r * .85), (cx - r, cy + r * .85)], fill=col, outline=INK)
    else:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col if est != "sin_umbral" else "#fff", outline=INK2 if est == "sin_umbral" else None, width=4)


def lienzo():
    im = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1200, 10], fill=WATER)
    d.text((64, 52), "Monitor de Ríos", font=f(30, "SemiBold"), fill=INK2)
    return im, d


def pie(d, txt):
    d.text((64, 560), txt, font=f(24), fill=INK2)


def spark(d, H, hoy, x0, y0, w, h):
    vals = [v for v in H[max(0, hoy - 14):hoy + 15] if v is not None]
    if len(vals) < 2:
        return
    lo, hi = min(vals) - .2, max(vals) + .2
    tramo = list(range(max(0, hoy - 14), min(len(H), hoy + 15)))
    def X(k): return x0 + (k - tramo[0]) / (len(tramo) - 1) * w
    def Y(v): return y0 + (hi - v) / (hi - lo) * h
    pas = [(X(k), Y(H[k])) for k in tramo if k <= hoy and H[k] is not None]
    fut = [(X(k), Y(H[k])) for k in tramo if k >= hoy and H[k] is not None]
    if len(pas) > 1:
        d.line(pas, fill=WATER, width=6, joint="curve")
    for i in range(0, len(fut) - 1, 2):
        d.line([fut[i], fut[i + 1]], fill=WATER, width=5)
    if pas:
        x, y = pas[-1]
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=WATER, outline="#fff", width=3)
    d.text((x0, y0 + h + 10), "últimos 14 días", font=f(20), fill=INK2)
    d.text((x0 + w, y0 + h + 10), "pronóstico", font=f(20), fill=INK2, anchor="ra")


def construir():
    B, N = cargar(SALIDA)
    estados_barrios(B, N)
    hoy = N["dias"].index(N["hoy"]) if N["hoy"] in N["dias"] else 30
    gen = generado_local(N)
    out = DIST / "og"
    (out / "puerto").mkdir(parents=True, exist_ok=True)
    (out / "rio").mkdir(parents=True, exist_ok=True)
    pie_txt = "Estimación propia con datos de Prefectura e INA. No reemplaza avisos oficiales."

    # portada
    im, d = lienzo()
    r2 = [b for b in B["barrios"] if b["S"][hoy] == 2]
    r1 = [b for b in B["barrios"] if b["S"][hoy] == 1]
    d.text((64, 110), "¿Llega el agua?", font=f(84, "ExtraBold"), fill=INK)
    d.text((64, 215), "Crecida del Paraná, el Paraguay y el Uruguay, barrio por barrio", font=f(32, "Medium"), fill=INK2)
    d.text((64, 300), f"{len(r2)} barrios", font=f(72, "ExtraBold"), fill=COL["evacuacion"])
    d.text((64, 385), f"con agua probable · {num(sum(b['fam'] or 0 for b in r2), 0)} familias", font=f(32), fill=INK)
    d.text((64, 440), f"{len(r1)} más a menos de 1 m · {num(sum(b['fam'] or 0 for b in r1), 0)} familias", font=f(32), fill=INK)
    d.text((64, 500), f"Datos del {fecha_txt(N['hoy'], True)}, cada 4 horas", font=f(26, "SemiBold"), fill=WATER)
    pie(d, pie_txt)
    im.save(out / "portada.png", optimize=True)

    for rio, nom_r in RIO_NOMBRE.items():
        ps = [p for p in N["puertos"] if p["rio"] == rio and p.get("activo", True) and any(v is not None for v in p["H"])]
        res = [(p, resumen_puerto(p, N, hoy)) for p in ps]
        im, d = lienzo()
        d.text((64, 110), f"Altura del río {nom_r} hoy", font=f(64, "ExtraBold"), fill=INK)
        top = sorted([(p, r) for p, r in res if r["h"] is not None and p.get("al")], key=lambda x: -(x[1]["h"] - x[0]["al"]))[:4]
        y = 220
        for p, r in top:
            forma(d, r["est"], 84, y + 26, 18)
            d.text((120, y), nombre_puerto(p), font=f(40, "SemiBold"), fill=INK)
            d.text((760, y), f"{num(r['h'])} m", font=f(40, "Bold"), fill=INK, anchor="ra")
            d.text((790, y + 4), ESTADO_TXT[r["est"]], font=f(32), fill=INK2)
            y += 74
        d.text((64, 520), f"{len(ps)} puertos · lecturas de Prefectura del {fecha_txt(N['hoy'])}", font=f(26, "SemiBold"), fill=WATER)
        pie(d, pie_txt)
        im.save(out / "rio" / f"{rio}.png", optimize=True)

    for p in N["puertos"]:
        if not any(v is not None for v in p["H"]) or not p.get("activo", True):
            continue
        r = resumen_puerto(p, N, hoy)
        im, d = lienzo()
        nom = nombre_puerto(p)
        d.text((64, 110), f"Río {RIO_NOMBRE[p['rio']]} en {nom}", font=f(54 if len(nom) < 18 else 44, "ExtraBold"), fill=INK)
        if r["h"] is not None:
            d.text((64, 200), f"{num(r['h'])} m", font=f(132, "ExtraBold"), fill=INK)
            forma(d, r["est"], 92, 400, 26)
            d.text((136, 378), ESTADO_TXT[r["est"]], font=f(44, "Bold"), fill=INK)
            d1 = r["d1"]
            if d1 is not None:
                d.text((64, 450), ("Estable en 24 h" if abs(d1) < .03 else f"{'Sube' if d1 > 0 else 'Baja'} {num(abs(d1))} m en 24 h"),
                       font=f(32), fill=INK2)
            d.text((64, 500), f"Prefectura Naval · {fecha_txt(r['fecha'], True)}", font=f(26, "SemiBold"), fill=WATER)
        elif r.get("estimado") is not None:
            d.text((64, 200), f"~{num(r['estimado'])} m", font=f(132, "ExtraBold"), fill=INK)
            d.text((64, 380), "Estimado con un modelo, no es una lectura", font=f(34), fill=INK2)
        else:
            d.text((64, 220), "Sin lecturas recientes", font=f(60, "Bold"), fill=INK2)
        spark(d, p["H"], hoy, 760, 230, 380, 200)
        pie(d, pie_txt)
        im.save(out / "puerto" / f"{slug_puerto(p)}.png", optimize=True)
    print("imágenes para compartir listas,", gen.strftime("%d/%m %H:%M"))


if __name__ == "__main__":
    construir()
