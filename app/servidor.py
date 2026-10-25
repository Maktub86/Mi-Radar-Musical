import re
from flask import Flask, jsonify, send_from_directory, request
import csv
import json
import subprocess
import shutil
import threading
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unicodedata
import difflib
from listas_musicales import cargar as cargar_lista, actualizar as actualizar_lista

BASE = Path(__file__).resolve().parent
CSV_PATH = BASE.parent / "mi_radar_musical.csv"
DATOS_PATH = BASE.parent / "lanzamientos.json"
TAREA = "MiRadarMusical_Actualizacion"

app = Flask(__name__, static_folder=str(BASE), static_url_path="")

BOTON_HTML = '\n<style>\n#panel-actualizacion{position:fixed;top:12px;right:16px;z-index:9999;background:#202633;color:#fff;padding:12px;border-radius:12px;box-shadow:0 3px 18px #0008;width:275px;max-width:calc(100vw - 32px);font:13px Arial}\n#panel-actualizacion button{width:100%;padding:10px;border:0;border-radius:8px;background:#e8bd62;color:#171717;font-weight:bold;cursor:pointer}\n#panel-actualizacion button:disabled{opacity:.65;cursor:wait}\n#progreso-actualizacion{height:8px;background:#414858;border-radius:8px;margin-top:9px;overflow:hidden}\n#barra-actualizacion{height:100%;width:0;background:#76e0c2;transition:width .2s}\n#estado-actualizacion{display:block;margin-top:7px;line-height:1.4}\n@media(max-width:600px){#panel-actualizacion{top:8px;right:8px;width:220px}body{padding-top:90px}}\n</style>\n<div id="panel-actualizacion">\n<button id="boton-actualizar" type="button">↻ Actualizar artistas y radar</button>\n<div id="progreso-actualizacion"><div id="barra-actualizacion"></div></div>\n<span id="estado-actualizacion" role="status">Actualización manual</span>\n</div>\n<script>\n(()=>{\nconst b=document.getElementById(\'boton-actualizar\');\nconst e=document.getElementById(\'estado-actualizacion\');\nconst barra=document.getElementById(\'barra-actualizacion\');\nlet vigilando=false;\nasync function consultar(){\n const r=await fetch(\'/api/estado-actualizacion\');\n const d=await r.json();\n barra.style.width=(d.progreso||0)+\'%\';\n e.textContent=(d.progreso||0)+\'% · \'+d.mensaje;\n b.disabled=!!d.en_curso;\n return d;\n}\nasync function vigilar(){\n if(vigilando)return;\n vigilando=true;\n try{\n  let d;\n  do{\n   await new Promise(r=>setTimeout(r,1500));\n   d=await consultar();\n  }while(d.en_curso);\n }catch(err){\n  e.textContent=\'No se pudo consultar el progreso.\';\n  b.disabled=false;\n }finally{vigilando=false;}\n}\nb.addEventListener(\'click\',async()=>{\n if(!confirm(\'¿Actualizar todos los artistas activos y regenerar el radar?\'))return;\n b.disabled=true;barra.style.width=\'0%\';e.textContent=\'Iniciando actualización...\';\n try{\n  const r=await fetch(\'/api/actualizar\',{method:\'POST\'});\n  const d=await r.json();\n  if(!r.ok){e.textContent=d.error||\'No se pudo iniciar.\';b.disabled=false;return;}\n  e.textContent=d.mensaje||\'Actualización iniciada.\';\n  vigilar();\n }catch(err){\n  e.textContent=\'No se pudo contactar con el servidor.\';\n  b.disabled=false;\n }\n});\nconsultar().catch(()=>{});\n})();\n</script>\n'


@app.get("/")
def inicio():
    html = (BASE / "portada.html").read_text(encoding="utf-8")
    return html.replace("</body>", BOTON_HTML + "\n</body>")

@app.get("/artistas")
def pagina_artistas():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    return html.replace("</body>", BOTON_HTML + "\n</body>")

@app.get("/api/artistas")
def artistas():
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as archivo:
        return jsonify(list(csv.DictReader(archivo)))


