"""Actualiza «Mi música» a partir del listado de MP3 que genera PowerShell.

Uso (desde la carpeta del proyecto):
    python app/actualizar_mi_musica.py                 -> usa lista_mp3.txt de la carpeta del proyecto
    python app/actualizar_mi_musica.py ruta\\lista.txt  -> usa otro archivo
    python app/actualizar_mi_musica.py --simular       -> solo enseña lo que cambiaría

Cada línea del listado tiene este formato:
    1982 | Michael Jackson - Thriller.mp3
    2024 | Lady Gaga - Die With A Smile (feat. Bruno Mars).mp3

Qué hace:
  1. Reescribe app/mi_musica.json con todas las canciones del listado.
     - El género de las canciones que ya estaban se conserva.
     - A las nuevas se les pone el género más habitual de ese artista en tu colección.
  2. Añade a mi_radar_musical.csv los artistas nuevos (para que el radar los vigile).
  3. Regenera artistas_unicos.txt.
"""
from __future__ import annotations

import collections
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

APP = Path(__file__).resolve().parent
RAIZ = APP.parent
JSON_MUSICA = APP / "mi_musica.json"
CSV_RADAR = RAIZ / "mi_radar_musical.csv"
ARTISTAS_UNICOS = RAIZ / "artistas_unicos.txt"
LISTA_POR_DEFECTO = RAIZ / "lista_mp3.txt"

# Windows no deja usar ciertos caracteres en los nombres de archivo: aquí se recuperan.
REEMPLAZOS_ARTISTA = {
    "AC_DC": "AC/DC",
}

GENERO_POR_DEFECTO = "Pop"
LINEA = re.compile(r"^\s*(\d{4})\s*\|\s*(.+?)\s+-\s+(.+?)\s*\.mp3\s*$", re.IGNORECASE)
FEAT = re.compile(r"\((?:feat\.?|ft\.?)\s*([^)]*)\)", re.IGNORECASE)


def normalizar(valor) -> str:
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in valor).split())


