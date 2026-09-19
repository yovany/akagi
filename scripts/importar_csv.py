#!/usr/bin/env python3
"""Importa la hoja editada en Numbers y regenera data/videolog.yaml.

Estatus (columna `estatus`):  v = vistas · e = esperando · a = algún día · n = no lo sé
Columnas que se leen: estatus, donde, caps_vistos, fecha_vista, mi_nota, y las de referencia
(tipo, titulo, temp, original, plataforma, estreno, tvmaze) para reconstruir cada título.

Uso:  python3 scripts/importar_csv.py videolog_editado.csv
"""
import csv, io, re, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECCION = {"v": "vistas", "e": "esperando", "a": "algun_dia", "n": "no_se"}

ENCABEZADO = '''# Videolog — cuatro listas, una por estatus. Se genera desde la hoja de Numbers
# (scripts/importar_csv.py) y se puede editar a mano: para cambiar el estatus de un título,
# mueve su línea a otra lista.
#
#   vistas:    v  · ya la vi. Con  donde: cine | streaming.  En series, se dan por vistos todos
#                   los capítulos ya estrenados.
#   esperando: e  · la quiero ver pronto, o la voy siguiendo.  Series: vistos: N (capítulos vistos)
#                   o al_dia: true (vistos todos los que han salido).
#   algun_dia: a  · algún día.
#   no_se:     n  · no lo sé.
#
# Campos: t (título) · o (título original) · tipo: pelicula|serie · estreno · via (plataforma)
#         tvmaze (id) · temp (temporada) · fecha (día que la vi) · nota (mi calificación)
# Fechas de películas: estreno en cines de México. Series: fecha de la plataforma (global).
# Estrenos en miércoles pueden ser preestreno; el oficial suele ser el jueves.
'''


def fecha_iso(txt, campo, fila):
    """Acepta 2026-03-08, 8/3/26, 08/03/2026 (día/mes/año, como en México)."""
    txt = (txt or "").strip()
    if not txt:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt):
        return txt
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", txt)
    if m:
        d, mo, a = int(m[1]), int(m[2]), int(m[3])
        a += 2000 if a < 100 else 0
        try:
            return date(a, mo, d).isoformat()
        except ValueError:
            pass
    print(f"  ! fila {fila}: no entiendo la fecha de {campo}: {txt!r} (la omito)")
    return ""


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def linea(x, fila):
    tipo = "serie" if x["tipo"].strip().lower().startswith("s") else "pelicula"
    partes = [f"t: {q(x['titulo'])}"]
    if x["original"].strip():
        partes.append(f"o: {q(x['original'].strip())}")
    partes.append(f"tipo: {tipo}")
    est = fecha_iso(x["estreno"], "estreno", fila)
    if est:
        partes.append(f'estreno: "{est}"')
    if x["plataforma"].strip():
        partes.append(f"via: {q(x['plataforma'].strip())}")
    if x["tvmaze"].strip():
        partes.append(f"tvmaze: {int(float(x['tvmaze']))}")
    if x["temp"].strip():
        partes.append(f"temp: {int(float(x['temp']))}")
    estatus = x["estatus"].strip().lower()
    if estatus == "v":
        donde = {"cine": "cine", "stream": "streaming", "streaming": "streaming"}.get(x["donde"].strip().lower(), "")
        if donde:
            partes.append(f"donde: {donde}")
        else:
            print(f"  ! fila {fila}: {x['titulo']} está como vista pero sin cine/stream")
    caps = x["caps_vistos"].strip().lower().replace("í", "i")
    if tipo == "serie" and caps and caps != "todos":
        if caps in ("al dia", "aldia", "al_dia"):
            partes.append("al_dia: true")
        elif re.fullmatch(r"\d+", caps):
            partes.append(f"vistos: {int(caps)}")
        else:
            print(f"  ! fila {fila}: caps_vistos no entendido: {x['caps_vistos']!r} (lo omito)")
    fv = fecha_iso(x["fecha_vista"], "fecha_vista", fila)
    if fv:
        partes.append(f'fecha: "{fv}"')
    nota = x["mi_nota"].strip().replace(",", ".")
    if nota:
        partes.append(f"nota: {nota[:-2] if nota.endswith('.0') else nota}")
    return "  - {" + ", ".join(partes) + "}"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    ruta = Path(sys.argv[1]).expanduser()
    crudo = ruta.read_text(encoding="utf-8-sig")
    inicio = crudo.find("#,estatus")          # Numbers antepone una línea con el nombre de la tabla
    if inicio < 0:
        sys.exit("No encuentro la fila de encabezados (#,estatus,...).")
    filas = [x for x in csv.DictReader(io.StringIO(crudo[inicio:])) if any((v or "").strip() for v in x.values())]
    grupos = {k: [] for k in SECCION}
    for n, x in enumerate(filas, 2):
        e = x["estatus"].strip().lower()
        if e not in SECCION:
            print(f"  ! fila {n}: estatus {x['estatus']!r} no válido, pasa a 'n' ({x['titulo']})")
            e = "n"
        grupos[e].append(linea(x, n))
    out = [ENCABEZADO]
    for e, nombre in SECCION.items():
        out.append(f"{nombre}:" + ("" if grupos[e] else " []"))
        out.extend(grupos[e])
        out.append("")
    (ROOT / "data/videolog.yaml").write_text("\n".join(out))
    print("videolog.yaml regenerado: " + " · ".join(f"{SECCION[e]} {len(v)}" for e, v in grupos.items()) + f"  (total {len(filas)})")


if __name__ == "__main__":
    main()
