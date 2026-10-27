import json
import re
from pathlib import Path
from datetime import date, datetime
from zoneinfo import ZoneInfo

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

        # MusicBrainz puede aportar fechas completas, año-mes o solo año.
        # Si la fecha conocida cae en el futuro, no se publica como novedad disponible.
        coincidencia = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", fecha)
        fecha_orden = ""
        fecha_valida = True
        if coincidencia:
            anio_txt, mes_txt, dia_txt = coincidencia.groups()
            try:
                anio = int(anio_txt)
                mes = int(mes_txt or 0)
                dia = int(dia_txt or 0)
                fecha_base = date(anio, mes or 1, dia or 1)
                hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
                if fecha_base > hoy:
                    fecha_valida = False
                else:
                    fecha_orden = f"{anio:04d}-{mes:02d}-{dia:02d}"
            except ValueError:
                fecha_valida = False
        elif fecha:
            fecha_valida = False
        if not fecha_valida:
            continue

        publicaciones.append({
            "id": id_publicacion,
            "imagen": pub.get("imagen") or (f"https://coverartarchive.org/release-group/{id_publicacion}/front-250" if not str(id_publicacion).startswith("apple-") else ""),
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