def titulo_base(titulo: str) -> str:
    """Título sin lo que va entre paréntesis (feat., directo, acústico...)."""
    return normalizar(re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", " ", titulo))


def leer_texto(ruta: Path) -> str:
    datos = ruta.read_bytes()
    # PowerShell 5 guarda en UTF-16 si no se indica otra codificación.
    if datos.startswith((b"\xff\xfe", b"\xfe\xff")):
        return datos.decode("utf-16")
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos.decode("cp1252")


def leer_lista(ruta: Path):
    canciones, descartadas = [], []
    vistas = set()
    for numero, linea in enumerate(leer_texto(ruta).splitlines(), 1):
        if not linea.strip():
            continue
        m = LINEA.match(linea)
        if not m:
            descartadas.append((numero, linea.strip()))
            continue
        anio, artista, titulo = int(m[1]), m[2].strip(), m[3].strip()
        artista = REEMPLAZOS_ARTISTA.get(artista, artista)
        clave = (anio, normalizar(artista), normalizar(titulo))
        if clave in vistas:
            continue
        vistas.add(clave)
        canciones.append({"artista": artista, "titulo": titulo, "anio": anio})
    return canciones, descartadas


def artista_principal(artista: str) -> str:
    return str(artista or "").split(",")[0].strip()


def cargar_generos_anteriores():
    """Géneros de la versión anterior de mi_musica.json, para no perderlos."""
    por_cancion, por_cancion_sin_anio, por_anio_titulo = {}, {}, {}
    por_artista = collections.defaultdict(collections.Counter)
    try:
        anteriores = json.loads(JSON_MUSICA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        anteriores = []
    for pista in anteriores if isinstance(anteriores, list) else []:
        genero = str(pista.get("genero") or "").strip()
        if not genero:
            continue
        titulo = titulo_base(pista.get("titulo"))
        # «Earth, Wind & Fire» lleva coma en el nombre: se guarda el nombre completo y el principal.
        nombres = {normalizar(pista.get("artista")), normalizar(artista_principal(pista.get("artista")))}
        for artista in nombres:
            por_cancion[(pista.get("anio"), artista, titulo)] = genero
            por_cancion_sin_anio.setdefault((artista, titulo), genero)
        por_artista[normalizar(pista.get("artista"))][genero] += 1
        por_anio_titulo.setdefault((pista.get("anio"), titulo), set()).add(genero)
    return por_cancion, por_cancion_sin_anio, por_artista, por_anio_titulo


def asignar_generos(canciones):
    por_cancion, sin_anio, por_artista, por_anio_titulo = cargar_generos_anteriores()
    sin_genero = []
    for c in canciones:
        artista = normalizar(c["artista"])
        titulo = titulo_base(c["titulo"])
        genero = por_cancion.get((c["anio"], artista, titulo)) or sin_anio.get((artista, titulo))
        if not genero and len(por_anio_titulo.get((c["anio"], titulo), ())) == 1:
            genero = next(iter(por_anio_titulo[(c["anio"], titulo)]))
        if not genero and por_artista.get(artista):
            genero = por_artista[artista].most_common(1)[0][0]
        if not genero and c["artista"].lower().startswith("cast "):
            genero = "Musical / BSO"
        if not genero:
            genero = GENERO_POR_DEFECTO
            sin_genero.append(c)
        c["genero"] = genero
    return sin_genero


def estado_para(artista: str):
    if "(ia)" in artista.lower():
        return "Pendiente de revisión", "Contiene etiqueta IA"
    if artista.lower().startswith("cast ") or artista.lower() == "varios artistas":
        return "Reparto o grupo pendiente", ""
    return "Vigilancia activa", ""


def actualizar_csv(artistas, simular):
    filas = []
    if CSV_RADAR.exists():
        with CSV_RADAR.open(encoding="utf-8-sig", newline="") as f:
            filas = list(csv.DictReader(f))
    conocidos = {normalizar(f.get("NombreOriginal")) for f in filas}
    conocidos |= {normalizar(f.get("NombreNormalizado")) for f in filas}
    nuevos = [a for a in artistas if normalizar(a) not in conocidos]
    if nuevos and not simular:
        for artista in nuevos:
            estado, observaciones = estado_para(artista)
            filas.append({"NombreOriginal": artista, "NombreNormalizado": artista,
                          "Estado": estado, "Observaciones": observaciones})
        with CSV_RADAR.open("w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(
                f, fieldnames=["NombreOriginal", "NombreNormalizado", "Estado", "Observaciones"],
                quoting=csv.QUOTE_ALL, lineterminator="\n")
            escritor.writeheader()
            escritor.writerows(filas)
    return nuevos


def main(argumentos):
    simular = "--simular" in argumentos
    rutas = [a for a in argumentos if not a.startswith("--")]
    lista = Path(rutas[0]) if rutas else LISTA_POR_DEFECTO
    if not lista.exists():
        raise SystemExit(f"No encuentro el listado: {lista}")

    canciones, descartadas = leer_lista(lista)
    if not canciones:
        raise SystemExit("El listado no contiene ninguna canción con el formato «AÑO | Artista - Título.mp3».")

    try:
        antes = json.loads(JSON_MUSICA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        antes = []
    claves_antes = {(p.get("anio"), normalizar(artista_principal(p.get("artista"))), titulo_base(p.get("titulo")))
                    for p in antes if isinstance(p, dict)}

    sin_genero = asignar_generos(canciones)
    canciones.sort(key=lambda c: (c["anio"], c["artista"].casefold(), c["titulo"].casefold()))
    nuevas = [c for c in canciones
              if (c["anio"], normalizar(c["artista"]), titulo_base(c["titulo"])) not in claves_antes]

    artistas = sorted({c["artista"] for c in canciones}, key=str.casefold)
    artistas_nuevos = actualizar_csv(artistas, simular)

    if not simular:
        JSON_MUSICA.write_text(
            json.dumps([{k: c[k] for k in ("artista", "titulo", "anio", "genero")} for c in canciones],
                       ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        ARTISTAS_UNICOS.write_text("\n".join(artistas) + "\n", encoding="utf-8-sig")

    print(("SIMULACIÓN (no se ha guardado nada)\n" if simular else "") +
          f"Canciones en el listado: {len(canciones)} (antes había {len(antes)})")
    print(f"Canciones nuevas o renombradas: {len(nuevas)}")
    print(f"Artistas distintos: {len(artistas)} · nuevos en el radar: {len(artistas_nuevos)}")
    for a in artistas_nuevos:
        print(f"  + {a}")
    if sin_genero:
        print(f"Canciones con género «{GENERO_POR_DEFECTO}» por defecto (revísalas): {len(sin_genero)}")
        for c in sin_genero:
            print(f"  ? {c['anio']} | {c['artista']} - {c['titulo']}")
    if descartadas:
        print(f"Líneas que no tienen el formato esperado: {len(descartadas)}")
        for numero, linea in descartadas:
            print(f"  ! línea {numero}: {linea}")


if __name__ == "__main__":
    main(sys.argv[1:])
