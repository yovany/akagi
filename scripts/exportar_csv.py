#!/usr/bin/env python3
"""Exporta el videolog a videolog.csv para editarlo en Numbers.

Estatus (columna `estatus`):  v = vista · e = esperando · a = algún día · n = no lo sé
Orden de las filas: v, e, a, n; dentro de cada grupo, como están en data/videolog.yaml.
La hoja editada se vuelve a cargar con scripts/importar_csv.py.

Uso:  python3 scripts/exportar_csv.py
"""
import csv, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPOS = ["#", "estatus", "donde", "tipo", "titulo", "temp", "original", "plataforma", "estreno",
          "popularidad", "nota_tvmaze", "caps_vistos", "fecha_vista", "mi_nota", "tvmaze"]


def leer_yaml():
    """[(seccion, dict)] con cada línea `- {clave: valor, ...}` de data/videolog.yaml."""
    filas, seccion = [], None
    for linea in (ROOT / "data/videolog.yaml").read_text().splitlines():
        m = re.match(r"^(\w+):", linea)
        if m:
            seccion = m.group(1)
        m = re.match(r"^\s*-\s*\{(.*)\}\s*$", linea)
        if not m:
            continue
        d = {}
        for k, comillas, simple in re.findall(r'(\w+):\s*(?:"((?:[^"\\]|\\.)*)"|([^,}]+))', m.group(1)):
            d[k] = (comillas.replace('\\"', '"').replace("\\\\", "\\") if comillas else simple.strip())
        filas.append((seccion, d))
    return filas


def main():
    series = json.loads((ROOT / "data/series.json").read_text())
    estatus_de = {"vistas": "v", "esperando": "e", "algun_dia": "a", "no_se": "n"}
    orden = {k: i for i, k in enumerate(estatus_de)}
    filas = [f for f in leer_yaml() if f[0] in estatus_de]
    filas.sort(key=lambda x: orden[x[0]])          # estable: conserva el orden del yaml dentro de cada grupo
    salida = ROOT / "videolog.csv"
    with salida.open("w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig: Numbers/Excel leen bien los acentos
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        for n, (sec, d) in enumerate(filas, 1):
            es_serie = d["tipo"] == "serie"
            k = f"{d['t']} T{d['temp']}" if d.get("temp") else d["t"]
            s = series.get(k, {}) if es_serie else {}
            estatus = estatus_de[sec]
            donde = {"cine": "cine", "streaming": "stream"}.get(d.get("donde", ""), "")
            caps = "todos" if (es_serie and sec == "vistas") else ("al dia" if d.get("al_dia") else d.get("vistos", ""))
            w.writerow({
                "#": n, "estatus": estatus, "donde": donde, "tipo": "serie" if es_serie else "peli",
                "titulo": d["t"], "temp": d.get("temp", ""), "original": d.get("o", ""),
                "plataforma": d.get("via", ""), "estreno": d.get("estreno", ""),
                "popularidad": s.get("peso", ""), "nota_tvmaze": s.get("nota") or "",
                "caps_vistos": caps if es_serie else "", "fecha_vista": d.get("fecha", ""),
                "mi_nota": d.get("nota", ""), "tvmaze": d.get("tvmaze", ""),
            })
    print(f"{len(filas)} filas -> {salida}")


if __name__ == "__main__":
    main()
