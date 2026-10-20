"""Arma la página del mapa.

    python -m mapa.armar web        # mapa/dist/: index.html + data/*.json (para publicar en la web)
    python -m mapa.armar unico      # mapa/dist/unico.html con los datos adentro (vista previa)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .comun import RAIZ, SALIDA

DIST = RAIZ / "dist"
CSS_ML = RAIZ / "site" / "maplibre-gl.css"


def _base() -> str:
    h = (RAIZ / "site" / "plantilla.html").read_text(encoding="utf-8")
    return h.replace("/*MAPLIBRE_CSS*/", CSS_ML.read_text(encoding="utf-8"))


def _min(nombre: str) -> str:
    d = json.loads((SALIDA / nombre).read_text(encoding="utf-8")) if nombre != "base.json" else json.loads((RAIZ / "base.json").read_text())
    return json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def web() -> Path:
    DIST.mkdir(exist_ok=True)
    (DIST / "data").mkdir(exist_ok=True)
    head = '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    html = _base().replace("<!--DATA-->", "")
    (DIST / "index.html").write_text(head + html.replace("<style>", "<style>[hidden]{display:none!important}", 1) + "</html>", encoding="utf-8")
    for n in ("barrios.json", "niveles.json"):
        shutil.copy(SALIDA / n, DIST / "data" / n)
    shutil.copy(RAIZ / "base.json", DIST / "data" / "base.json")
    return DIST / "index.html"


def unico() -> Path:
    DIST.mkdir(exist_ok=True)
    datos = "".join(f'<script type="application/json" id="d-{n}">{_min(n + ".json")}</script>' for n in ("barrios", "niveles", "base"))
    p = DIST / "unico.html"
    p.write_text(_base().replace("<!--DATA-->", datos), encoding="utf-8")
    print(p, f"{p.stat().st_size / 1024:.0f} KB")
    return p


if __name__ == "__main__":
    (unico if "unico" in sys.argv else web)()