def normalizar_texto(valor):
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return " ".join("".join(
        c.lower() if c.isalnum() else " " for c in valor
    ).split())


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

    try:
        peticion = Request(
            "https://itunes.apple.com/search?" + parametros,
            headers={"User-Agent": "MiRadarMusical/1.0"}
        )
        with urlopen(peticion, timeout=8) as respuesta:
            resultados = json.loads(
                respuesta.read().decode("utf-8")
            ).get("results", [])
    except Exception:
        return jsonify({
            "error": "No se ha podido consultar el catálogo musical ahora mismo."
        }), 502

    titulo_objetivo = normalizar_texto(titulo)
    artista_objetivo = normalizar_texto(artista)
    mejor = None
    mejor_puntuacion = 0.0
    mejor_titulo = 0.0
    mejor_artista = 0.0

    for resultado in resultados:
        preview = resultado.get("previewUrl")
        titulo_resultado = normalizar_texto(resultado.get("trackName"))
        artista_resultado = normalizar_texto(resultado.get("artistName"))

        if not preview or not titulo_resultado or not artista_resultado:
            continue

        similitud_titulo = difflib.SequenceMatcher(
            None, titulo_objetivo, titulo_resultado
        ).ratio()
        similitud_artista = difflib.SequenceMatcher(
            None, artista_objetivo, artista_resultado
        ).ratio()
        puntuacion = similitud_titulo * 0.65 + similitud_artista * 0.35

        if titulo_objetivo in titulo_resultado or titulo_resultado in titulo_objetivo:
            puntuacion += 0.08

        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = resultado
            mejor_titulo = similitud_titulo
            mejor_artista = similitud_artista

    if (
        not mejor or mejor_puntuacion < 0.76
        or mejor_titulo < 0.72 or mejor_artista < 0.60
    ):
        return jsonify({
            "error": "No he encontrado una muestra que coincida con suficiente seguridad."
        }), 404

    return jsonify({
        "previewUrl": mejor.get("previewUrl"),
        "trackViewUrl": mejor.get("trackViewUrl"),
        "titulo": mejor.get("trackName"),
        "artista": mejor.get("artistName"),
        "duracion": 30
    })


@app.get("/api/youtube/buscar")
def buscar_videos_youtube():
    """Busca candidatos en YouTube para que el usuario elija la versión correcta."""
    titulo = (request.args.get("titulo") or "").strip()
    artista = (request.args.get("artista") or "").strip()
    consulta = " ".join(x for x in (artista, titulo) if x).strip()
    if not consulta:
        return jsonify({"error": "Falta el título o el artista."}), 400

    url = "https://www.youtube.com/results?" + urlencode({"search_query": consulta})
    try:
        peticion = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.7"
        })
        with urlopen(peticion, timeout=12) as respuesta:
            pagina = respuesta.read().decode("utf-8", errors="replace")

        # YouTube incluye los resultados en ytInitialData. Extraemos el JSON
        # equilibrando llaves para no depender de un patrón que corte el objeto.
        marcador = "ytInitialData"
        pos = pagina.find(marcador)
        if pos < 0:
            raise ValueError("YouTube no ha devuelto los resultados esperados.")
        inicio = pagina.find("{", pos)
        if inicio < 0:
            raise ValueError("No se encontraron datos de búsqueda.")
        profundidad = 0
        dentro_cadena = False
        escape = False
        fin = None
        for i in range(inicio, len(pagina)):
            c = pagina[i]
            if dentro_cadena:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    dentro_cadena = False
                continue
            if c == '"':
                dentro_cadena = True
            elif c == "{":
                profundidad += 1
            elif c == "}":
                profundidad -= 1
                if profundidad == 0:
                    fin = i + 1
                    break
        if fin is None:
            raise ValueError("Los resultados de YouTube estaban incompletos.")
        datos = json.loads(pagina[inicio:fin])

        encontrados = []
        vistos = set()
        def recorrer(obj):
            if isinstance(obj, dict):
                video = obj.get("videoRenderer")
                if isinstance(video, dict):
                    video_id = video.get("videoId")
                    if video_id and video_id not in vistos:
                        titulo_video = video.get("title", {})
                        titulo_texto = titulo_video.get("simpleText")
                        if not titulo_texto:
                            titulo_texto = "".join(
                                tramo.get("text", "")
                                for tramo in titulo_video.get("runs", [])
                            )
                        canal = video.get("ownerText") or video.get("longBylineText") or {}
                        canal_texto = canal.get("simpleText")
                        if not canal_texto:
                            canal_texto = "".join(
                                tramo.get("text", "") for tramo in canal.get("runs", [])
                            )
                        if titulo_texto:
                            vistos.add(video_id)
                            encontrados.append({
                                "titulo": titulo_texto,
                                "canal": canal_texto or "Canal desconocido",
                                "url": "https://www.youtube.com/watch?v=" + video_id
                            })
                for valor in obj.values():
                    recorrer(valor)
            elif isinstance(obj, list):
                for valor in obj:
                    recorrer(valor)
        recorrer(datos)
        if not encontrados:
            return jsonify({"error": "YouTube no devolvió vídeos para esa búsqueda. Puedes probar otra vez más tarde."}), 502
        return jsonify({"consulta": consulta, "resultados": encontrados[:8]})
    except Exception:
        return jsonify({
            "error": "No he podido consultar los resultados de YouTube. Comprueba la conexión e inténtalo de nuevo."
        }), 502


