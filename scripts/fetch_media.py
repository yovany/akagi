#!/usr/bin/env python3
"""Baja carátulas y capítulos para el videolog.

Lee los títulos de data/videolog.yaml y escribe:
  data/series.json     -> carátula + capítulos con fecha (TVmaze, sin API key)
  data/peliculas.json  -> cartel (Wikipedia, sin API key)

Campos opcionales por título en videolog.yaml: `tvmaze: <id>` (evita la búsqueda) y
`temp: N` (solo los capítulos de esa temporada; para temporadas nuevas de series ya existentes).

Uso:  python3 scripts/fetch_media.py            # solo lo que falta
      python3 scripts/fetch_media.py --all      # vuelve a bajar todo
Solo usa la librería estándar.
"""
import json, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "videolog-personal/0.1"
PAUSA = 0.4  # cortesía con las APIs


def get(url, intentos=5):
    """GET JSON con pausa entre llamadas (más larga en Wikipedia) y espera si dan 429."""
    pausa = 1.0 if "wikipedia.org" in url else PAUSA
    for intento in range(intentos):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                time.sleep(pausa)
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                time.sleep(pausa)
                return None
            if e.code == 429 and intento < intentos - 1:
                time.sleep(int(e.headers.get("Retry-After", 5)) + 2 * intento)
                continue
            raise


def leer_items():
    """Cada línea `- {t: "...", o: "...", tipo: ...}` de videolog.yaml (sin PyYAML)."""
    items = []
    for linea in (ROOT / "data/videolog.yaml").read_text().splitlines():
        m = re.match(r"^\s*-\s*\{(.*)\}\s*$", linea)
        if not m:
            continue
        d = {}
        for k, comillas, simple in re.findall(r'(\w+):\s*(?:"((?:[^"\\]|\\.)*)"|([^,}]+))', m.group(1)):
            d[k] = (comillas or simple).strip()
        if "t" in d and "tipo" in d:
            items.append(d)
    return items


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def dias(a, b):
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


# ---------- series (TVmaze) ----------
def clave(item):
    """Llave en series.json: el título, más " T3" si el registro es de una temporada concreta."""
    return f"{item['t']} T{item['temp']}" if item.get("temp") else item["t"]


def detalle_serie(s, temp=None):
    eps = get(f"https://api.tvmaze.com/shows/{s['id']}/episodes") or []
    return {
        "id": s["id"],
        "nombre": s["name"],
        "poster": (s.get("image") or {}).get("medium"),
        "estado": s.get("status"),
        "eps": [
            {"s": e["season"], "n": e["number"], "t": e["name"], "d": e["airdate"]}
            for e in eps
            if e.get("airdate") and e.get("number") is not None and (not temp or e["season"] == int(temp))
        ],
    }


def buscar_serie(item):
    # Con `tvmaze: <id>` en el yaml no hay búsqueda ni adivinanzas.
    if item.get("tvmaze"):
        s = get(f"https://api.tvmaze.com/shows/{item['tvmaze']}")
        return detalle_serie(s, item.get("temp")) if s else None
    estreno = item.get("estreno")
    mejor = None
    for q in {item["t"], item["t"].split(":")[0]}:
        for r in get("https://api.tvmaze.com/search/shows?q=" + urllib.parse.quote(q)) or []:
            s = r["show"]
            if not s.get("premiered") or not estreno or dias(s["premiered"], estreno) > 45:
                continue
            sim = max(SequenceMatcher(None, norm(s["name"]), norm(x)).ratio() for x in (item["t"], q))
            if sim < 0.4:
                continue
            k = (sim, -dias(s["premiered"], estreno))
            if not mejor or k > mejor[0]:
                mejor = (k, s)
    return detalle_serie(mejor[1], item.get("temp")) if mejor else None


# ---------- películas (Wikipedia) ----------
def miniatura(url, ancho=250):
    """.../wikipedia/en/6/6c/X.jpg -> .../wikipedia/en/thumb/6/6c/X.jpg/250px-X.jpg"""
    url = url.split("?")[0]
    m = re.match(r"(https://upload\.wikimedia\.org/wikipedia/\w+)/(\w/\w\w)/(.+)$", url)
    return f"{m.group(1)}/thumb/{m.group(2)}/{m.group(3)}/{ancho}px-{m.group(3)}" if m else url


def resumen(titulo):
    d = get("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(titulo.replace(" ", "_"), safe="(),!:'&"))
    if not d or d.get("type") == "disambiguation":
        return None
    desc = d.get("description") or ""
    # Si el título ya dice "(2026 film)" basta con que sea una película; si no, exigimos año 2025/26.
    con_anio = re.search(r"\(202[56] film\)", titulo)
    if "film" not in desc.lower() or not (con_anio or re.search(r"202[56]", desc)):
        return None
    th = (d.get("thumbnail") or {}).get("source")
    return {"poster": miniatura(th), "wiki": d["title"]} if th else None


def buscar_pelicula(item):
    base = re.sub(r"\s*\(.*?\)", "", item.get("o") or item["t"]).strip()
    for cand in (f"{base} (2026 film)", f"{base} (2025 film)", f"{base} (film)", base):
        r = resumen(cand)
        if r:
            return r
    q = urllib.parse.quote(f'"{base}" film 2026')
    d = get(f"https://en.wikipedia.org/w/api.php?action=query&list=search&srlimit=3&format=json&srsearch={q}")
    for h in (d or {}).get("query", {}).get("search", []):
        r = resumen(h["title"])
        if r:
            return r
    return None


def main():
    todo = "--all" in sys.argv
    items = leer_items()
    series_p, pelis_p = ROOT / "data/series.json", ROOT / "data/peliculas.json"
    series = {} if todo or not series_p.exists() else json.loads(series_p.read_text())
    pelis = {} if todo or not pelis_p.exists() else json.loads(pelis_p.read_text())
    faltan = []
    for it in items:
        destino, buscar = (series, buscar_serie) if it["tipo"] == "serie" else (pelis, buscar_pelicula)
        k = clave(it) if it["tipo"] == "serie" else it["t"]
        if k in destino:
            continue
        try:
            r = buscar(it)
        except Exception as e:  # una falla de red no debe tirar todo
            print(f"  ! {it['t']}: {e}")
            r = None
        if r:
            destino[k] = r
            print(f"  ok  {k}")
        else:
            faltan.append(k)
            print(f"  --  {k}  (sin resultado)")
    series_p.write_text(json.dumps(series, ensure_ascii=False, indent=1))
    pelis_p.write_text(json.dumps(pelis, ensure_ascii=False, indent=1))
    print(f"\nseries: {len(series)}  películas: {len(pelis)}  sin resultado: {len(faltan)}")
    for t in faltan:
        print("   -", t)


if __name__ == "__main__":
    main()
