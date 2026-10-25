from flask import Flask, jsonify, send_from_directory
import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
CSV_PATH = BASE.parent / "mi_radar_musical.csv"
DATOS_PATH = BASE.parent / "lanzamientos.json"

app = Flask(__name__, static_folder=str(BASE), static_url_path="")

@app.get("/")
def inicio():
    return send_from_directory(BASE, "index.html")

@app.get("/api/artistas")
def artistas():
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    return jsonify(filas)

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
