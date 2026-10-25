import csv
import json
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CSV = BASE / "mi_radar_musical.csv"
DATOS = BASE / "lanzamientos.json"
ULTIMA_CONSULTA = 0

def consultar(url):
    global ULTIMA_CONSULTA

    for intento in range(5):
        espera = 1.1 - (time.time() - ULTIMA_CONSULTA)
        if espera > 0:
            time.sleep(espera)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "MiRadarMusical/0.1 (app local)"}
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as respuesta:
                resultado = json.load(respuesta)
            ULTIMA_CONSULTA = time.time()
            return resultado

        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or intento == 4:
                raise
            pausa = 5 * (2 ** intento)
            print(f"  Error HTTP {e.code}; reintento en {pausa} segundos...", flush=True)
            time.sleep(pausa)

        except urllib.error.URLError:
            if intento == 4:
                raise
            pausa = 5 * (2 ** intento)
            print(f"  Error de conexion; reintento en {pausa} segundos...", flush=True)
            time.sleep(pausa)

    raise RuntimeError("No se pudo completar la consulta tras varios intentos")


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


def publicaciones_apple(artista):
    """Completa con singles/álbumes recientes de Apple cuando MusicBrainz va retrasado."""
    nombre = artista.get("name", "").strip()
    if not nombre:
        return {}

    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode({
        "term": nombre,
        "country": "ES",
        "entity": "album",
        "limit": 200,
    })
    try:
        peticion = urllib.request.Request(
            url, headers={"User-Agent": "MiRadarMusical/1.0"}
        )
        with urllib.request.urlopen(peticion, timeout=12) as respuesta:
            resultados = json.loads(respuesta.read().decode("utf-8")).get("results", [])
    except Exception as error:
        print("  Aviso: no se pudo consultar el catálogo complementario:", error, flush=True)
        return {}

    def normalizar(texto):
        return " ".join(str(texto or "").casefold().split())

    encontrados = {}
    for resultado in resultados:
        artista_resultado = normalizar(resultado.get("artistName"))
        if artista_resultado != normalizar(nombre):
            continue

        titulo = str(resultado.get("collectionName") or "").strip()
        fecha = str(resultado.get("releaseDate") or "")[:10]
        identificador = resultado.get("collectionId")
        if not titulo or not identificador:
            continue

        # Solo añadimos resultados de este año: la fuente principal sigue siendo MusicBrainz.
        if not fecha.startswith(time.strftime("%Y")):
            continue

        tipo = "Single" if "single" in titulo.casefold() or resultado.get("trackCount") == 1 else "Album"
        clave = "apple-" + str(identificador)
        encontrados[clave] = {
            "titulo": titulo,
            "fecha": fecha,
            "tipo": tipo,
            "artista": nombre,
            "imagen": resultado.get("artworkUrl100", ""),
            "fuente": "Apple Music",
        }
    return encontrados


def main():
    if len(sys.argv) < 2:
        print('Uso: detector.py --artist "ABBA"')
        print("     detector.py --all")
        print("     detector.py --batch INICIO CANTIDAD")
        return

    modo = sys.argv[1]

    if modo == "--artist":
        if len(sys.argv) < 3:
            print('Indica el nombre: --artist "ABBA"')
            return
        nombres = [sys.argv[2]]

    elif modo in ("--all", "--batch"):
        with CSV.open(encoding="utf-8-sig", newline="") as f:
            filas = list(csv.DictReader(f))

        nombres = [
            r["NombreOriginal"] for r in filas
            if r["Estado"].strip() == "Vigilancia activa"
        ]

        if modo == "--batch":
            if len(sys.argv) < 4:
                print("Uso: detector.py --batch INICIO CANTIDAD")
                return
            try:
                inicio_lote = int(sys.argv[2])
                cantidad = int(sys.argv[3])
            except ValueError:
                print("El inicio y la cantidad deben ser numeros enteros.")
                return
            if inicio_lote < 0 or cantidad < 1:
                print("El inicio debe ser 0 o mayor y la cantidad al menos 1.")
                return
            nombres = nombres[inicio_lote:inicio_lote + cantidad]
            if not nombres:
                print("No hay artistas en esa tanda.")
                return
    else:
        print("Modo desconocido:", modo)
        return

    if DATOS.exists():
        datos = json.loads(DATOS.read_text(encoding="utf-8"))
    else:
        datos = {}

    total = len(nombres)

    for i, nombre in enumerate(nombres, 1):
        print(f"\\n[{i}/{total}] Consultando: {nombre}", flush=True)
        try:
            artista = buscar_artista(nombre)
            if not artista:
                continue

            actuales = publicaciones(artista)
            # Completar siempre con los lanzamientos del año en Apple Music,
            # porque MusicBrainz puede tardar en registrar algunos singles.
            complementarias = publicaciones_apple(artista)
            anadidas = 0
            for ident, pub in complementarias.items():
                clave_titulo = " ".join(pub["titulo"].casefold().split())
                duplicada = any(
                    " ".join(str(existente.get("titulo", "")).casefold().split()) == clave_titulo
                    and str(existente.get("fecha", ""))[:4] == str(pub.get("fecha", ""))[:4]
                    for existente in actuales.values()
                )
                if not duplicada:
                    actuales[ident] = pub
                    anadidas += 1
            if anadidas:
                print(f"  Apple Music añadió {anadidas} publicaciones recientes.", flush=True)
            clave = artista["id"]
            anteriores = datos.get(clave)

            if anteriores is None:
                print("Primera consulta: guardando linea de base.")
            else:
                previas = anteriores.get("publicaciones", {})
                nuevas = set(actuales) - set(previas)
                if nuevas:
                    print("NUEVAS PUBLICACIONES:")
                    for ident in sorted(nuevas):
                        pub = actuales[ident]
                        print(f"  {pub['fecha']} - {pub['titulo']} ({pub['tipo']})")
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

    print("\\nProceso terminado. Datos guardados en:", DATOS)


if __name__ == "__main__":
    main()
