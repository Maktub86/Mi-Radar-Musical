import json
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
DATOS = BASE / "lanzamientos.json"
SALIDA = BASE / "portada.json"

if not DATOS.exists():
    raise FileNotFoundError(f"No encuentro {DATOS}")

datos = json.loads(DATOS.read_text(encoding="utf-8"))
publicaciones = []

for artista in datos.values():
    nombre = artista.get("nombre_musicbrainz") or artista.get("nombre_consultado", "Artista desconocido")

    for id_publicacion, pub in artista.get("publicaciones", {}).items():
        fecha = str(pub.get("fecha") or "").strip()

        try:
            fecha_orden = date.fromisoformat(fecha[:10]).isoformat()
        except ValueError:
            fecha_orden = ""

        publicaciones.append({
            "id": id_publicacion,
            "imagen": f"https://coverartarchive.org/release-group/{id_publicacion}/front-250",
            "titulo": pub.get("titulo") or "Sin título",
            "fecha": fecha,
            "artista": pub.get("artista") or nombre,
            "tipo": pub.get("tipo") or "Publicación",
            "_fecha_orden": fecha_orden,
        })

publicaciones.sort(
    key=lambda p: (bool(p["_fecha_orden"]), p["_fecha_orden"]),
    reverse=True
)

for pub in publicaciones:
    pub.pop("_fecha_orden", None)

SALIDA.write_text(
    json.dumps(publicaciones, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(f"Correcto: {len(publicaciones)} publicaciones preparadas.")
print(f"Archivo creado: {SALIDA}")