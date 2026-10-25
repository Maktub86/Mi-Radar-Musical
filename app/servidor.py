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

BOTON_HTML = r'''
<style>
#boton-actualizar{position:fixed;top:14px;right:16px;z-index:10000;width:44px;height:44px;border:1px solid #ffffff45;border-radius:50%;background:#e8bd62;color:#171717;font-size:24px;font-weight:bold;box-shadow:0 3px 14px #0008;cursor:pointer}
#boton-actualizar:hover{transform:scale(1.05)}
#boton-actualizar:disabled{opacity:.6;cursor:wait}
#panel-actualizacion{position:fixed;top:66px;right:16px;z-index:9999;background:#202633;color:#fff;padding:12px;border-radius:12px;box-shadow:0 3px 18px #0008;width:280px;max-width:calc(100vw - 32px);font:13px Arial}
#panel-actualizacion[hidden]{display:none}
#panel-actualizacion button{padding:7px 11px;border:0;border-radius:8px;background:#e8bd62;color:#171717;font-weight:bold;cursor:pointer}
#progreso-actualizacion{height:7px;background:#414858;border-radius:8px;margin-top:9px;overflow:hidden}
#barra-actualizacion{height:100%;width:0;background:#76e0c2;transition:width .2s}
#estado-actualizacion{display:block;margin-top:7px;line-height:1.4}
@media(max-width:600px){#boton-actualizar{top:8px;right:8px}#panel-actualizacion{top:58px;right:8px}}
</style>
<button id="boton-actualizar" type="button" title="Actualizar manualmente" aria-label="Actualizar manualmente">↻</button>
<div id="panel-actualizacion" hidden>
 <button id="cerrar-panel-actualizacion" type="button" aria-label="Cerrar">Cerrar</button>
 <div id="progreso-actualizacion"><div id="barra-actualizacion"></div></div>
 <span id="estado-actualizacion" role="status">Preparado para actualizar artistas, radar y listas.</span>
</div>
<script>
(()=>{
const b=document.getElementById('boton-actualizar');
const panel=document.getElementById('panel-actualizacion');
const cerrar=document.getElementById('cerrar-panel-actualizacion');
const e=document.getElementById('estado-actualizacion');
const barra=document.getElementById('barra-actualizacion');
let vigilando=false;
async function consultar(){
 const r=await fetch('/api/estado-actualizacion',{cache:'no-store'});
 const d=await r.json();
 barra.style.width=(d.progreso||0)+'%';
 e.textContent=(d.progreso||0)+'% · '+d.mensaje;
 b.disabled=!!d.en_curso;
 if(d.en_curso) panel.hidden=false;
 return d;
}
async function vigilar(){
 if(vigilando)return;
 vigilando=true;
 try{
  let d;
  do{
   await new Promise(r=>setTimeout(r,1500));
   d=await consultar();
  }while(d.en_curso);
 }catch(err){
  e.textContent='No se pudo consultar el progreso.';
  b.disabled=false;
 }finally{vigilando=false;}
}
b.addEventListener('click',async()=>{
 panel.hidden=false;
 try{
  const estado=await consultar();
  if(estado.en_curso){vigilar();return;}
 }catch(err){}
 if(!confirm('¿Actualizar todos los artistas, el radar y las tres listas musicales?'))return;
 b.disabled=true;barra.style.width='0%';e.textContent='Iniciando actualización completa…';
 try{
  const r=await fetch('/api/actualizar',{method:'POST'});
  const d=await r.json();
  if(!r.ok){e.textContent=d.error||'No se pudo iniciar.';b.disabled=false;return;}
  e.textContent=d.mensaje||'Actualización iniciada.';
  vigilar();
 }catch(err){
  e.textContent='No se pudo contactar con el servidor.';
  b.disabled=false;
 }
});
cerrar.addEventListener('click',()=>{if(!vigilando)panel.hidden=true;});
consultar().then(d=>{if(d.en_curso)vigilar();}).catch(()=>{});
})();
</script>
'''


