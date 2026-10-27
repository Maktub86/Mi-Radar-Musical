import re
import os
from flask import Flask, jsonify, send_from_directory, request
import csv
import json
import subprocess
import shutil
import threading
import sys
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.error import HTTPError
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


def _normalizar_nombre_musical(valor):
    valor = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", valor).strip()


def _buscar_fallback_musical(tipo, nombre, artista=""):
    """Busca un resumen existente en Last.fm; MusicBrainz no se trata como biografía."""
    clave = (os.environ.get("LASTFM_API_KEY") or "").strip()
    if not clave:
        return None
    cabeceras = {"User-Agent": "MiRadarMusical/1.0 (catalogo musical)"}
    try:
        params = {"method": "artist.getinfo" if tipo == "artista" else "track.getinfo",
                  "api_key": clave, "format": "json", "lang": "es", "autocorrect": "1"}
        if tipo == "artista":
            params["artist"] = nombre
        else:
            params.update({"track": nombre, "artist": artista})
        req = Request("https://ws.audioscrobbler.com/2.0/?" + urlencode(params), headers=cabeceras)
        with urlopen(req, timeout=8) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
        entidad = datos.get("artist") if tipo == "artista" else datos.get("track")
        wiki = (entidad or {}).get("bio" if tipo == "artista" else "wiki") or {}
        texto = re.sub(r"<[^>]+>", " ", str(wiki.get("content") or wiki.get("summary") or ""))
        texto = re.sub(r"\s+", " ", texto).strip()
        texto = re.sub(r"Read more on Last.fm.*$", "", texto, flags=re.I).strip()
        if len(texto) < 100:
            return None
        # Last.fm suele entregar un extracto corto; no lo presentamos como biografía
        # completa si no alcanza una extensión mínimamente útil.
        return {
            "encontrado": True,
            "resumen": texto[:2400],
            "biografia": texto[:2400] if tipo == "artista" else "",
            "informacion": texto[:2400] if tipo == "cancion" else "",
            "fuentes": [{"titulo": "Last.fm", "url": "https://www.last.fm/"}],
            "fuente_tipo": "lastfm",
            "fuente": "Last.fm"
        }
    except Exception as error:
        app.logger.info("Last.fm no disponible para %s: %s", nombre, error)
        return None


