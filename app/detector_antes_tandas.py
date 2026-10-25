import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CSV = BASE / "mi_radar_musical.csv"
DATOS = BASE / "lanzamientos.json"
ULTIMA_CONSULTA = 0

def consultar(url):
    global ULTIMA_CONSULTA
    espera = 1.1 - (time.time() - ULTIMA_CONSULTA)
    if espera > 0:
        time.sleep(espera)
    req = urllib.request.Request(
        url, headers={"User-Agent": "MiRadarMusical/0.1 (app local)"}
    )
    with urllib.request.urlopen(req, timeout=30) as respuesta:
        resultado = json.load(respuesta)
    ULTIMA_CONSULTA = time.time()
    return resultado

def buscar_artista(nombre):
    url = "https://musicbrainz.org/ws/2/artist/?" + urllib.parse.urlencode({
        "query": "artist:" + nombre, "fmt": "json", "limit": 10
    })
    resultados = consultar(url).get("artists", [])
    coincidencias = [
        a for a in resultados
        if a["name"].casefold() == nombre.casefold()
    ]
    if not coincidencias:
        print("No hay coincidencia exacta en MusicBrainz:", nombre)
        return None
    return coincidencias[0]

def publicaciones(artista):
    todas = []
    offset = 0

    while True:
        url = "https://musicbrainz.org/ws/2/release-group/?" + urllib.parse.urlencode({
            "artist": artista["id"],
            "fmt": "json",
            "limit": 100,
            "offset": offset
        })
        respuesta = consultar(url)
        grupos = respuesta.get("release-groups", [])

        if not grupos:
            break

        todas.extend(grupos)
        print(f"  Publicaciones recopiladas: {len(todas)}", flush=True)

        if len(grupos) < 100:
            break

        offset += len(grupos)

    return {
        g["id"]: {
            "titulo": g["title"],
            "fecha": g.get("first-release-date", ""),
            "tipo": g.get("primary-type", ""),
            "artista": artista["name"]
        }
        for g in todas
    }


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("--artist", "--all"):
        print('Uso: detector.py --artist "ABBA"')
        print("O para la lista activa: detector.py --all")
        return

    with CSV.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))

    if sys.argv[1] == "--artist":
        nombres = [sys.argv[2]]
    else:
        nombres = [
            r["NombreOriginal"] for r in filas
            if r["Estado"] == "Vigilancia activa"
        ]

    if DATOS.exists():
        datos = json.loads(DATOS.read_text(encoding="utf-8"))
    else:
        datos = {}

    for i, nombre in enumerate(nombres, 1):
        print(f"\n[{i}/{len(nombres)}] Consultando: {nombre}", flush=True)
        try:
            artista = buscar_artista(nombre)
            if not artista:
                continue

            actuales = publicaciones(artista)
            clave = artista["id"]
            anteriores = datos.get(clave)

            if anteriores is None:
                print("Primera consulta: guardando línea de base.")
            else:
                nuevas = set(actuales) - set(anteriores["publicaciones"])
                if nuevas:
                    print("NUEVAS PUBLICACIONES:")
                    for ident in nuevas:
                        p = actuales[ident]
                        print(f"  {p['fecha']} — {p['titulo']} ({p['tipo']})")
                else:
                    print("No se detectan publicaciones nuevas.")

            datos[clave] = {
                "nombre_consultado": nombre,
                "nombre_musicbrainz": artista["name"],
                "ultima_consulta": time.strftime("%Y-%m-%d %H:%M:%S"),
                "publicaciones": actuales
            }
            DATOS.write_text(
                json.dumps(datos, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print("Publicaciones registradas:", len(actuales))
        except Exception as e:
            print("Error con", nombre, ":", e)

    print("\nProceso terminado. Datos guardados en:", DATOS)

if __name__ == "__main__":
    main()