def _pagina_portada(tipo="inicio"):
    html = (BASE / "portada.html").read_text(encoding="utf-8")
    html = html.replace("<body>", f'<body data-pagina="{tipo}">', 1)
    html = html.replace('href="#lista-youtube"', 'href="/listas/youtube"')
    html = html.replace('href="#lista-los40"', 'href="/listas/los40"')
    html = html.replace('href="#lista-canal-fiesta"', 'href="/listas/canal-fiesta"')
    estilos = """
<style>
body[data-pagina="inicio"] #listas-musicales{display:none}
body[data-pagina^="lista-"] main>.cabecera,
body[data-pagina^="lista-"] #estado,
body[data-pagina^="lista-"] #ultima-actualizacion,
body[data-pagina^="lista-"] #lista{display:none}
body[data-pagina="lista-youtube"] #lista-los40,
body[data-pagina="lista-youtube"] #lista-canal-fiesta{display:none}
body[data-pagina="lista-los40"] #lista-youtube,
body[data-pagina="lista-los40"] #lista-canal-fiesta{display:none}
body[data-pagina="lista-canal-fiesta"] #lista-youtube,
body[data-pagina="lista-canal-fiesta"] #lista-los40{display:none}
body[data-pagina^="lista-"] #listas-musicales{margin-top:0}
body[data-pagina^="lista-"] #listas-musicales>h2{margin-bottom:8px}
body[data-pagina^="lista-"] #listas-musicales>.sub{display:none}
</style>
"""
    html = html.replace("</head>", estilos + "\n</head>", 1)
    return html.replace("</body>", BOTON_HTML + "\n</body>")

@app.get("/")
def inicio():
    return _pagina_portada("inicio")

@app.get("/listas/<tipo>")
def pagina_lista(tipo):
    if tipo not in ("youtube", "los40", "canal-fiesta"):
        return "Lista no encontrada", 404
    return _pagina_portada("lista-" + tipo)

@app.get("/programas")
def pagina_programas():
    return "<!DOCTYPE html>\n<html lang=\"es\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<title>Programas · Mi Radar Musical</title>\n<style>\n:root{color-scheme:dark;--panel:#1b1b2d;--texto:#f7f5ff;--suave:#b8b6cf;--verde:#55e6bd}\n*{box-sizing:border-box}body{margin:0;background:linear-gradient(140deg,#17152d,#10101c 55%,#26152e);color:var(--texto);font-family:Segoe UI,Arial,sans-serif;min-height:100vh}\nheader{padding:30px 6%;background:linear-gradient(110deg,#5727a5,#b72d83 65%,#f06a76)}h1{font-size:clamp(32px,6vw,52px);margin:12px 0 8px}header p{margin:0}\nnav{display:flex;gap:10px;flex-wrap:wrap;padding:18px 6%;border-bottom:1px solid #ffffff18}nav a{color:#e8e5ff;text-decoration:none;background:#ffffff12;padding:10px 15px;border-radius:22px;font-size:14px}nav a.activo{background:#ff4fa3;color:#fff;font-weight:bold}\n.estilos-musicales{margin:0 0 24px;padding:0;background:#ffffff0a;border:1px solid #ffffff20;border-radius:14px;overflow:hidden}.estilos-musicales summary{cursor:pointer;list-style:none;padding:14px 18px;font-weight:800;background:#ffffff08}.estilos-musicales summary::-webkit-details-marker{display:none}.estilos-musicales summary:after{content:"＋";float:right;color:var(--verde)}.estilos-musicales[open] summary:after{content:"−"}.contenido-estilos{padding:0 18px 18px;color:var(--suave);line-height:1.8}.etiquetas-estilos{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.etiquetas-estilos span{display:inline-block;padding:5px 10px;border-radius:16px;background:#706bff26;border:1px solid #706bff66;color:#f7f5ff;font-size:13px}\nmain{max-width:1000px;margin:auto;padding:30px 6%}.programa{padding:20px;margin:12px 0;background:var(--panel);border:1px solid #ffffff18;border-radius:15px}.programa h2{margin:0 0 8px;font-size:21px}.programa p{color:var(--suave);line-height:1.5}.descargar{display:inline-block;padding:10px 15px;background:#2b765f;color:white;text-decoration:none;border-radius:20px;font-weight:bold}.aviso{font-size:13px;color:var(--suave);line-height:1.5}footer{text-align:center;color:var(--suave);font-size:12px;padding:30px}\n</style></head><body>\n<header><div>Tu universo musical</div><h1>🧰 Programas</h1><p>Enlaces para descargar las herramientas de tu colección musical.</p></header>\n<nav><a href=\"/\">🏠 Portada</a><a href=\"/listas/youtube\">▶ YouTube</a><a href=\"/listas/los40\">🎵 LOS40</a><a href=\"/listas/canal-fiesta\">📻 Canal Fiesta</a><a href=\"/lo-mejor\">⭐ Lo mejor</a><a href=\"/artistas\">🎤 Mis artistas</a><a class=\"activo\" href=\"/programas\">🧰 Programas</a></nav>\n<main>\n<details class=\"estilos-musicales\" id=\"estilos-musicales\"><summary>🎼 Estilos musicales</summary><div class=\"contenido-estilos\"><div class=\"etiquetas-estilos\"><span>Pop</span><span>Rock</span><span>Pop Rock</span><span>R&amp;B</span><span>Rumba / Flamenco</span><span>Fusión / Mestizaje</span><span>Urbana</span><span>Dance</span><span>Musical / BSO</span><span>Chill / Acústico</span><span>Autor / Raíz</span><span>Flamenco Pop</span><span>Latina</span><span>Disco</span><span>Flamenco de Autor</span><span>Dance Pop</span><span>Tropical</span></div><p><strong>Latina:</strong> Salsa, Bachata, Merengue, Cumbia y Bolero.</p></div></details>\n<section class=\"programa\"><h2>MediaHuman YouTube to MP3 Converter</h2><p>Descarga audio de vídeos y listas de reproducción. El enlace lleva a la web del desarrollador.</p><a class=\"descargar\" href=\"https://www.mediahuman.com/es/7/?mh_product=youtubetomp3\" target=\"_blank\" rel=\"noopener noreferrer\">Ir a la descarga oficial ↗</a></section>\n<section class=\"programa\"><h2>Mp3tag</h2><p>Editar etiquetas de canciones, artista, álbum y otros metadatos.</p><a class=\"descargar\" href=\"https://www.mp3tag.de/en/download.html\" target=\"_blank\" rel=\"noopener noreferrer\">Descargar desde Mp3tag ↗</a></section>\n<section class=\"programa\"><h2>ID3Remover</h2><p>Herramienta para eliminar etiquetas ID3 de archivos MP3. Es un programa antiguo; revisa la página y el archivo antes de instalarlo.</p><a class=\"descargar\" href=\"https://sourceforge.net/projects/id3remover/files/\" target=\"_blank\" rel=\"noopener noreferrer\">Ver archivos en SourceForge ↗</a></section>\n<section class=\"programa\"><h2>MP3Gain GUI</h2><p>Normaliza el volumen de archivos MP3. Enlace al proyecto original de MP3Gain.</p><a class=\"descargar\" href=\"https://mp3gain.sourceforge.net/download.php\" target=\"_blank\" rel=\"noopener noreferrer\">Descargar MP3Gain ↗</a></section>\n<p class=\"aviso\">Nota: los enlaces abren páginas externas. ID3Remover y MP3Gain son herramientas antiguas; crea una copia de seguridad antes de modificar archivos y comprueba que la versión sea compatible con tu Windows.</p>\n</main><footer>Mi Radar Musical</footer></body></html>"