def _buscar_gemini_musical(tipo, nombre, artista=""):
    """Genera una ficha en español con Gemini y fuentes obtenidas mediante Google Search."""
    clave = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not clave:
        return None, "Falta configurar GEMINI_API_KEY en las variables de entorno del servicio."

    modelo = (os.environ.get("GEMINI_MODEL") or "gemini-3.8-flash").strip()
    entidad = f"la canción «{nombre}» de {artista}" if tipo == "cancion" else f"el artista «{nombre}»"
    if tipo == "artista":
        instrucciones = (
            "Redacta una biografía breve pero sustanciosa en español: orígenes, trayectoria, "
            "estilo musical y momentos relevantes. Termina con un apartado «Curiosidad documentada» "
            "solo si encuentras un dato concreto respaldado por las fuentes; si no, dilo claramente."
        )
    else:
        instrucciones = (
            "Explica en español el contexto de la canción, sus autores, publicación o álbum cuando "
            "pueda verificarse. Añade un apartado «Curiosidad documentada» con una anécdota sobre "
            "su creación, grabación, versiones o impacto únicamente si las fuentes la respaldan. "
            "No confundas una versión con la canción original."
        )
    prompt = (
        f"Investiga {entidad}. {instrucciones} "
        "Usa búsqueda web para contrastar la identidad y los datos. Prioriza fuentes oficiales, "
        "entrevistas y medios musicales fiables; puedes usar enciclopedias como apoyo. "
        "No inventes hechos, fechas, anécdotas ni fuentes. Si no hay una curiosidad verificable, "
        "escribe claramente que no has encontrado una curiosidad suficientemente documentada. "
        "Redacta entre 120 y 260 palabras, con los encabezados «Resumen» y "
        "«Curiosidad documentada». No incluyas enlaces inventados ni afirmes que algo está "
        "verificado si no aparece en las fuentes consultadas."
    )
    cuerpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700}
    }
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + quote(modelo, safe="") + ":generateContent"
    req = Request(
        url,
        data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": clave,
                 "User-Agent": "MiRadarMusical/1.0"},
        method="POST"
    )
    try:
        with urlopen(req, timeout=35) as resp:
            respuesta = json.loads(resp.read().decode("utf-8"))
        candidatos = respuesta.get("candidates") or []
        if not candidatos:
            return None, "Gemini no devolvió una respuesta utilizable."
        candidato = candidatos[0]
        partes = ((candidato.get("content") or {}).get("parts") or [])
        resumen = "\n".join(str(p.get("text") or "").strip() for p in partes if p.get("text")).strip()
        metadatos = candidato.get("groundingMetadata") or {}
        chunks = metadatos.get("groundingChunks") or []
        fuentes = []
        urls_vistas = set()
        for chunk in chunks:
            web = chunk.get("web") or {}
            enlace = str(web.get("uri") or "").strip()
            titulo = str(web.get("title") or "Fuente consultada").strip()
            if enlace.startswith("https://") and enlace not in urls_vistas:
                urls_vistas.add(enlace)
                fuentes.append({"titulo": titulo[:160], "url": enlace})
            if len(fuentes) >= 5:
                break
        if len(resumen) < 100:
            return None, "Gemini devolvió un texto demasiado corto para una ficha útil."
        if not fuentes:
            return None, "Gemini no devolvió fuentes web verificables para esta respuesta."
        return ({
            "encontrado": True,
            "nombre": nombre,
            "titulo": nombre,
            "resumen": resumen[:7000],
            "biografia": resumen if tipo == "artista" else "",
            "informacion": resumen if tipo == "cancion" else "",
            "fuentes": fuentes,
            "fuente_tipo": "gemini",
            "fuente": "Gemini con búsqueda web",
            "motor": "gemini"
        }, None)
    except HTTPError as error:
        detalle = ""
        try:
            cuerpo_error = json.loads(error.read().decode("utf-8"))
            detalle = str((cuerpo_error.get("error") or {}).get("message") or "")
        except Exception:
            pass
        if error.code == 402:
            mensaje = "Gemini devuelve HTTP 402: la cuenta API puede necesitar saldo o facturación activa."
        elif error.code in (401, 403):
            mensaje = "Gemini no acepta la clave o el proyecto no tiene permiso para usar la API."
        elif error.code == 429:
            mensaje = "Gemini ha alcanzado un límite de uso o cuota; hay que revisar la cuota del proyecto."
        else:
            mensaje = f"Gemini devuelve HTTP {error.code}."
        app.logger.warning("%s Detalle API: %s", mensaje, detalle[:500])
        return None, mensaje
    except Exception as error:
        app.logger.warning("No se pudo consultar Gemini para %s: %s", nombre, error)
        return None, "No se ha podido conectar con Gemini en este momento."


@app.get("/api/resumen-musical")
def api_resumen_musical():
    """Devuelve fichas exclusivamente generadas por Gemini con búsqueda web; nunca usa fuentes alternativas."""
    tipo = (request.args.get("tipo") or "").strip().lower()
    nombre = re.sub(r"\s+", " ", (request.args.get("nombre") or "").strip())[:180]
    artista = re.sub(r"\s+", " ", (request.args.get("artista") or "").strip())[:180]
    if tipo not in ("artista", "cancion") or not nombre or (tipo == "cancion" and not artista):
        return jsonify({
            "encontrado": False,
            "motor": "ninguno",
            "fuente_tipo": "ninguna",
            "error": "Falta el artista o la canción."
        }), 400

    resultado_gemini, error_gemini = _buscar_gemini_musical(tipo, nombre, artista)
    if resultado_gemini:
        return jsonify(resultado_gemini)

    # No devolver MusicBrainz, Last.fm ni Wikipedia si Gemini falla.
    mensaje = error_gemini or "Gemini no ha podido generar una ficha con fuentes verificables."
    app.logger.warning("No se generó ficha Gemini para %s (%s): %s", nombre, tipo, mensaje)
    return jsonify({
        "encontrado": False,
        "nombre": nombre,
        "titulo": nombre,
        "fuente_tipo": "ninguna",
        "motor": "ninguno",
        "aviso_gemini": mensaje,
        "error": mensaje,
        "fuentes": []
    }), 503

@app.get("/api/wikipedia")
def api_wikipedia():
    """Compatibilidad con páginas antiguas: redirige la consulta al endpoint exclusivo de Gemini."""
    # No usar caché ni lógica antigua: esta ruta no debe devolver MusicBrainz,
    # Last.fm ni Wikipedia aunque una versión anterior de la portada la solicite.
    return api_resumen_musical()



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