@app.get("/api/publicaciones/<nombre>")
def publicaciones(nombre):
    if not DATOS_PATH.exists():
        return jsonify({"error": "Todavía no hay publicaciones guardadas"}), 404

    datos = json.loads(DATOS_PATH.read_text(encoding="utf-8"))
    artista = next(
        (
            v for v in datos.values()
            if v.get("nombre_musicbrainz", "").casefold() == nombre.casefold()
        ),
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


_candado_estado = threading.Lock()
_estado_actualizacion = {"en_curso": False, "mensaje": "Actualización manual", "progreso": 0}



def _ejecutar_actualizacion():
    log_path = BASE / "actualizacion_diaria.log"
    raiz = BASE.parent
    try:
        detector = BASE / "detector.py"
        preparar = BASE / "preparar_portada.py"
        origen = raiz / "portada.json"
        destino = BASE / "portada.json"

        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            log.write("\n==== Actualización conjunta manual ====\n")
            proceso = subprocess.Popen(
                [sys.executable, str(detector), "--all"],
                cwd=str(raiz), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            total = 0
            for linea in proceso.stdout:
                log.write(linea)
                log.flush()
                m = re.search(r"\[(\d+)/(\d+)\]\s+Consultando", linea)
                if m:
                    hecho, total = int(m.group(1)), int(m.group(2))
                    porcentaje = min(90, int(90 * hecho / max(total, 1)))
                    with _candado_estado:
                        _estado_actualizacion["progreso"] = porcentaje
                        _estado_actualizacion["mensaje"] = f"Consultando artistas: {hecho} de {total}"

            codigo = proceso.wait()
            if codigo:
                raise RuntimeError("El detector falló. Consulta actualizacion_diaria.log.")

            with _candado_estado:
                _estado_actualizacion["progreso"] = 92
                _estado_actualizacion["mensaje"] = "Preparando el radar..."

            resultado = subprocess.run(
                [sys.executable, str(preparar)], cwd=str(raiz),
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if resultado.returncode:
                raise RuntimeError("No se pudo preparar el radar. Consulta el registro.")

            shutil.copy2(origen, destino)

        with _candado_estado:
            _estado_actualizacion.update(
                en_curso=False, progreso=100,
                mensaje="Actualización conjunta completada."
            )
    except Exception as error:
        with _candado_estado:
            _estado_actualizacion.update(
                en_curso=False,
                mensaje="Actualización fallida: " + str(error)
            )


@app.get("/api/estado-actualizacion")
def estado_actualizacion():
    with _candado_estado:
        return jsonify(dict(_estado_actualizacion))



@app.post("/api/actualizar")
def actualizar_radar():
    with _candado_estado:
        if _estado_actualizacion["en_curso"]:
            return jsonify({"error": "Ya hay una actualización en curso."}), 409
        _estado_actualizacion.update(
            en_curso=True, progreso=0,
            mensaje="Iniciando actualización de artistas..."
        )
    try:
        threading.Thread(target=_ejecutar_actualizacion, daemon=True).start()
        return jsonify({"en_curso": True, "mensaje": "Actualización conjunta iniciada."}), 202
    except Exception:
        with _candado_estado:
            _estado_actualizacion.update(en_curso=False, mensaje="No se pudo iniciar.")
        return jsonify({"error": "No se pudo iniciar la actualización."}), 500



@app.get("/api/listas/<tipo>")
def api_lista_musical(tipo):
    if tipo not in ("los40", "canal-fiesta", "youtube"):
        return jsonify({"error": "Lista desconocida."}), 404
    return jsonify(cargar_lista(tipo))


@app.post("/api/listas/<tipo>/actualizar")
def api_actualizar_lista_musical(tipo):
    if tipo not in ("los40", "canal-fiesta", "youtube"):
        return jsonify({"error": "Lista desconocida."}), 404
    resultado = actualizar_lista(tipo)
    if resultado.get("en_curso"):
        return jsonify(resultado), 409
    if resultado.get("error"):
        return jsonify(resultado), 502
    return jsonify(resultado)


if __name__ == "__main__":
    print("Mi Radar Musical: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)