@app.get("/lo-mejor")
def pagina_lo_mejor():
    return "<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Lo mejor · Mi Radar Musical</title>\n<style>:root{color-scheme:dark;--suave:#b8b6cf}*{box-sizing:border-box}body{margin:0;background:linear-gradient(140deg,#17152d,#10101c 55%,#26152e);color:#f7f5ff;font-family:Segoe UI,Arial,sans-serif;min-height:100vh}header{padding:30px 6%;background:linear-gradient(110deg,#5727a5,#b72d83 65%,#f06a76)}h1{font-size:clamp(32px,6vw,52px);margin:12px 0 8px}nav{display:flex;gap:10px;flex-wrap:wrap;padding:18px 6%;border-bottom:1px solid #ffffff18}nav a{color:#e8e5ff;text-decoration:none;background:#ffffff12;padding:10px 15px;border-radius:22px;font-size:14px}nav a.activo{background:#ff4fa3;color:#fff;font-weight:bold}main{max-width:900px;margin:auto;padding:30px 6%}.panel{padding:22px;background:#1b1b2d;border:1px solid #ffffff18;border-radius:15px;line-height:1.6}.suave{color:var(--suave)}</style></head><body><header><div>Tu universo musical</div><h1>⭐ Lo mejor</h1><p>Las cinco canciones más escuchadas de cada artista que sigues.</p></header><nav><a href=\"/\">🏠 Portada</a><a href=\"/listas/youtube\">▶ YouTube</a><a href=\"/listas/los40\">🎵 LOS40</a><a href=\"/listas/canal-fiesta\">📻 Canal Fiesta</a><a class=\"activo\" href=\"/lo-mejor\">⭐ Lo mejor</a><a href=\"/artistas\">🎤 Mis artistas</a><a href=\"/programas\">🧰 Programas</a></nav><main><section class=\"panel\"><h2>Falta elegir la fuente de popularidad</h2><p>Para mostrar las cinco canciones realmente más escuchadas, necesito basar el orden en una plataforma con datos de reproducciones. No quiero inventar un ranking a partir de búsquedas o resultados que no indican cuántas escuchas tiene cada canción.</p><p class=\"suave\">Esta sección se completará cuando elijas la fuente: por ejemplo, reproducciones de YouTube o popularidad de Spotify.</p></section></main></body></html>"

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

    titulo_objetivo = normalizar_texto(titulo)
    artista_objetivo = normalizar_texto(artista)

    def buscar_en_catalogo(url, fuente, campos):
        peticion = Request(
            url,
            headers={"User-Agent": "MiRadarMusical/1.0", "Accept": "application/json"}
        )
        with urlopen(peticion, timeout=8) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))

        if fuente == "Deezer":
            resultados = datos.get("data", [])
        else:
            resultados = datos.get("results", [])

        mejor = None
        mejor_puntuacion = 0.0
        mejor_titulo = 0.0
        mejor_artista = 0.0

        for resultado in resultados:
            if fuente == "Deezer":
                preview = resultado.get("preview")
                titulo_original = resultado.get("title")
                artista_original = (resultado.get("artist") or {}).get("name")
                enlace = resultado.get("link")
            else:
                preview = resultado.get("previewUrl")
                titulo_original = resultado.get("trackName")
                artista_original = resultado.get("artistName")
                enlace = resultado.get("trackViewUrl")

            titulo_resultado = normalizar_texto(titulo_original)
            artista_resultado = normalizar_texto(artista_original)
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
                mejor = {
                    "previewUrl": preview,
                    "trackViewUrl": enlace,
                    "titulo": titulo_original,
                    "artista": artista_original,
                    "fuente": fuente
                }
                mejor_titulo = similitud_titulo
                mejor_artista = similitud_artista

        if (
            not mejor or mejor_puntuacion < 0.76
            or mejor_titulo < 0.72 or mejor_artista < 0.60
        ):
            return None
        return mejor

    errores = []
    consulta_deezer = urlencode({"q": f"{artista} {titulo}", "limit": 15})
    try:
        resultado = buscar_en_catalogo(
            "https://api.deezer.com/search?" + consulta_deezer,
            "Deezer",
            None
        )
        if resultado:
            return jsonify({**resultado, "duracion": 30})
    except Exception:
        errores.append("Deezer")

    # Si Deezer no responde o no ofrece una coincidencia fiable con muestra,
    # se intenta Apple/iTunes como alternativa.
    parametros_itunes = urlencode({
        "term": f"{artista} {titulo}",
        "country": "es",
        "media": "music",
        "entity": "song",
        "limit": 15
    })
    try:
        resultado = buscar_en_catalogo(
            "https://itunes.apple.com/search?" + parametros_itunes,
            "Apple Music/iTunes",
            None
        )
        if resultado:
            return jsonify({**resultado, "duracion": 30})
    except Exception:
        errores.append("Apple Music/iTunes")

    if len(errores) == 2:
        return jsonify({
            "error": "No se ha podido consultar Deezer ni Apple Music/iTunes ahora mismo."
        }), 502

    return jsonify({
        "error": "No he encontrado una muestra que coincida con suficiente seguridad en Deezer ni en Apple Music/iTunes."
    }), 404

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
            log.write("\n==== Actualización completa manual ====\n")
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
                    porcentaje = min(85, int(85 * hecho / max(total, 1)))
                    with _candado_estado:
                        _estado_actualizacion["progreso"] = porcentaje
                        _estado_actualizacion["mensaje"] = f"Consultando artistas: {hecho} de {total}"

            codigo = proceso.wait()
            if codigo:
                raise RuntimeError("El detector falló. Consulta actualizacion_diaria.log.")

            with _candado_estado:
                _estado_actualizacion["progreso"] = 87
                _estado_actualizacion["mensaje"] = "Preparando el radar..."

            resultado = subprocess.run(
                [sys.executable, str(preparar)], cwd=str(raiz),
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if resultado.returncode:
                raise RuntimeError("No se pudo preparar el radar. Consulta el registro.")
            shutil.copy2(origen, destino)

            for numero, tipo in enumerate(("los40", "canal-fiesta", "youtube"), 1):
                with _candado_estado:
                    _estado_actualizacion["progreso"] = 87 + numero * 4
                    _estado_actualizacion["mensaje"] = f"Actualizando lista {numero} de 3: {tipo}"
                try:
                    lista = actualizar_lista(tipo)
                    log.write(f"Lista {tipo}: {lista.get('mensaje', '')}\n")
                    log.flush()
                    if lista.get("error"):
                        with _candado_estado:
                            _estado_actualizacion["mensaje"] = f"Advertencia en {tipo}: {lista.get('mensaje', 'error')}"
                except Exception as error_lista:
                    log.write(f"Error actualizando {tipo}: {error_lista}\n")
                    log.flush()
                    with _candado_estado:
                        _estado_actualizacion["mensaje"] = f"Advertencia en {tipo}: {error_lista}"

        with _candado_estado:
            _estado_actualizacion.update(
                en_curso=False, progreso=100,
                mensaje="Actualización completa finalizada."
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