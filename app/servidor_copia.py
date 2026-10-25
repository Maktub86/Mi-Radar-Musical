from flask import Flask, jsonify, send_from_directory
import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent
CSV_PATH = BASE.parent / "mi_radar_musical.csv"

app = Flask(__name__, static_folder=str(BASE), static_url_path="")

@app.get("/")
def inicio():
    return send_from_directory(BASE, "index.html")

@app.get("/api/artistas")
def artistas():
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    return jsonify(filas)

if __name__ == "__main__":
    print("Mi Radar Musical: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
