from flask import Flask, jsonify, send_from_directory, request
import csv
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unicodedata
import difflib

BASE = Path(__file__).resolve().parent
CSV_PATH = BASE.parent / "mi_radar_musical.csv"
DATOS_PATH = BASE.parent / "lanzamientos.json"

app = Flask(__name__, static_folder=str(BASE), static_url_path="")

@app.get("/")
def inicio():
    return send_from_directory(BASE, "portada.html")

@app.get("/artistas")
def pagina_artistas():
    return send_from_directory(BASE, "index.html")

@app.get("/api/artistas")
def artistas():
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    return jsonify(filas)

def normalizar_texto(valor):
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in valor).split())

@app.get("/api/muestra")
def muestra_musical():
    titulo = (request.args.get("titulo") or "").strip()
    artista = (request.args.get("artista") or "").strip()
    if not titulo or not artista:
        return jsonify({"error": "Falta el título o el artista."}), 400

    parametros = urlencode({
        "term": f"{artista} {titulo}",
        "country": "es",
        "media": "music",
        "entity": "song",
        "limit": 15
    })
    url = "https://itunes.apple.com/search?" + parametros
    try:
        peticion = Request(url, headers={"User-Agent": "MiRadarMusical/1.0"})
        with urlopen(peticion, timeout=8) as respuesta:
            resultados = json.loads(respuesta.read().decode("utf-8")).get("results", [])
    except Exception:
        return jsonify({"error": "No se ha podido consultar el catálogo musical ahora mismo."}), 502

    titulo_objetivo = normalizar_texto(titulo)
    artista_objetivo = normalizar_texto(artista)
    mejor = None
    mejor_puntuacion = 0.0
    for resultado in resultados:
        preview = resultado.get("previewUrl")
        titulo_resultado = normalizar_texto(resultado.get("trackName"))
        artista_resultado = normalizar_texto(resultado.get("artistName"))
        if not preview or not titulo_resultado or not artista_resultado:
            continue
        similitud_titulo = difflib.SequenceMatcher(None, titulo_objetivo, titulo_resultado).ratio()
        similitud_artista = difflib.SequenceMatcher(None, artista_objetivo, artista_resultado).ratio()
        puntuacion = similitud_titulo * 0.65 + similitud_artista * 0.35
        if titulo_objetivo in titulo_resultado or titulo_resultado in titulo_objetivo:
            puntuacion += 0.08
        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = resultado
            mejor_titulo = similitud_titulo
            mejor_artista = similitud_artista

    if not mejor or mejor_puntuacion < 0.76 or mejor_titulo < 0.72 or mejor_artista < 0.60:
        return jsonify({"error": "No he encontrado una muestra que coincida con suficiente seguridad."}), 404

    return jsonify({
        "previewUrl": mejor.get("previewUrl"),
        "trackViewUrl": mejor.get("trackViewUrl"),
        "titulo": mejor.get("trackName"),
        "artista": mejor.get("artistName"),
        "duracion": 30
    })


@app.get("/api/publicaciones/<nombre>")
def publicaciones(nombre):
    if not DATOS_PATH.exists():
        return jsonify({"error": "Todavía no hay publicaciones guardadas"}), 404

    datos = json.loads(DATOS_PATH.read_text(encoding="utf-8"))
    artista = next(
        (v for v in datos.values()
         if v.get("nombre_musicbrainz", "").casefold() == nombre.casefold()),
        None
    )

    if artista is None:
        return jsonify({"error": "Artista todavía no consultado"}), 404

    lista = list(artista.get("publicaciones", {}).values())
    lista.sort(key=lambda p: p.get("fecha", ""), reverse=True)

    return jsonify({
        "artista": artista.get("nombre_musicbrainz", nombre),
        "total": len(lista),
        "publicaciones": lista[:20]
    })

if __name__ == "__main__":
    print("Mi Radar Musical: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)

