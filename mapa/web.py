"""Cálculos compartidos por la página interactiva y las páginas prerenderizadas (SEO).

Mismo criterio que el JavaScript de la portada:
  - subida del río en cada escala = altura del día − altura de febrero de 2000 (ancla SRTM);
  - un barrio tiene agua probable si la subida supera su parte baja (p25 del terreno);
  - "cerca del agua" si le falta menos de 1 m;
  - una escala sólo se muestra en evacuación con valor medido: un pronóstico llega como máximo a alerta.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timezone, timedelta

BASE = "https://gaetanof.github.io/monitor-rios-mapa"   # único lugar a cambiar cuando haya dominio propio
RIO_NOMBRE = {"parana": "Paraná", "uruguay": "Uruguay", "paraguay": "Paraguay"}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_C = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
# nombres de escala que chocan con otra cosa o vienen con agregados
SLUG_PUERTO = {29: "parana-entre-rios", 33: "san-lorenzo", 77: "salto-grande-arriba", 78: "salto-grande-abajo",
               57: "formosa", 84: "boca-del-gualeguaychu"}
MINUS = {"de", "del", "la", "las", "los", "el", "y", "e"}


def slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def titulo(s: str | None) -> str:
    """'Concepción Del Uruguay' -> 'Concepción del Uruguay' (preposiciones en minúscula salvo al inicio)."""
    if not s:
        return ""
    p = s.split()
    return " ".join(w if i == 0 or w.lower() not in MINUS else w.lower() for i, w in enumerate(p))


def nombre_puerto(p: dict) -> str:
    return re.sub(r"\s*\(.*\)", "", p["n"]).strip()


def slug_puerto(p: dict) -> str:
    return SLUG_PUERTO.get(p["id"], slug(nombre_puerto(p)))


def num(x, d=2) -> str:
    if x is None:
        return "sin dato"
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fecha_txt(iso: str, largo=False) -> str:
    d = date.fromisoformat(iso[:10])
    base = f"{d.day:02d}/{d.month:02d}"
    return f"{DIAS[d.weekday()]} {base}" if largo else base


def estado_puerto(p: dict, t: int) -> str:
    """normal | atencion | alerta | evacuacion | sin_umbral | sin_dato (el rojo sólo con dato medido)."""
    h = p["H"][t]
    if h is None:
        return "sin_dato"
    medido = p["src"][t] == "m"
    if p.get("ev") is not None and h >= p["ev"]:
        return "evacuacion" if medido else "alerta"
    if p.get("al") is not None and h >= p["al"]:
        return "alerta"
    if p.get("al") is not None and h >= p["al"] - 0.3:
        return "atencion"
    return "normal" if p.get("al") is not None else "sin_umbral"


ESTADO_TXT = {"normal": "Normal", "atencion": "Atención", "alerta": "Alerta", "evacuacion": "Evacuación",
              "sin_umbral": "Sin umbral oficial", "sin_dato": "Sin dato"}


def ultimo_medido(p: dict, hoy: int) -> int | None:
    for t in range(hoy, -1, -1):
        if p["H"][t] is not None and p["src"][t] == "m":
            return t
    return None


def variacion(p: dict, t: int, dias: int) -> float | None:
    if t - dias < 0 or p["H"][t] is None or p["H"][t - dias] is None:
        return None
    return round(p["H"][t] - p["H"][t - dias], 2)


def estados_barrios(B: dict, N: dict) -> None:
    """Agrega a cada barrio: R (subida por día), S (estado por día: 2, 1, 0, -1), motivo y nombres prolijos."""
    P = {p["id"]: p for p in N["puertos"]}
    T = len(N["dias"])
    for b in B["barrios"]:
        b["loc"] = titulo(b.get("loc") or b.get("dep"))
        b["prov"] = titulo(b.get("prov"))
        b["n"] = b["n"] if b.get("n") and b["n"].lower() != "sin nombre" else f"Barrio sin nombre ({b['id']})"
        b["h25"], b["h50"] = b["h"][1], b["h"][2]
        b["R"], b["S"] = [None] * T, [-1] * T
        b["motivo"] = B["zonas"].get(b["z"]) if b.get("z") else None
        if not b["motivo"] and b.get("esc"):
            pa = P.get(b["esc"][0])
            if pa and pa.get("med") is not None and pa.get("ancla") is not None and b["h25"] < (pa["med"] - pa["ancla"]) - 1:
                b["motivo"] = ("Según el modelo estaría bajo el agua en un día normal: puede tener una defensa, "
                               "un terraplén o un error del modelo de elevación.")
        if b["motivo"] or not b.get("esc"):
            continue
        a, c, w = b["esc"]
        pa, pc = P.get(a), P.get(c)
        for t in range(T):
            ra = _sub(pa, t)
            rc = _sub(pc, t)
            if ra is not None and rc is not None:
                r = w * ra + (1 - w) * rc
            else:
                r = ra if ra is not None else rc
            if r is None:
                continue
            b["R"][t] = r
            m = r - b["h25"]
            b["S"][t] = 2 if m >= 0 else 1 if m > -1 else 0


def _sub(p, t):
    if not p or p.get("ancla") is None or p["H"][t] is None:
        return None
    return p["H"][t] - p["ancla"]


def generado_local(N: dict) -> datetime:
    g = datetime.fromisoformat(N["generado"])
    if g.tzinfo is None:
        g = g.replace(tzinfo=timezone.utc)
    return g.astimezone(timezone(timedelta(hours=-3)))


def cargar(salida) -> tuple[dict, dict]:
    B = json.loads((salida / "barrios.json").read_text(encoding="utf-8"))
    N = json.loads((salida / "niveles.json").read_text(encoding="utf-8"))
    return B, N
