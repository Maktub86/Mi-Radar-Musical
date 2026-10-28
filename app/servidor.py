import re
from flask import Flask, jsonify, send_from_directory, request
import csv
import json
import subprocess
import shutil
import threading
import time
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import unicodedata
import difflib
import os
import secrets
from listas_musicales import cargar as cargar_lista, actualizar as actualizar_lista

BASE = Path(__file__).resolve().parent
CSV_PATH = BASE.parent / "mi_radar_musical.csv"
DATOS_PATH = BASE.parent / "lanzamientos.json"
TAREA = "MiRadarMusical_Actualizacion"

app = Flask(__name__, static_folder=str(BASE), static_url_path="")

@app.after_request
def agregar_enlace_mi_musica(response):
    if response.mimetype == "text/html":
        html = response.get_data(as_text=True)
        # Una única navegación, con los mismos enlaces y en el mismo orden en todas las páginas.
        pestañas = [
            ("/", "🏠 Portada"),
            ("/listas/youtube", "▶ YouTube"),
            ("/listas/los40", "🎵 LOS40"),
            ("/listas/canal-fiesta", "📻 Canal Fiesta"),
            ("/lo-mejor", "🎤 Cantantes"),
            ("/mi-musica", "🎧 Mi música"),
            ("/recomendaciones", "✨ Recomendaciones"),
            ("/programas", "🧰 Programas"),
        ]
        ruta = request.path.rstrip("/") or "/"
        enlaces = []
        for href, etiqueta in pestañas:
            activa = (ruta == href) or (href != "/" and ruta.startswith(href + "/"))
            clase = ' class="activo"' if activa else ""
            enlaces.append(f'<a{clase} href="{href}">{etiqueta}</a>')
        nav_comun = '<nav class="navegacion-comun">' + "\n".join(enlaces) + "</nav>"
        if re.search(r"<nav\b[^>]*>.*?</nav>", html, flags=re.IGNORECASE | re.DOTALL):
            html = re.sub(r"<nav\b[^>]*>.*?</nav>", lambda _: nav_comun, html, count=1, flags=re.IGNORECASE | re.DOTALL)
        css_nav = """
<style id="navegacion-comun-estilos">
nav.navegacion-comun{display:flex;flex-flow:row wrap;align-items:center;gap:8px;padding:10px 6%;box-sizing:border-box;width:100%}
nav.navegacion-comun a{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;margin:0!important;white-space:nowrap;text-decoration:none}
nav.navegacion-comun a.activo{font-weight:700}
button,a[role=button],.icono-boton,[class*=icono][role=button]{transition:filter .15s ease,transform .15s ease,box-shadow .15s ease}
button:hover,a[role=button]:hover,.icono-boton:hover,[class*=icono][role=button]:hover{filter:brightness(1.18);transform:translateY(-1px)}
button:focus-visible,a:focus-visible{outline:2px solid #c9a5ff;outline-offset:3px}
/* Identidad común para los iconos de muestra, descarga y YouTube en toda la web */
.boton-30,.boton-muestra,.b30{
  display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:7px!important;
  min-height:42px!important;border-radius:12px!important;padding:0 12px!important;
  background:linear-gradient(135deg,#7867ff 0%,#9b45cf 52%,#d43e8f 100%)!important;
  border:1px solid #ffffff70!important;color:#fff!important;font-weight:850!important;
  box-shadow:0 4px 12px #7c45d044,inset 0 1px 0 #ffffff35!important;
  text-decoration:none!important;cursor:pointer!important;
}
.boton-mediahuman,.boton-descarga-radar,.descarga{
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
  min-width:42px!important;min-height:42px!important;padding:8px 11px!important;border-radius:12px!important;
  background:linear-gradient(135deg,#168653,#20ad70)!important;border:1px solid #69e5a4!important;
  color:#fff!important;font-size:19px!important;font-weight:900!important;
  box-shadow:0 4px 12px #16865340,inset 0 1px 0 #ffffff35!important;
  text-decoration:none!important;cursor:pointer!important;
}
.boton-youtube,.youtube{
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
  min-width:42px!important;min-height:42px!important;padding:8px 11px!important;border-radius:12px!important;
  background:linear-gradient(135deg,#ff4545,#d80d20)!important;border:1px solid #ff8c8c!important;
  color:#fff!important;font-size:17px!important;font-weight:900!important;
  box-shadow:0 4px 12px #e6212940,inset 0 1px 0 #ffffff35!important;
  text-decoration:none!important;cursor:pointer!important;
}
.boton-30:hover,.boton-muestra:hover,.b30:hover,
.boton-mediahuman:hover,.boton-descarga-radar:hover,.descarga:hover,
.boton-youtube:hover,.youtube:hover{
  filter:brightness(1.15)!important;transform:translateY(-2px) scale(1.035)!important;
  box-shadow:0 7px 18px #0004,inset 0 1px 0 #ffffff55!important;
}
.boton-30:active,.boton-muestra:active,.b30:active,
.boton-mediahuman:active,.boton-descarga-radar:active,.descarga:active,
.boton-youtube:active,.youtube:active{transform:translateY(0) scale(.98)!important}
.boton-30:focus-visible,.boton-muestra:focus-visible,.b30:focus-visible,
.boton-mediahuman:focus-visible,.boton-descarga-radar:focus-visible,.descarga:focus-visible,
.boton-youtube:focus-visible,.youtube:focus-visible{outline:2px solid #f0d7ff!important;outline-offset:3px!important}

#modal-info-musical[hidden]{display:none!important}\n.wiki-icon,.boton-wikipedia,.wiki{display:inline-flex!important;align-items:center!important;justify-content:center!important;width:30px!important;height:30px!important;min-width:30px!important;padding:0!important;border-radius:50%!important;border:1px solid #ffffffa8!important;background:linear-gradient(145deg,#b58aff,#7440b8 65%,#54258c)!important;color:#fff!important;font-size:16px!important;font-family:Segoe UI,Arial,sans-serif!important;font-weight:900!important;line-height:1!important;text-align:center!important;box-shadow:0 3px 10px #0004,inset 0 1px 0 #ffffff55!important;cursor:pointer!important;vertical-align:middle!important;transition:transform .15s ease,filter .15s ease!important}\n.wiki-icon:hover,.boton-wikipedia:hover,.wiki:hover{transform:translateY(-1px) scale(1.06);filter:brightness(1.12)}\n.wiki-icon:focus-visible,.boton-wikipedia:focus-visible,.wiki:focus-visible{outline:2px solid #e8d4ff;outline-offset:3px}
@media(max-width:760px){nav.navegacion-comun{gap:6px;padding:8px 5%}nav.navegacion-comun a{font-size:14px;padding:8px 10px}}
</style>
"""
        if "</head>" in html:
            enlaces_marca = """
<link rel="icon" type="image/png" sizes="192x192" href="/icono-mrm-192.png?v=3">
<link rel="icon" type="image/svg+xml" href="/icono-mrm.svg?v=3">
<link rel="apple-touch-icon" sizes="192x192" href="/icono-mrm-192.png?v=3">
<link rel="manifest" href="/manifest.webmanifest?v=3">
<meta name="theme-color" content="#6d28a8">
<meta name="application-name" content="Mi Radar Musical">
"""
            html = html.replace("</head>", enlaces_marca + css_nav + "</head>", 1)
        # Los iconos informativos solo aparecen si la actualización diaria guardó
        # una ficha con fuentes verificables. La normalización coincide con el preparador.
        script_resumenes = r"""
<script id="visibilidad-resumenes-cache">
(function(){
 function normalizar(v){return String(v||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z0-9]+/g,' ').trim();}
 function clave(b){return [b.dataset.resumenTipo||'',normalizar(b.dataset.resumenNombre),normalizar(b.dataset.resumenArtista)].join('|');}
 let disponibles=new Set(),cargado=false;
 function aplicar(){document.querySelectorAll('[data-resumen-tipo]').forEach(b=>{b.hidden=false;b.style.display='';});}
 const observador=new MutationObserver(aplicar);observador.observe(document.documentElement,{childList:true,subtree:true});
 aplicar();
})();
</script>
"""
        if "</body>" in html and "visibilidad-resumenes-cache" not in html:
            html = html.replace("</body>", script_resumenes + "</body>", 1)
        response.set_data(html)
    return response


BOTON_HTML = ''

LIMPIAR_CONTROLES_HTML = r"""
<style>
#boton-actualizar,#panel-actualizacion,[aria-label="Actualizar manualmente"],[title="Actualizar manualmente"]{display:none!important;visibility:hidden!important;pointer-events:none!important}
</style>
<script>
(function(){
 function quitar(){
  document.querySelectorAll('#boton-actualizar,#panel-actualizacion,[aria-label="Actualizar manualmente"],[title="Actualizar manualmente"]').forEach(function(n){n.remove();});
  document.querySelectorAll('button,a,[role="button"]').forEach(function(n){
   var t=(n.innerText||n.textContent||'').trim();
   if(t==='↻' || t==='⟳' || t==='⟲' || t==='↻ Actualizar') n.remove();
  });
 }
 quitar();
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',quitar);
 new MutationObserver(quitar).observe(document.documentElement,{childList:true,subtree:true});
})();
</script>
"""


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
body[data-pagina^="lista-"] .selector-lanzamientos,
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
    estilos += """
<style>
/* Vistas de listas: identidad visual propia, manteniendo los datos y funciones existentes */
body[data-pagina="lista-youtube"]{--panel:#211a2b;--suave:#d0c2df;--verde:#ff6565;--rosa:#ff3333;--azul:#d72b2b;background:linear-gradient(140deg,#210d13,#111018 58%,#32151b)}
body[data-pagina="lista-youtube"] header{background:linear-gradient(110deg,#8f1019,#e62129 65%,#ff6262)}
body[data-pagina="lista-los40"]{--panel:#17283a;--suave:#c3d9ed;--verde:#5fe2d0;--rosa:#ff7b42;--azul:#168fe5;background:linear-gradient(140deg,#0c1c2c,#10101c 58%,#142e42)}
body[data-pagina="lista-los40"] header{background:linear-gradient(110deg,#075ca8,#1285c7 65%,#31c5dc)}
body[data-pagina="lista-canal-fiesta"]{--panel:#172a2b;--suave:#c0e3d7;--verde:#a7ed79;--rosa:#f0b943;--azul:#20a77c;background:linear-gradient(140deg,#102522,#10101c 58%,#183a2f)}
body[data-pagina="lista-canal-fiesta"] header{background:linear-gradient(110deg,#075a43,#078b66 65%,#8ccf53)}
body[data-pagina="lista-youtube"] nav a[href="/listas/youtube"],
body[data-pagina="lista-los40"] nav a[href="/listas/los40"],
body[data-pagina="lista-canal-fiesta"] nav a[href="/listas/canal-fiesta"]{background:var(--rosa);color:#fff;font-weight:bold}
body[data-pagina="lista-youtube"] .actualizar-lista{background:linear-gradient(100deg,#b71924,#ff4444)}
body[data-pagina="lista-los40"] .actualizar-lista{background:linear-gradient(100deg,#0874bd,#27b6d4)}
body[data-pagina="lista-canal-fiesta"] .actualizar-lista{background:linear-gradient(100deg,#08734f,#9acb42)}
body[data-pagina^="lista-"] main>.cabecera,
body[data-pagina^="lista-"] main>.botones,
body[data-pagina^="lista-"] #estado,
body[data-pagina^="lista-"] #ultima-actualizacion,
body[data-pagina^="lista-"] #lista{display:none!important}
body[data-pagina^="lista-"] #listas-musicales{margin-top:0;padding-top:0;border-top:0}
body[data-pagina^="lista-"] #listas-musicales>h2{font-size:30px;margin-bottom:8px}
body[data-pagina^="lista-"] #listas-musicales>.sub{display:none}
</style>
"""
    html = html.replace("</head>", estilos + "\n</head>", 1)
    script_vista = """
<script>
(()=> {
 const pagina=document.body.dataset.pagina||"inicio";
 const config={
  "lista-youtube":{titulo:"Tendencias YouTube",subtitulo:"Lo que está marcando tendencia en YouTube",nav:"/listas/youtube"},
  "lista-los40":{titulo:"Los 40",subtitulo:"La lista musical de Los 40",nav:"/listas/los40"},
  "lista-canal-fiesta":{titulo:"Canal Fiesta",subtitulo:"Los éxitos de Canal Fiesta",nav:"/listas/canal-fiesta"}
 };
 const vista=config[pagina];
 if(!vista)return;
 const h1=document.querySelector("header h1");
 if(h1)h1.textContent=(pagina==="lista-youtube"?"▶ ":pagina==="lista-los40"?"🎵 ":"📻 ")+vista.titulo;
 const lema=document.querySelector("header p");
 if(lema)lema.textContent=vista.subtitulo;
 const h2=document.querySelector("#listas-musicales>h2");
 if(h2)h2.textContent=vista.titulo;
 document.querySelectorAll("nav a").forEach(a=>{
  a.classList.toggle("activo",a.getAttribute("href")===vista.nav);
 });
})();
</script>
"""
    return html.replace("</body>", script_vista + BOTON_HTML + LIMPIAR_CONTROLES_HTML + "\n</body>")

@app.get("/")
def inicio():
    return _pagina_portada("inicio")

@app.get("/listas/<tipo>")
def pagina_lista(tipo):
    if tipo not in ("youtube", "los40", "canal-fiesta"):
        return "Lista no encontrada", 404
    return _pagina_portada("lista-" + tipo)

# Caché en memoria para no volver a leer el archivo de portada completo en cada clic.
_cache_portada = {"mtime": None, "publicaciones": []}
_candado_cache_portada = threading.Lock()


def _fecha_clave_portada(valor):
    """Devuelve una clave numérica de fecha y descarta fechas inválidas o futuras."""
    texto = str(valor or "").strip()
    coincidencia = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", texto)
    if not coincidencia:
        return None
    anio, mes, dia = coincidencia.groups()
    try:
        anio = int(anio)
        mes_num = int(mes or 0)
        dia_num = int(dia or 0)
        fecha_base = date(anio, mes_num or 1, dia_num or 1)
    except (TypeError, ValueError):
        return None
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
    if fecha_base > hoy:
        return None
    return (anio, mes_num, dia_num)


def _tipo_normalizado_portada(valor):
    tipo = str(valor or "").strip().casefold()
    if tipo in ("single", "singles"):
        return "Single"
    if tipo in ("album", "álbum", "albums", "álbumes"):
        return "Album"
    return tipo


@app.get("/api/portada")
def api_portada():
    """Devuelve solo las 12 o 32 novedades del tipo solicitado, sin fechas futuras."""
    tipo = _tipo_normalizado_portada(request.args.get("tipo") or "Single")
    if tipo not in ("Single", "Album"):
        return jsonify({"error": "Tipo de publicación no válido."}), 400
    try:
        cantidad = int(request.args.get("cantidad", "12"))
    except (TypeError, ValueError):
        cantidad = 12
    if cantidad not in (12, 32):
        cantidad = 12

    ruta = BASE / "portada.json"
    try:
        mtime = ruta.stat().st_mtime_ns
        with _candado_cache_portada:
            if _cache_portada["mtime"] != mtime:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                if not isinstance(datos, list):
                    raise ValueError("El archivo de portada no contiene una lista.")
                _cache_portada["publicaciones"] = datos
                _cache_portada["mtime"] = mtime
            publicaciones = list(_cache_portada["publicaciones"])
    except (OSError, json.JSONDecodeError, ValueError):
        app.logger.exception("No se pudo cargar el catálogo de portada.")
        return jsonify({"error": "No se han podido cargar las publicaciones."}), 503

    filtradas = []
    for publicacion in publicaciones:
        if not isinstance(publicacion, dict):
            continue
        if _tipo_normalizado_portada(publicacion.get("tipo")) != tipo:
            continue
        fecha = str(publicacion.get("fecha") or "").strip()
        clave_fecha = _fecha_clave_portada(fecha)
        if fecha and clave_fecha is None:
            continue
        filtradas.append((clave_fecha or (0, 0, 0), publicacion))

    filtradas.sort(
        key=lambda item: (bool(item[0][0]), item[0], str(item[1].get("titulo") or "").casefold()),
        reverse=True,
    )
    respuesta = jsonify({
        "tipo": tipo,
        "total": len(filtradas),
        "publicaciones": [item[1] for item in filtradas[:cantidad]],
    })
    respuesta.headers["Cache-Control"] = "public, max-age=180"
    return respuesta


@app.get("/programas")
def pagina_programas():
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Programas · Mi Radar Musical</title>
<style>
:root{color-scheme:dark;--panel:#1b1b2d;--texto:#f7f5ff;--suave:#b8b6cf;--verde:#55e6bd}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(140deg,#17152d,#10101c 55%,#26152e);color:var(--texto);font-family:Segoe UI,Arial,sans-serif;min-height:100vh}
header{padding:30px 6%;background:linear-gradient(110deg,#5727a5,#b72d83 65%,#f06a76)}
h1{font-size:clamp(32px,6vw,52px);margin:12px 0 8px}header p{margin:0}
nav{display:flex;gap:10px;flex-wrap:wrap;padding:18px 6%;border-bottom:1px solid #ffffff18}
nav a{color:#e8e5ff;text-decoration:none;background:#ffffff12;padding:10px 15px;border-radius:22px;font-size:14px}
nav a.activo{background:#ff4fa3;color:#fff;font-weight:bold}
main{max-width:1000px;margin:auto;padding:30px 6%}
.programa{padding:20px;margin:12px 0;background:var(--panel);border:1px solid #ffffff18;border-radius:15px}
.programa h2{margin:0 0 8px;font-size:clamp(22px,3vw,28px)}
.programa p{color:var(--suave);line-height:1.5}
.descargar{display:inline-block;padding:10px 15px;background:#2b765f;color:white;text-decoration:none;border-radius:20px;font-weight:bold}
.boton-estilos{display:inline-block;padding:12px 18px;background:#326de6;color:white;border:0;border-radius:20px;font-size:15px;font-weight:800;cursor:pointer}
.boton-estilos:hover{background:#4782ff}
.aviso{font-size:13px;color:var(--suave);line-height:1.5}
.modal-estilos[hidden]{display:none}
.modal-estilos{position:fixed;inset:0;z-index:30000;background:#000c;display:flex;align-items:center;justify-content:center;padding:16px}
.caja-estilos{width:min(720px,100%);max-height:86vh;overflow:auto;background:#171b29;color:#fff;border:1px solid #ffffff25;border-radius:16px;padding:20px;box-shadow:0 12px 45px #0009}
.cabecera-estilos{display:flex;align-items:center;justify-content:space-between;gap:12px}
.cabecera-estilos h2{margin:0;font-size:24px}
.cerrar-estilos{background:#34394a;border:0;border-radius:9px;padding:9px 12px;color:#fff;cursor:pointer}
.texto-estilos{color:var(--suave);line-height:1.5}
.copiar-todos-estilos{background:#326de6;border:0;border-radius:10px;padding:11px 15px;color:#fff;font-weight:800;cursor:pointer;margin:0 0 12px}
.lista-estilos-copiables{display:flex;flex-wrap:wrap;gap:8px}
.estilo-copiable{background:#242b40;border:1px solid #536fae;border-radius:18px;padding:9px 13px;color:#fff;cursor:pointer}
.estilo-copiable:hover{background:#344b78}
.estado-copiar-estilos{color:var(--verde);min-height:20px;font-size:13px}
footer{text-align:center;color:var(--suave);font-size:12px;padding:30px}
</style>
</head>
<body>
<script>try{if(localStorage.getItem('mrWikipediaEnabled')==='0')document.body.dataset.wikipediaOff='1'}catch(e){}</script>
<header><div>Tu universo musical</div><h1>🧰 Programas</h1><p>Enlaces para descargar las herramientas de tu colección musical.</p></header>
<nav>
<a href="/">🏠 Portada</a>
<a href="/listas/youtube">▶ YouTube</a>
<a href="/listas/los40">🎵 LOS40</a>
<a href="/listas/canal-fiesta">📻 Canal Fiesta</a>
<a href="/lo-mejor">⭐ Lo mejor</a>
<a class="activo" href="/programas">🧰 Programas</a>

</nav>
<main>
<section class="programa"><h2>MediaHuman YouTube to MP3 Converter</h2><p>Descarga audio de vídeos y listas de reproducción. El enlace lleva a la web del desarrollador.</p><a class="descargar" href="https://www.mediahuman.com/es/7/?mh_product=youtubetomp3" target="_blank" rel="noopener noreferrer">Ir a la descarga oficial ↗</a></section>
<section class="programa"><h2>Mp3tag</h2><p>Editar etiquetas de canciones, artista, álbum y otros metadatos.</p><a class="descargar" href="https://www.mp3tag.de/en/download.html" target="_blank" rel="noopener noreferrer">Descargar desde Mp3tag ↗</a></section>
<section class="programa"><h2>ID3Remover</h2><p>Herramienta para eliminar etiquetas ID3 de archivos MP3. Es un programa antiguo; revisa la página y el archivo antes de instalarlo.</p><a class="descargar" href="https://sourceforge.net/projects/id3remover/files/" target="_blank" rel="noopener noreferrer">Ver archivos en SourceForge ↗</a></section>
<section class="programa"><h2>MP3Gain GUI</h2><p>Normaliza el volumen de archivos MP3. Enlace al proyecto original de MP3Gain.</p><a class="descargar" href="https://mp3gain.sourceforge.net/download.php" target="_blank" rel="noopener noreferrer">Descargar MP3Gain ↗</a></section>
<p class="aviso">Nota: los enlaces abren páginas externas. ID3Remover y MP3Gain son herramientas antiguas; crea una copia de seguridad antes de modificar archivos y comprueba que la versión sea compatible con tu Windows.</p>
<section class="programa"><h2>Estilos musicales</h2><p>Consulta la lista en una ventana independiente y copia un estilo concreto o todos los estilos de una vez.</p><button type="button" id="abrir-estilos" class="boton-estilos">🎼 Desplegar estilos musicales</button></section>
</main>
<div id="modal-estilos" class="modal-estilos" hidden role="dialog" aria-modal="true" aria-labelledby="titulo-estilos">
<div class="caja-estilos">
<div class="cabecera-estilos"><h2 id="titulo-estilos">🎼 Estilos musicales</h2><button type="button" id="cerrar-estilos" class="cerrar-estilos">Cerrar ✕</button></div>
<p class="texto-estilos">Pulsa un estilo para copiarlo. También puedes copiar la lista completa.</p>
<button type="button" id="copiar-todos-estilos" class="copiar-todos-estilos">📋 Copiar todos los estilos</button>
<div id="lista-estilos-copiables" class="lista-estilos-copiables"></div>
<p id="estado-copiar-estilos" class="estado-copiar-estilos" role="status"></p>
</div></div>
<script>
(function(){
 const estilos=["Pop","Rock","Pop Rock","R&B","Rumba / Flamenco","Fusión / Mestizaje","Urbana","Dance","Musical / BSO","Chill / Acústico","Autor / Raíz","Flamenco Pop","Latina","Disco","Flamenco de Autor","Dance Pop","Tropical"];
 const modal=document.getElementById("modal-estilos");
 const lista=document.getElementById("lista-estilos-copiables");
 const estado=document.getElementById("estado-copiar-estilos");
 async function copiar(texto){
  try{await navigator.clipboard.writeText(texto);estado.textContent="✓ Copiado al portapapeles.";}
  catch(e){window.prompt("Copia el texto:",texto);estado.textContent="Si no se copió automáticamente, copia el texto de la ventana.";}
 }
 for(const estilo of estilos){
  const b=document.createElement("button");b.type="button";b.className="estilo-copiable";b.textContent=estilo;b.title="Copiar "+estilo;
  b.addEventListener("click",()=>copiar(estilo));lista.appendChild(b);
 }
 document.getElementById("copiar-todos-estilos").addEventListener("click",()=>copiar(estilos.join("\\n")+"\\n\\nLatina: Salsa, Bachata, Merengue, Cumbia y Bolero."));
 document.getElementById("abrir-estilos").addEventListener("click",()=>{modal.hidden=false;document.getElementById("cerrar-estilos").focus();});
 function cerrar(){modal.hidden=true;}
 document.getElementById("cerrar-estilos").addEventListener("click",cerrar);
 modal.addEventListener("click",e=>{if(e.target===modal)cerrar();});
 document.addEventListener("keydown",e=>{if(e.key==="Escape")cerrar();});
})();
</script>
<footer>Mi Radar Musical</footer>
</body></html>"""


@app.get("/lo-mejor")
def pagina_lo_mejor():
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lo mejor · Mi Radar Musical</title>
<style>
:root{color-scheme:dark;--suave:#b8b6cf;--panel:#1b1b2d;--verde:#55e6bd}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(140deg,#17152d,#10101c 55%,#26152e);color:#f7f5ff;font-family:Segoe UI,Arial,sans-serif;min-height:100vh}

header{padding:30px 6%;background:linear-gradient(110deg,#5727a5,#b72d83 65%,#f06a76)}
h1{font-size:clamp(32px,6vw,52px);margin:12px 0 8px}
nav{display:flex;gap:10px;flex-wrap:wrap;padding:18px 6%;border-bottom:1px solid #ffffff18}
nav a{color:#e8e5ff;text-decoration:none;background:#ffffff12;padding:10px 15px;border-radius:22px;font-size:14px}
nav a.activo{background:#ff4fa3;color:#fff;font-weight:bold}
main{max-width:1100px;margin:auto;padding:28px 5%}
#buscar-artista{width:100%;padding:13px 15px;border-radius:12px;border:1px solid #ffffff25;background:#171827;color:#fff;font-size:16px;margin:0 0 16px}
#estado-lo-mejor{color:var(--suave);font-size:14px;margin:8px 0 18px}
.artista-mejor{background:var(--panel);border:1px solid #ffffff18;border-radius:14px;margin:10px 0;overflow:hidden}
.artista-mejor .canciones-populares{background:#30264b;border:1px solid #8b6ce0;border-radius:0 0 10px 10px;padding:12px 16px 14px;margin:0 8px 10px}
.artista-mejor .canciones-recientes{background:#193b32;border:1px solid #46c49b;border-radius:0 0 10px 10px;padding:12px 16px 14px;margin:0 8px 10px}
.artista-mejor .canciones-publicaciones{background:#463018;border:1px solid #e7a84e;border-radius:0 0 10px 10px;padding:12px 16px 14px;margin:0 8px 10px}
.artista-mejor .boton-populares{background:linear-gradient(100deg,#6043a0,#9876e8)}
.artista-mejor .boton-recientes{background:linear-gradient(100deg,#116b55,#36b58a)}
.artista-mejor .boton-publicaciones{background:linear-gradient(100deg,#995b19,#e6a33e);color:#211506}
.publicacion-mejor{padding:10px 0;border-top:1px solid #ffffff20}
.publicacion-mejor small{display:block;color:#f0c98e;margin-top:4px}
.cabecera-artista{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:15px 17px}
.cabecera-artista h2{font-size:18px;margin:0}
.botones-ranking{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.botones-ranking button{font-size:13px;padding:9px 11px}
button{cursor:pointer;border:0;border-radius:9px;padding:10px 13px;background:linear-gradient(100deg,#706bff,#b72d83);color:#fff;font-weight:700}
button:disabled{opacity:.55;cursor:wait}
.canciones-artista{padding:0 16px 14px}
.pista{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;padding:12px 0;border-top:1px solid #ffffff12}
.pista-titulo{font-weight:700}.pista-meta{font-size:12px;color:var(--suave);margin-top:4px}
.acciones-pista{display:grid;grid-template-columns:82px 42px 42px 42px;grid-template-rows:40px;grid-auto-flow:column;gap:7px;justify-content:start;align-content:start;align-items:stretch;width:max-content;min-width:229px;flex-wrap:nowrap}
.acciones-pista button{box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;line-height:1;vertical-align:middle;width:42px;height:40px;min-height:40px;padding:7px 3px;margin:0;min-width:42px;white-space:nowrap}
.acciones-pista .boton-30{grid-column:1;grid-row:1;width:82px;height:40px;min-height:40px;padding:8px 7px;font-weight:800;font-size:15px;min-width:82px}
.acciones-pista .boton-mediahuman{grid-column:2;grid-row:1;align-self:center}
.acciones-pista .boton-youtube{grid-column:3;grid-row:1}
.acciones-pista .boton-completa{grid-column:4;grid-row:1}
.boton-30,.boton-completa{background:#292d3b;border:1px solid #ffffff30;color:#fff;min-width:42px}
.boton-30{flex:0 0 82px;width:82px;background:linear-gradient(120deg,#ff4fa3,#8a4dff 52%,#20bde8);border:1px solid #ffffff50;box-shadow:0 3px 12px #8e42e833}
.boton-mediahuman{background:#238b55;color:#fff;border:1px solid #55c783;min-width:42px}
.boton-youtube{background:#e62129;color:#fff;min-width:42px}
.boton-youtube:hover{background:#ff333b}
.boton-wikipedia{display:inline-flex;align-items:center;justify-content:center;flex:0 0 30px;width:30px;height:30px;margin-left:8px;border-radius:5px;background:#777d88;color:#fff;font-weight:900;border:1px solid #a8adb6;cursor:pointer;text-decoration:none}
.historia-wikipedia{grid-column:1/-1;margin:9px 0;padding:12px;border-left:3px solid #aeb4c0;background:#ffffff0b;border-radius:7px;color:#e4e4ec;font-size:14px;line-height:1.5}
.historia-wikipedia a{color:#c9b0ff}
.barra-alfabetica{display:flex;flex-wrap:wrap;gap:5px;margin:10px 0 16px;position:sticky;top:6px;z-index:100;background:#17152deb;backdrop-filter:blur(12px);padding:10px;border:1px solid #ffffff20;border-radius:13px}
.barra-alfabetica button{min-width:30px;padding:7px 8px;background:#ffffff12;border:1px solid #ffffff20;color:#eee;border-radius:8px}
.barra-alfabetica button.activa{background:#ff4fa3;color:#fff;font-weight:900}
.barra-alfabetica .boton-estrella{font-size:17px;min-width:30px;padding:7px 8px;background:#ffffff12;border:1px solid #ffffff20;color:#eee}
.barra-alfabetica .boton-estrella.activa{background:#ff4fa3;color:#fff;font-weight:900;box-shadow:none}
#letra-actual{position:fixed;right:16px;bottom:22px;z-index:15000;background:#ff4fa3;color:#fff;font-size:24px;font-weight:900;width:48px;height:48px;border-radius:13px;display:flex;align-items:center;justify-content:center;box-shadow:0 5px 24px #0008;pointer-events:none}
#letra-actual[hidden]{display:none}
.reproductor-completo{width:100%;aspect-ratio:16/9;border:0;border-radius:12px;margin:12px 0;background:#000}

.boton-secundario{background:#ffffff12;border:1px solid #ffffff20}
.mensaje-pista{grid-column:1/-1;color:var(--suave);font-size:13px}
#modal-youtube[hidden]{display:none}
#modal-youtube{position:fixed;inset:0;z-index:20000;background:#000b;display:flex;align-items:center;justify-content:center;padding:18px}
.modal-caja{background:#1b1b2d;border:1px solid #ffffff25;border-radius:16px;width:min(700px,100%);max-height:85vh;overflow:auto;padding:18px}
.modal-top{display:flex;justify-content:space-between;gap:12px;align-items:center}.modal-top h2{font-size:20px;margin:0}
.resultado-youtube{display:block;width:100%;text-align:left;margin-top:8px;background:#ffffff0b;border:1px solid #ffffff18}
.resultado-youtube span{display:block;color:var(--suave);font-size:12px;margin-top:5px}
@media(max-width:600px){.cabecera-artista{align-items:flex-start;flex-direction:column}.pista{grid-template-columns:1fr}.acciones-pista{justify-content:flex-start}}
</style></head>
<body>
<header><div>Tu universo musical</div><h1>⭐ Lo mejor</h1><p>Consulta los temas más populares de cada artista o descubre sus éxitos recientes.</p></header>
<nav><a href="/">🏠 Portada</a><a href="/listas/youtube">▶ YouTube</a><a href="/listas/los40">🎵 LOS40</a><a href="/listas/canal-fiesta">📻 Canal Fiesta</a><a class="activo" href="/lo-mejor">⭐ Lo mejor</a><a href="/programas">🧰 Programas</a></nav>
<main><input id="buscar-artista" type="search" placeholder="Buscar artista de tu lista…"><div id="alfabeto-lo-mejor" class="barra-alfabetica" aria-label="Buscar por inicial"></div><div id="letra-actual" hidden aria-live="polite"></div><div id="estado-lo-mejor" role="status">Cargando tus artistas…</div><div id="artistas-lo-mejor"></div></main>
<div id="modal-youtube" hidden role="dialog" aria-modal="true" aria-labelledby="titulo-modal-youtube"><div class="modal-caja"><div class="modal-top"><h2 id="titulo-modal-youtube">Elegir versión para MediaHuman</h2><button id="cerrar-modal" class="boton-secundario">Cerrar ✕</button></div><p id="estado-youtube">Buscando en YouTube…</p><div id="reproductor-completo"></div><div id="resultados-youtube"></div></div></div>
<script>
const estado=document.getElementById('estado-lo-mejor');
const contenedor=document.getElementById('artistas-lo-mejor');
const buscar=document.getElementById('buscar-artista');
const modal=document.getElementById('modal-youtube');
const estadoYoutube=document.getElementById('estado-youtube');
const resultadosYoutube=document.getElementById('resultados-youtube');
const reproductorCompleto=document.getElementById('reproductor-completo');
let artistas=[];
let inicialSeleccionada='';
const alfabetoLoMejor=document.getElementById('alfabeto-lo-mejor');
const letraActual=document.getElementById('letra-actual');
const letrasAlfabeto=['#',...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')];
let mostrandoFavoritos=false;
let topArtistasColeccion=[];
let artistasBase=artistas;
const botonEstrella=nodo('button','boton-estrella','⭐');
botonEstrella.type='button';botonEstrella.title='Mostrar tus 20 artistas con más canciones';botonEstrella.setAttribute('aria-label','Mostrar tus 20 artistas con más canciones');
botonEstrella.addEventListener('click',async()=>{
 mostrandoFavoritos=!mostrandoFavoritos;
 if(mostrandoFavoritos&&!topArtistasColeccion.length){
  estado.textContent='Calculando tus 20 artistas con más canciones…';
  try{const r=await fetch('/api/lo-mejor/artistas',{cache:'no-store'});if(!r.ok)throw new Error();topArtistasColeccion=await r.json();}
  catch(e){mostrandoFavoritos=false;estado.textContent='No se ha podido cargar el top 20 de tu colección.';return;}
 }
 artistasBase=mostrandoFavoritos?topArtistasColeccion:artistas;
 inicialSeleccionada='';
 botonEstrella.classList.toggle('activa',mostrandoFavoritos);
 botonEstrella.title=mostrandoFavoritos?'Volver a todos los artistas':'Mostrar tus 20 artistas con más canciones';
 mostrarArtistas();
});
alfabetoLoMejor.appendChild(botonEstrella);
function normalizarNombre(v){return String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleUpperCase('es');}
for(const letra of letrasAlfabeto){const b=nodo('button','',letra);b.type='button';b.dataset.letra=letra;b.addEventListener('click',()=>{inicialSeleccionada=inicialSeleccionada===letra?'':letra;mostrarArtistas();if(inicialSeleccionada&&inicialSeleccionada!=='#'){const caja=[...contenedor.querySelectorAll('.artista-mejor')].find(x=>normalizarNombre(x.querySelector('h2')?.textContent).startsWith(inicialSeleccionada));if(caja)caja.scrollIntoView({behavior:'smooth',block:'start'});}});alfabetoLoMejor.appendChild(b);}
window.addEventListener('scroll',()=>{const cajas=[...contenedor.querySelectorAll('.artista-mejor')];let actual='';for(const caja of cajas){if(caja.getBoundingClientRect().top<=180)actual=normalizarNombre(caja.querySelector('h2')?.textContent).charAt(0)||'';else break;}if(!actual&&cajas.length)actual=normalizarNombre(cajas[0].querySelector('h2')?.textContent).charAt(0)||'';letraActual.hidden=!actual;if(actual){letraActual.textContent=actual;for(const b of alfabetoLoMejor.querySelectorAll('button'))b.classList.toggle('activa',b.dataset.letra===actual);}});
const cacheGemini=new Map();
async function consultarGemini(tipo,nombre,artista){
 const clave=[tipo,normalizarNombre(nombre),normalizarNombre(artista||'')].join('|');
 if(!cacheGemini.has(clave)){
  cacheGemini.set(clave,(async()=>{
   try{
    const q=new URLSearchParams({tipo,nombre,artista:artista||''});
    const r=await fetch('/api/resumen-musical?'+q.toString(),{cache:'no-store',signal:AbortSignal.timeout(45000)});
    const d=await r.json();
    if(!r.ok||!d.encontrado||!d.resumen)return {encontrado:false,mensaje:d.error||'No se ha encontrado información en español para este resultado.'};
    return d;
   }catch(e){return {encontrado:false,mensaje:'No se ha podido cargar la información ahora mismo. Inténtalo de nuevo.'};}
  })());
 }
 const resultado=await cacheGemini.get(clave);
 if(!resultado.encontrado)cacheGemini.delete(clave);
 return resultado;
}
function mostrarInfoWikipedia(contenedor,info,tipo){
 let modal=document.getElementById('modal-info-musical');
 if(!modal){
  modal=nodo('div','');modal.id='modal-info-musical';modal.hidden=true;
  modal.style.cssText='position:fixed;inset:0;z-index:50000;background:#000b;display:flex;align-items:center;justify-content:center;padding:16px';
  const caja=nodo('section','');caja.style.cssText='width:min(680px,100%);max-height:85vh;overflow:auto;background:#171b29;color:#fff;border:1px solid #ffffff35;border-radius:16px;padding:20px;box-shadow:0 18px 60px #0009';
  const cabecera=nodo('div','');cabecera.style.cssText='display:flex;align-items:center;justify-content:space-between;gap:12px';
  const titulo=nodo('h2','','Información musical');titulo.id='titulo-modal-info-musical';titulo.style.margin='0';
  const cerrar=nodo('button','','Cerrar ✕');cerrar.type='button';cerrar.addEventListener('click',()=>{modal.hidden=true;if(modal._boton)modal._boton.focus();});
  cabecera.append(titulo,cerrar);
  const cuerpo=nodo('div','');cuerpo.id='contenido-modal-info-musical';cuerpo.style.cssText='line-height:1.65;margin-top:14px';
  caja.append(cabecera,cuerpo);modal.appendChild(caja);
  modal.addEventListener('click',e=>{if(e.target===modal){modal.hidden=true;if(modal._boton)modal._boton.focus();}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden){modal.hidden=true;if(modal._boton)modal._boton.focus();}});
  document.body.appendChild(modal);
 }
 document.getElementById('titulo-modal-info-musical').textContent=(tipo==='artista'?'Biografía de ':'Sobre la canción: ')+(info.nombre||info.titulo||'Información musical');
 const cuerpo=document.getElementById('contenido-modal-info-musical');cuerpo.replaceChildren();
 const motor=String(info.motor||info.fuente_tipo||'').toLowerCase();
 let etiqueta='';
 if(motor==='gemini'||motor==='google') etiqueta='✨ Información generada por Gemini (sin búsqueda web)';
 else if(motor==='groq') etiqueta='⚡ Información generada por Groq (alternativa a Gemini)';
 else if(motor==='web'||motor==='wikipedia') etiqueta='🌐 Información consultada en la web';
 else etiqueta='Información musical generada automáticamente';
 const atribucion=nodo('p','atribucion-motor',etiqueta);
 atribucion.style.cssText='margin:0 0 12px;color:#c9b0ff;font-size:0.9em;font-weight:700';
 cuerpo.appendChild(atribucion);
 const p=nodo('p','',info.resumen||'');p.style.whiteSpace='pre-line';cuerpo.appendChild(p);
 const fuentesValidas=(info.fuentes||[]).filter(f=>f.url&&String(f.url).startsWith('https://'));
 if(motor==='gemini'&&!fuentesValidas.length){
  const avisoFuentes=nodo('p','','Gemini no ha proporcionado enlaces de fuentes para esta ficha.');
  avisoFuentes.style.cssText='margin-top:12px;color:#c5c8d3;font-size:0.9em';
  cuerpo.appendChild(avisoFuentes);
 }
 if(info.aviso_gemini){const aviso=nodo('p','',String(info.aviso_gemini));aviso.style.cssText='margin-top:14px;padding:10px;border-radius:8px;background:#5b3b162e;color:#ffd9a3;font-size:0.92em';cuerpo.appendChild(aviso);}
 fuentesValidas.forEach(f=>{const a=nodo('a','','Fuente: '+(f.titulo||f.url)+' ↗');a.href=f.url;a.target='_blank';a.rel='noopener noreferrer';a.style.cssText='display:block;margin-top:8px;color:#c9b0ff;font-weight:700';cuerpo.appendChild(a);});
 modal._boton=contenedor.querySelector('button.boton-wikipedia')||null;modal.hidden=false;
}
let audioActivo=null;
let temporizador=null;
function nodo(tag,clase,texto){const n=document.createElement(tag);if(clase)n.className=clase;if(texto!==undefined)n.textContent=texto;return n;}
function mostrarArtistas(){
 const q=buscar.value.trim().toLocaleLowerCase('es');
 const filtrados=artistasBase.filter(a=>{const nombre=a.NombreOriginal||a.NombreNormalizado||'',ini=normalizarNombre(nombre).charAt(0)||'#';const coincide=!inicialSeleccionada||(inicialSeleccionada==='#'?!/^[A-Z]/.test(normalizarNombre(nombre)):ini===inicialSeleccionada);return nombre.toLocaleLowerCase('es').includes(q)&&coincide;}).sort((a,b)=>mostrandoFavoritos?((Number(b.cancionesEnColeccion)||0)-(Number(a.cancionesEnColeccion)||0)||(a.NombreOriginal||a.NombreNormalizado||'').localeCompare(b.NombreOriginal||b.NombreNormalizado||'','es',{sensitivity:'base'})):(a.NombreOriginal||a.NombreNormalizado||'').localeCompare(b.NombreOriginal||b.NombreNormalizado||'','es',{sensitivity:'base'}));
 contenedor.replaceChildren();
 for(const artista of filtrados){
  const nombre=artista.NombreOriginal||artista.NombreNormalizado;
  const caja=nodo('section','artista-mejor');
  const cabecera=nodo('div','cabecera-artista');
  cabecera.appendChild(nodo('h2','',nombre+(artista.cancionesEnColeccion?' · '+artista.cancionesEnColeccion+' canciones':'')));
  const huecoWiki=nodo('span','');huecoWiki.style.marginRight='auto';
  const wikiArtista=nodo('button','boton-wikipedia','I');wikiArtista.type='button';
  wikiArtista.dataset.resumenTipo='artista';wikiArtista.dataset.resumenNombre=nombre;wikiArtista.dataset.resumenArtista='';
  wikiArtista.title='Consultar biografía y curiosidad de '+nombre;wikiArtista.setAttribute('aria-label','Consultar biografía de '+nombre);
  wikiArtista.addEventListener('click',async()=>{
   if(wikiArtista.disabled)return;wikiArtista.disabled=true;wikiArtista.textContent='…';
   let infoBox=caja.querySelector('.info-wikipedia');if(infoBox)infoBox.remove();
   const cargando=nodo('div','info-wikipedia','Buscando información en español…');caja.appendChild(cargando);
   try{
    const info=await consultarGemini('artista',nombre,'');
    cargando.remove();
    if(info.encontrado)mostrarInfoWikipedia(caja,info,'artista');
    else caja.appendChild(nodo('div','info-wikipedia',info.mensaje||'No se ha encontrado información sobre este artista.'));
   }finally{wikiArtista.disabled=false;wikiArtista.textContent='I';}
  });
  huecoWiki.appendChild(wikiArtista);cabecera.appendChild(huecoWiki);
  const botonesRanking=nodo('div','botones-ranking');
  const boton=nodo('button','boton-populares','⭐ Más populares (20)');
  boton.addEventListener('click',()=>cargarTop(nombre,caja,boton,'populares'));
  const botonRecientes=nodo('button','boton-recientes','🆕 Éxitos recientes (5)');
  botonRecientes.addEventListener('click',()=>cargarTop(nombre,caja,botonRecientes,'recientes'));
  const botonPublicaciones=nodo('button','boton-publicaciones','💿 Últimas publicaciones');
  botonPublicaciones.addEventListener('click',()=>cargarPublicacionesLoMejor(nombre,caja,botonPublicaciones));
  botonesRanking.append(boton,botonRecientes,botonPublicaciones);
  cabecera.appendChild(botonesRanking);
  caja.appendChild(cabecera);
  const canciones=nodo('div','canciones-artista canciones-populares');
  canciones.hidden=true;
  caja.appendChild(canciones);
  const recientes=nodo('div','canciones-artista canciones-recientes');
  recientes.hidden=true;
  caja.appendChild(recientes);
  const publicaciones=nodo('div','canciones-artista canciones-publicaciones');
  publicaciones.hidden=true;
  caja.appendChild(publicaciones);
  contenedor.appendChild(caja);
 }
 estado.textContent=filtrados.length+' artistas. Pulsa «Ver sus 20 canciones» para consultar su ranking.';for(const b of alfabetoLoMejor.querySelectorAll('button'))b.classList.toggle('activa',b.dataset.letra===inicialSeleccionada);
}
async function cargarPublicacionesLoMejor(nombre,caja,boton){
 const zona=caja.querySelector('.canciones-publicaciones');
 if(!zona)return;
 if(!zona.hidden&&zona.dataset.cargado==='1'){zona.hidden=true;boton.textContent='💿 Últimas publicaciones';return;}
 zona.hidden=false;
 if(zona.dataset.cargado==='1'){boton.textContent='Ocultar últimas publicaciones';return;}
 zona.replaceChildren();boton.disabled=true;boton.textContent='Consultando publicaciones…';
 try{
  const r=await fetch('/api/publicaciones/'+encodeURIComponent(nombre),{cache:'no-store'});
  const datos=await r.json();
  if(!r.ok)throw new Error(datos.error||'No se han podido cargar las publicaciones.');
  zona.appendChild(nodo('h3','','Últimas publicaciones de '+(datos.artista||nombre)+' ('+(datos.total||0)+' registradas)'));
  const publicaciones=Array.isArray(datos.publicaciones)?datos.publicaciones:[];
  if(!publicaciones.length)zona.appendChild(nodo('p','mensaje-pista','No hay publicaciones registradas para este artista.'));
  for(const p of publicaciones){
   const item=nodo('div','publicacion-mejor');
   item.appendChild(nodo('strong','',p.titulo||'Sin título'));
   const meta=[p.fecha,p.tipo].filter(Boolean).join(' · ');
   if(meta)item.appendChild(nodo('small','',meta));
   zona.appendChild(item);
  }
  zona.dataset.cargado='1';boton.textContent='Ocultar últimas publicaciones';
 }catch(e){
  zona.appendChild(nodo('p','mensaje-pista',e.message||'No se han podido cargar las publicaciones.'));
  boton.textContent='Reintentar últimas publicaciones';
 }finally{boton.disabled=false;}
}
async function cargarTop(nombre,caja,boton,tipo='populares'){
 const recientes=tipo==='recientes';
 const zona=caja.querySelector(recientes?'.canciones-recientes':'.canciones-populares');
 const etiqueta=recientes?'🆕 Éxitos recientes (5)':'⭐ Más populares (20)';
 const etiquetaOcultar=recientes?'Ocultar éxitos recientes':'Ocultar canciones populares';
 const etiquetaReintentar=recientes?'Reintentar éxitos recientes':'Reintentar canciones populares';
 if(!zona.hidden&&boton.dataset.error!=='1'){zona.hidden=true;boton.textContent=etiqueta;return;}
 zona.hidden=false;
 if(zona.dataset.cargado==='1'){boton.textContent=etiquetaOcultar;return;}
 zona.replaceChildren();boton.disabled=true;boton.textContent='Consultando Deezer…';
 const controlador=new AbortController();
 const limite=setTimeout(()=>controlador.abort(),30000);
 let correcto=false;
 try{
  const parametros=new URLSearchParams({artista:nombre,tipo});
  const r=await fetch('/api/lo-mejor?'+parametros.toString(),{cache:'no-store',signal:controlador.signal});
  let d;
  try{d=await r.json();}catch(_){throw new Error('La consulta musical ha devuelto una respuesta no válida. Inténtalo de nuevo.');}
  if(!r.ok)throw new Error(d.error||'No se ha podido cargar el ranking.');
  if(!Array.isArray(d.canciones)||!d.canciones.length)throw new Error('Deezer no ha devuelto canciones para este artista.');
  for(const pista of d.canciones){
   const fila=nodo('div','pista');
   const detalle=nodo('div','');
   const tituloPista=nodo('span','pista-titulo',pista.titulo);
   const tituloLinea=nodo('div','');tituloLinea.appendChild(tituloPista);detalle.appendChild(tituloLinea);
   const wiki=nodo('button','boton-wikipedia','G');wiki.type='button';
   wiki.dataset.resumenTipo='cancion';wiki.dataset.resumenNombre=pista.titulo;wiki.dataset.resumenArtista=pista.artista;
   wiki.title='Consultar información de '+pista.titulo+' de '+pista.artista;
   wiki.setAttribute('aria-label','Consultar información sobre '+pista.titulo+' de '+pista.artista);
   wiki.addEventListener('click',async()=>{
    if(wiki.disabled)return;wiki.disabled=true;wiki.textContent='…';
    let infoBox=fila.querySelector('.info-wikipedia');if(infoBox)infoBox.remove();
    const cargando=nodo('div','info-wikipedia','Buscando información de la canción…');fila.insertAdjacentElement('afterend',cargando);
    try{
     const info=await consultarGemini('cancion',pista.titulo,pista.artista);
     cargando.remove();
     if(info.encontrado)mostrarInfoWikipedia(fila,info,'cancion');
     else fila.insertAdjacentElement('afterend',nodo('div','info-wikipedia',info.mensaje||'No se ha encontrado información sobre esta canción.'));
    }finally{wiki.disabled=false;wiki.textContent='I';}
   });
   tituloLinea.appendChild(wiki);
   const descripcion=recientes?'Lanzamiento reciente entre los temas destacados de Deezer':'Popularidad en Deezer';
   detalle.appendChild(nodo('div','pista-meta',(pista.anio||'Año no disponible')+' · '+pista.artista+' · '+descripcion+(pista.album?' · '+pista.album:'')));
   const acciones=nodo('div','acciones-pista');
   const muestra=nodo('button','boton-30','');muestra.innerHTML='<svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" focusable="false"><path d="M8 5.5v13l10-6.5z" fill="currentColor"/></svg><span>30 s</span>';
   muestra.title=pista.preview?'Reproducir muestra de 30 segundos':'Muestra de 30 segundos no disponible';
   muestra.disabled=!pista.preview;
   muestra.addEventListener('click',()=>reproducir(pista,muestra));
   const mediahuman=nodo('button','boton-mediahuman','');mediahuman.innerHTML='<svg aria-hidden="true" viewBox="0 0 24 24" width="21" height="21" focusable="false"><path d="M12 3v11m-5-5 5 5 5-5M4 17v3h16v-3" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
   mediahuman.title='Buscar enlace para MediaHuman';
   mediahuman.setAttribute('aria-label','MediaHuman');
   mediahuman.addEventListener('click',()=>buscarYouTube(pista,'mediahuman'));
   const youtube=nodo('button','boton-youtube','');youtube.innerHTML='<svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" focusable="false"><path d="M8 5.5v13l10-6.5z" fill="currentColor"/></svg>';
   youtube.title='Abrir opciones de YouTube';
   youtube.setAttribute('aria-label','YouTube');
   youtube.addEventListener('click',()=>buscarYouTube(pista,'youtube'));
   acciones.append(muestra,mediahuman,youtube);fila.append(detalle,acciones);zona.appendChild(fila);
  }
  zona.dataset.cargado='1';
  zona.dataset.error='0';
  correcto=true;
 }catch(e){
  zona.dataset.error='1';
  const mensaje=e.name==='AbortError'?'Deezer está tardando demasiado en responder. Inténtalo otra vez.':(e.message||'Error al consultar Deezer.');
  zona.appendChild(nodo('div','mensaje-pista',mensaje));
  boton.textContent=etiquetaReintentar;
 }finally{
  clearTimeout(limite);boton.disabled=false;
  if(correcto)boton.textContent=etiquetaOcultar;
 }
}
function reproducir(pista,boton){
 if(audioActivo){audioActivo.pause();audioActivo.currentTime=0;audioActivo=null;}
 if(temporizador)clearTimeout(temporizador);
 const audio=new Audio(pista.preview);audio.preload='none';audioActivo=audio;
 boton.disabled=true;audio.play().then(()=>{
  temporizador=setTimeout(()=>{if(audioActivo===audio){audio.pause();audio.currentTime=0;audioActivo=null;}boton.disabled=false;},30000);
 }).catch(()=>{boton.disabled=false;estado.textContent='No se ha podido reproducir la muestra de esta canción.';});
 audio.addEventListener('ended',()=>{if(temporizador)clearTimeout(temporizador);boton.disabled=false;if(audioActivo===audio)audioActivo=null;},{once:true});
}
async function buscarYouTube(pista,modo='mediahuman'){
 if(modo==='full'){
  modal.hidden=false;resultadosYoutube.replaceChildren();reproductorCompleto.replaceChildren();document.getElementById('titulo-modal-youtube').textContent='Audio completo';estadoYoutube.textContent='Buscando una versión de audio en Audius…';
  try{
   const r=await fetch('/api/audius/buscar?'+new URLSearchParams({titulo:pista.titulo,artista:pista.artista})),d=await r.json();
   if(!r.ok)throw new Error(d.error||'No se ha podido buscar en Audius.');
   const p=(d.resultados||[])[0];if(!p)throw new Error('Audius no ha encontrado una coincidencia para esta canción.');
   const texto=nodo('p','','Audio de Audius: '+p.titulo+' · '+p.artista);reproductorCompleto.appendChild(texto);
   const audio=document.createElement('audio');audio.controls=true;audio.preload='none';audio.src=p.streamUrl;audio.style.width='100%';reproductorCompleto.appendChild(audio);
   if(p.url){const a=nodo('a','','Abrir pista en Audius');a.href=p.url;a.target='_blank';a.rel='noopener noreferrer';reproductorCompleto.appendChild(a);}
   estadoYoutube.textContent='Encontrada una pista en Audius. Pulsa reproducir si el audio no empieza automáticamente.';
   try{await audio.play();}catch(e){}
  }catch(e){estadoYoutube.textContent=e.message||'No se ha podido encontrar audio en Audius.';const a=nodo('a','','Buscar esta canción en Audius');a.href='https://audius.co/search/'+encodeURIComponent(pista.artista+' '+pista.titulo);a.target='_blank';a.rel='noopener noreferrer';resultadosYoutube.appendChild(a);}
  return;
 }
 modal.hidden=false;resultadosYoutube.replaceChildren();reproductorCompleto.replaceChildren();
 estadoYoutube.textContent='Buscando versiones disponibles…';
 try{
  const r=await fetch('/api/youtube/buscar?'+new URLSearchParams({titulo:pista.titulo,artista:pista.artista}));
  const d=await r.json();if(!r.ok)throw new Error(d.error||'No se encontraron vídeos.');
  if(modo==='full'){
   const video=(d.resultados||[])[0];
   if(!video){estadoYoutube.textContent='No se encontró una versión para reproducir.';return;}
   const match=String(video.url||'').match(/[?&]v=([^&]+)/);
   if(!match){estadoYoutube.textContent='No se pudo identificar el vídeo.';return;}
   document.getElementById('titulo-modal-youtube').textContent='Reproduciendo canción completa';
   const iframe=document.createElement('iframe');iframe.className='reproductor-completo';iframe.title='Reproductor de canción completa';
   iframe.src='https://www.youtube-nocookie.com/embed/'+encodeURIComponent(match[1])+'?autoplay=1&rel=0';
   iframe.allow='autoplay; encrypted-media; picture-in-picture; fullscreen';iframe.allowFullscreen=true;
   reproductorCompleto.replaceChildren(iframe);
   estadoYoutube.textContent='Reproduciendo automáticamente: '+(video.titulo||pista.titulo)+' · '+(video.canal||pista.artista)+'.';
   return;
  }
  if(modo==='mediahuman')estadoYoutube.textContent='Elige una versión para copiar su enlace y pegarlo en MediaHuman.';
  else estadoYoutube.textContent='Elige una versión para abrirla en YouTube.';
  for(const video of d.resultados||[]){
   const b=nodo('button','resultado-youtube');
   b.appendChild(nodo('strong','',video.titulo));b.appendChild(nodo('span','',video.canal));
   b.addEventListener('click',async()=>{
    if(modo==='youtube'){
     window.open(video.url,'_blank','noopener,noreferrer');
    }else if(modo==='full'){
     const match=video.url.match(/[?&]v=([^&]+)/);
     if(!match){estadoYoutube.textContent='No se pudo obtener el identificador del vídeo.';return;}
     reproductorCompleto.replaceChildren();
     const iframe=document.createElement('iframe');
     iframe.className='reproductor-completo';iframe.title='Reproductor de canción completa';
     iframe.src='https://www.youtube-nocookie.com/embed/'+encodeURIComponent(match[1])+'?autoplay=1&rel=0';
     iframe.allow='autoplay; encrypted-media; picture-in-picture; fullscreen';
     iframe.allowFullscreen=true;
     reproductorCompleto.appendChild(iframe);
     estadoYoutube.textContent='Reproduciendo dentro de Mi Radar Musical si el vídeo permite reproducción integrada.';
    }else{
     try{await navigator.clipboard.writeText(video.url);estadoYoutube.textContent='Enlace copiado. Pégalo en MediaHuman.';b.appendChild(nodo('span','','✓ Enlace copiado'));}
     catch(e){window.prompt('Copia el enlace para MediaHuman:',video.url);}
    }
   });
   resultadosYoutube.appendChild(b);
  }
 }catch(e){estadoYoutube.textContent=e.message||'No se pudo buscar en YouTube.';}
}
document.getElementById('cerrar-modal').addEventListener('click',()=>modal.hidden=true);
modal.addEventListener('click',e=>{if(e.target===modal)modal.hidden=true;});
document.addEventListener('keydown',e=>{if(e.key==='Escape')modal.hidden=true;});
buscar.addEventListener('input',mostrarArtistas);
fetch('/api/artistas',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(datos=>{artistas=datos;artistasBase=artistas;mostrarArtistas();}).catch(()=>{estado.textContent='No se ha podido cargar la lista de artistas.';});
</script></body></html>"""


@app.get("/api/lo-mejor/artistas")
def api_lo_mejor_artistas():
    """Devuelve los 20 artistas con más canciones distintas en la colección local."""
    ruta = BASE / "mi_musica.json"
    try:
        with ruta.open("r", encoding="utf-8") as archivo:
            biblioteca = json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return jsonify({"error": "No se ha podido leer tu colección musical."}), 500
    grupos = {}
    vistos = set()
    for pista in biblioteca if isinstance(biblioteca, list) else []:
        artista = str(pista.get("artista") or "").strip()
        titulo = str(pista.get("titulo") or "").strip()
        if not artista or not titulo:
            continue
        clave_artista = normalizar_texto(artista)
        clave_pista = (clave_artista, normalizar_texto(titulo))
        if clave_pista in vistos:
            continue
        vistos.add(clave_pista)
        if clave_artista not in grupos:
            grupos[clave_artista] = {"NombreOriginal": artista, "NombreNormalizado": artista, "cancionesEnColeccion": 0}
        grupos[clave_artista]["cancionesEnColeccion"] += 1
    top = sorted(grupos.values(), key=lambda a: (-a["cancionesEnColeccion"], a["NombreOriginal"].casefold()))[:20]
    return jsonify(top)


@app.get("/api/lo-mejor")
def api_lo_mejor():
    nombre_solicitado = (request.args.get("artista") or "").strip()
    tipo = (request.args.get("tipo") or "populares").strip().lower()
    if not nombre_solicitado:
        return jsonify({"error": "Falta el nombre del artista."}), 400
    if tipo not in ("populares", "recientes"):
        return jsonify({"error": "Tipo de ranking no válido."}), 400

    try:
        parametros = urlencode({"q": nombre_solicitado, "limit": 10})
        peticion = Request(
            "https://api.deezer.com/search/artist?" + parametros,
            headers={"User-Agent": "MiRadarMusical/1.0"}
        )
        with urlopen(peticion, timeout=4) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        if datos.get("error"):
            raise ValueError("Deezer no ha permitido consultar su catálogo.")

        candidatos = datos.get("data", [])
        objetivo = normalizar_texto(nombre_solicitado)
        mejor = None
        puntuacion_mejor = 0.0
        for candidato in candidatos:
            nombre = candidato.get("name") or ""
            puntuacion = difflib.SequenceMatcher(
                None, objetivo, normalizar_texto(nombre)
            ).ratio()
            if puntuacion > puntuacion_mejor:
                puntuacion_mejor = puntuacion
                mejor = candidato

        if not mejor or puntuacion_mejor < 0.86:
            return jsonify({
                "error": "No he encontrado una coincidencia suficientemente segura para este artista en Deezer."
            }), 404

        # Preferir coincidencia exacta del artista al resolver el nombre solicitado.
        coincidencia_exacta = next(
            (c for c in candidatos
             if normalizar_texto(c.get("name", "")) == objetivo),
            None
        )
        if coincidencia_exacta:
            mejor = coincidencia_exacta

        nombre_deezer = mejor.get("name", nombre_solicitado)
        pistas_top = []
        # El endpoint /top puede devolver error o lista vacía según artista/región.
        # En ambos casos, pasar a búsqueda de pistas en vez de abortar toda la ficha.
        url_top = "https://api.deezer.com/artist/" + str(int(mejor["id"])) + "/top?" + urlencode({"limit": 50})
        try:
            peticion_top = Request(url_top, headers={"User-Agent": "MiRadarMusical/1.0"})
            with urlopen(peticion_top, timeout=3) as respuesta:
                datos_top = json.loads(respuesta.read().decode("utf-8"))
            if not datos_top.get("error"):
                pistas_top = (datos_top.get("data") or [])
        except Exception:
            # El fallback de búsqueda libre puede seguir funcionando aunque falle /top.
            pistas_top = []

        if not pistas_top:
            # No usar el filtro avanzado artist:"...": puede devolver falsos vacíos.
            consulta_pistas = urlencode({"q": nombre_deezer, "limit": 100})
            peticion_pistas = Request(
                "https://api.deezer.com/search/track?" + consulta_pistas,
                headers={"User-Agent": "MiRadarMusical/1.0"}
            )
            with urlopen(peticion_pistas, timeout=3) as respuesta:
                datos_pistas = json.loads(respuesta.read().decode("utf-8"))
            if datos_pistas.get("error"):
                raise ValueError("Deezer no ha permitido buscar canciones de este artista.")

            pistas_busqueda = datos_pistas.get("data") or []
            objetivo_artista = normalizar_texto(nombre_deezer)
            id_artista = str(mejor.get("id", ""))
            pistas_top = [
                pista for pista in pistas_busqueda
                if (
                    id_artista and str((pista.get("artist") or {}).get("id", "")) == id_artista
                ) or (
                    normalizar_texto((pista.get("artist") or {}).get("name", "")) == objetivo_artista
                )
            ]
            pistas_top.sort(key=lambda pista: int(pista.get("rank") or 0), reverse=True)
            pistas_top = pistas_top[:50]

        biblioteca = []
        try:
            with (BASE / "mi_musica.json").open("r", encoding="utf-8") as archivo:
                biblioteca = json.load(archivo)
        except (OSError, json.JSONDecodeError):
            biblioteca = []
        anios_locales = {}
        for local in biblioteca if isinstance(biblioteca, list) else []:
            if normalizar_texto(local.get("artista")) == normalizar_texto(nombre_deezer):
                anio_local = local.get("anio")
                if anio_local:
                    anios_locales[normalizar_texto(local.get("titulo"))] = anio_local

        canciones = []
        vistos = set()
        for pista in pistas_top:
            titulo = pista.get("title") or "Sin título"
            clave_titulo = normalizar_texto(titulo)
            if clave_titulo in vistos:
                continue
            vistos.add(clave_titulo)
            artista_pista = (pista.get("artist") or {}).get("name") or mejor.get("name", nombre_solicitado)
            album = pista.get("album") or {}
            fecha = str(pista.get("release_date") or album.get("release_date") or "")
            anio = fecha[:4] if len(fecha) >= 4 and fecha[:4].isdigit() else anios_locales.get(clave_titulo)
            canciones.append({
                "titulo": titulo,
                "artista": artista_pista,
                "album": album.get("title") or "",
                "preview": pista.get("preview") or "",
                "url": pista.get("link") or "",
                "rank": pista.get("rank"),
                "anio": anio
            })
        if tipo == "recientes":
            # Seleccionar primero los temas destacados que tengan año verificable
            # y priorizar el lanzamiento más reciente; el ranking de Deezer desempata.
            canciones = [
                c for c in canciones
                if str(c.get("anio") or "").isdigit() and len(str(c.get("anio"))) == 4
            ]
            canciones.sort(
                key=lambda c: (int(c.get("anio") or 0), int(c.get("rank") or 0)),
                reverse=True
            )
            canciones = canciones[:5]
            mensaje_vacio = "Deezer no ha devuelto temas destacados con fecha de lanzamiento identificable para este artista."
        else:
            # Mantener el comportamiento actual: las 20 más populares,
            # ordenadas cronológicamente para facilitar la consulta por año.
            canciones.sort(key=lambda c: int(c.get("rank") or 0), reverse=True)
            canciones = canciones[:20]
            canciones.sort(key=lambda c: (int(c["anio"]) if str(c.get("anio") or "").isdigit() else 9999, -(int(c.get("rank") or 0))))
            mensaje_vacio = "Deezer no ha encontrado canciones para este artista en este momento. Prueba de nuevo más tarde."

        if not canciones:
            return jsonify({"error": mensaje_vacio}), 502

        return jsonify({
            "artista": mejor.get("name", nombre_solicitado),
            "fuente": "Deezer",
            "tipo": tipo,
            "canciones": canciones
        })
    except Exception:
        return jsonify({
            "error": "No se ha podido consultar Deezer ahora mismo. Inténtalo de nuevo más tarde."
        }), 502



@app.get("/recomendaciones")
def pagina_recomendaciones():
    return (BASE / "recomendaciones.html").read_text(encoding="utf-8")


@app.get("/api/recomendaciones")
def api_recomendaciones():
    """Recomienda temas ajenos a la biblioteca a partir de los artistas más representados."""
    genero_solicitado = (request.args.get("genero") or "").strip()
    try:
        inicio = max(0, min(int(request.args.get("inicio") or 0), 500))
    except (TypeError, ValueError):
        inicio = 0

    ruta_biblioteca = BASE / "mi_musica.json"
    try:
        with ruta_biblioteca.open("r", encoding="utf-8") as archivo:
            biblioteca = json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return jsonify({"error": "No se ha podido leer tu biblioteca musical."}), 503
    if not isinstance(biblioteca, list) or not biblioteca:
        return jsonify({"error": "Tu biblioteca está vacía o no está disponible todavía."}), 503

    def clave(valor):
        return normalizar_texto(valor)

    existentes = set()
    artistas = {}
    generos_por_artista = {}
    for pista in biblioteca:
        if not isinstance(pista, dict):
            continue
        artista = str(pista.get("artista") or "").strip()
        titulo = str(pista.get("titulo") or "").strip()
        genero = str(pista.get("genero") or "").strip()
        if artista and titulo:
            existentes.add((clave(artista), clave(titulo)))
        if artista:
            entrada = artistas.setdefault(clave(artista), {"nombre": artista, "total": 0, "generos": {}})
            entrada["total"] += 1
            if genero:
                entrada["generos"][genero] = entrada["generos"].get(genero, 0) + 1
                generos_por_artista.setdefault(clave(artista), {})
                generos_por_artista[clave(artista)][genero] = generos_por_artista[clave(artista)].get(genero, 0) + 1

    generos = sorted({g for p in biblioteca if isinstance(p, dict) for g in [str(p.get("genero") or "").strip()] if g}, key=str.casefold)
    semillas = sorted(artistas.values(), key=lambda a: (-a["total"], a["nombre"].casefold()))
    if genero_solicitado:
        semillas = [a for a in semillas if a["generos"] and max(a["generos"], key=a["generos"].get).casefold() == genero_solicitado.casefold()]
    semillas = semillas[:8]
    if not semillas:
        return jsonify({"canciones": [], "generos": generos, "total_biblioteca": len(biblioteca),
                        "error": "No hay suficientes artistas en tu colección para ese género."}), 200

    candidatos = {}
    cache_peticion = {}
    def consultar(url, timeout=4):
        if url in cache_peticion:
            return cache_peticion[url]
        try:
            pet = Request(url, headers={"User-Agent": "MiRadarMusical/1.0"})
            with urlopen(pet, timeout=timeout) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
            if isinstance(datos, dict) and not datos.get("error"):
                cache_peticion[url] = datos
                return datos
        except Exception as error:
            app.logger.info("Recomendaciones: fallo consultando catálogo: %s", error)
        cache_peticion[url] = {}
        return {}

    for semilla in semillas:
        q = urlencode({"q": semilla["nombre"], "limit": 8})
        datos_artista = consultar("https://api.deezer.com/search/artist?" + q)
        objetivo = clave(semilla["nombre"])
        artistas_deezer = datos_artista.get("data") or []
        if not artistas_deezer:
            continue
        coincidencia = next((a for a in artistas_deezer if clave(a.get("name")) == objetivo), None)
        if not coincidencia:
            coincidencia = max(artistas_deezer, key=lambda a: difflib.SequenceMatcher(None, objetivo, clave(a.get("name"))).ratio())
            if difflib.SequenceMatcher(None, objetivo, clave(coincidencia.get("name"))).ratio() < 0.82:
                continue
        id_artista = coincidencia.get("id")
        relacionados = consultar("https://api.deezer.com/artist/" + str(id_artista) + "/related?" + urlencode({"limit": 8})).get("data") or []
        # Si Deezer no proporciona artistas relacionados, usamos temas populares del artista semilla como alternativa.
        objetivos = [(a, 1.0) for a in relacionados[:8]]
        if not objetivos:
            objetivos = [(coincidencia, 0.55)]
        for artista_rel, peso in objetivos:
            id_rel = artista_rel.get("id")
            if not id_rel:
                continue
            top = consultar("https://api.deezer.com/artist/" + str(id_rel) + "/top?" + urlencode({"limit": 12})).get("data") or []
            for pista in top:
                titulo = str(pista.get("title") or "").strip()
                datos_artista_pista = pista.get("artist") or artista_rel
                nombre_artista = str(datos_artista_pista.get("name") or artista_rel.get("name") or "").strip()
                if not titulo or not nombre_artista or (clave(nombre_artista), clave(titulo)) in existentes:
                    continue
                album = pista.get("album") or {}
                llave = (clave(nombre_artista), clave(titulo))
                puntaje = peso * 100 + min(int(pista.get("rank") or 0) / 100000, 30)
                actual = candidatos.get(llave)
                if actual and actual["puntuacion"] >= puntaje:
                    continue
                candidatos[llave] = {
                    "titulo": titulo, "artista": nombre_artista,
                    "album": album.get("title") or "",
                    "portada": album.get("cover_medium") or album.get("cover") or "",
                    "preview": pista.get("preview") or "", "url": pista.get("link") or "",
                    "genero": genero_solicitado or (max(semilla["generos"], key=semilla["generos"].get) if semilla["generos"] else ""),
                    "relacionado_con": semilla["nombre"], "puntuacion": puntaje
                }

    ordenadas = sorted(candidatos.values(), key=lambda p: (-p["puntuacion"], clave(p["artista"]), clave(p["titulo"])))
    # Rota el orden de resultados al solicitar otras tandas, sin cambiar la exclusión de la colección.
    if ordenadas:
        inicio_real = inicio % len(ordenadas)
        ordenadas = ordenadas[inicio_real:] + ordenadas[:inicio_real]
    return jsonify({"canciones": ordenadas[:10], "generos": generos,
                    "total_candidatas": len(candidatos), "total_biblioteca": len(biblioteca),
                    "inicio": inicio, "fuente": "Deezer + tu biblioteca",
                    "aviso": "La similitud se estima por artistas relacionados y popularidad del catálogo; no es un análisis acústico de audio."})


@app.get("/mi-musica")
def pagina_mi_musica():
    return (BASE / "mimusica.html").read_text(encoding="utf-8")


@app.get("/api/mi-musica")
def api_mi_musica():
    ruta = BASE / "mi_musica.json"
    with ruta.open("r", encoding="utf-8") as archivo:
        return jsonify(json.load(archivo))


@app.get("/artistas")
def pagina_artistas():
    html = (BASE / "index.html").read_text(encoding="utf-8")
    return html.replace("</body>", BOTON_HTML + LIMPIAR_CONTROLES_HTML + "\n</body>")

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


@app.get("/api/audius/buscar")
def buscar_audio_audius():
    titulo = (request.args.get("titulo") or "").strip()
    artista = (request.args.get("artista") or "").strip()
    if not titulo or not artista:
        return jsonify({"error": "Falta el título o el artista."}), 400

    consulta = f"{titulo} {artista}"
    url = "https://api.audius.co/v1/tracks/search?" + urlencode({
        "query": consulta,
        "limit": 15,
        "app_name": "MiRadarMusical"
    })
    try:
        peticion = Request(
            url,
            headers={"User-Agent": "MiRadarMusical/1.0", "Accept": "application/json"}
        )
        with urlopen(peticion, timeout=12) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        pistas = datos.get("data", [])
        objetivo_titulo = normalizar_texto(titulo)
        objetivo_artista = normalizar_texto(artista)
        clasificadas = []
        for pista in pistas:
            id_pista = pista.get("id")
            titulo_pista = pista.get("title") or ""
            artista_pista = (pista.get("user") or {}).get("name") or pista.get("artist_name") or ""
            if not id_pista or not titulo_pista or not artista_pista:
                continue
            t = normalizar_texto(titulo_pista)
            a = normalizar_texto(artista_pista)
            sim_titulo = difflib.SequenceMatcher(None, objetivo_titulo, t).ratio()
            sim_artista = difflib.SequenceMatcher(None, objetivo_artista, a).ratio()
            if objetivo_titulo == t:
                sim_titulo = 1.0
            if objetivo_artista == a:
                sim_artista = 1.0
            puntuacion = sim_titulo * 0.65 + sim_artista * 0.35
            if objetivo_titulo and (objetivo_titulo in t or t in objetivo_titulo):
                puntuacion += 0.12
            if objetivo_artista and (objetivo_artista in a or a in objetivo_artista):
                puntuacion += 0.12
            if pista.get("duration", 0) >= 120:
                puntuacion += 0.02
            clasificadas.append({
                "id": str(id_pista),
                "titulo": titulo_pista,
                "artista": artista_pista,
                "duracion": pista.get("duration"),
                "url": pista.get("permalink") and ("https://audius.co" + pista.get("permalink")),
                "streamUrl": "https://api.audius.co/v1/tracks/" + str(id_pista) + "/stream?" + urlencode({"app_name": "MiRadarMusical"}),
                "puntuacion": puntuacion
            })
        clasificadas.sort(key=lambda x: x["puntuacion"], reverse=True)
        return jsonify({"resultados": clasificadas[:8], "fuente": "Audius"})
    except Exception:
        return jsonify({"error": "Audius no está disponible ahora o no tiene coincidencias para esta canción."}), 502


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

    # MusicBrainz puede devolver fechas con precisión distinta: YYYY, YYYY-MM
    # o YYYY-MM-DD. Comparamos sus componentes numéricos para que el orden
    # cronológico no dependa de una comparación textual de las fechas.
    def clave_fecha_publicacion(publicacion):
        fecha = str(publicacion.get("fecha") or "").strip()
        coincidencia = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", fecha)
        if not coincidencia:
            return (0, 0, 0, 0)
        anio, mes, dia = coincidencia.groups()
        return (1, int(anio), int(mes or 0), int(dia or 0))

    lista.sort(key=clave_fecha_publicacion, reverse=True)

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

        # La fecha solo cambia cuando detector y preparación del radar terminan bien.
        fecha_actualizacion = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%d/%m/%Y, %H:%M")
        (BASE / "ultima_actualizacion.txt").write_text(fecha_actualizacion, encoding="utf-8")
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



def _clave_resumen(tipo, nombre, artista=""):
    def normalizar(valor):
        valor = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode("ascii").upper()
        return re.sub(r"[^A-Z0-9]+", " ", valor).strip()
    return "|".join((tipo, normalizar(nombre), normalizar(artista)))


@app.get("/api/resumenes-disponibles")
def api_resumenes_disponibles():
    ruta = BASE / "resumenes_musicales.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        items = datos.get("items", {}) if isinstance(datos, dict) else {}
        claves = [
            k for k, v in items.items()
            if isinstance(v, dict) and v.get("encontrado") and len(str(v.get("resumen") or "").strip()) >= 100
            and str(v.get("fuente_tipo") or "").casefold() == "gemini"
        ]
        return jsonify({"claves": claves, "actualizado": datos.get("actualizado")})
    except (OSError, json.JSONDecodeError, AttributeError):
        return jsonify({"claves": [], "actualizado": None})



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
    """Genera una ficha en español con Gemini sin búsqueda web."""
    clave = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not clave:
        return None, "Falta configurar GEMINI_API_KEY en las variables de entorno del servicio."

    # Se usa generación de texto sin Google Search para evitar la cuota de búsqueda,
    # que no está disponible en el nivel gratuito para los modelos Gemini 3.x.
    modelo = "gemini-3.6-flash"
    entidad = f"la canción «{nombre}» de {artista}" if tipo == "cancion" else f"el artista «{nombre}»"
    if tipo == "artista":
        instrucciones = (
            "Escribe una biografía informativa y concreta en español que incluya, cuando lo sepas, "
            "su nombre real, fecha y lugar de nacimiento, comienzos, salto a la fama, principales "
            "éxitos, estilo musical, colaboraciones y evolución profesional. "
            "Termina con una curiosidad interesante y prudente."
        )
    else:
        instrucciones = (
            "Explica qué canción es, quién la compuso e interpreta, cuándo y en qué álbum se publicó "
            "si lo sabes, su estilo, contexto, recepción e impacto. Distingue la versión original "
            "de las versiones posteriores y termina con una curiosidad relevante si la conoces."
        )
    prompt = (
        f"Prepara una ficha musical útil sobre {entidad}. {instrucciones} "
        "Escribe en español natural entre 180 y 250 palabras. Organiza la respuesta con los "
        "encabezados «Biografía» (o «Sobre la canción») y «Curiosidad». "
        "No tienes búsqueda web disponible: usa solo datos de tu conocimiento general, no inventes "
        "fechas, cifras, anécdotas ni fuentes y omite los detalles de los que no estés seguro. "
        "Si no conoces una curiosidad fiable, indícalo en una sola frase y desarrolla el resto de la ficha. "
        "No incluyas enlaces ni digas que has consultado fuentes externas."
    )
    # La API Interactions es la vía recomendada para los modelos actuales de Gemini.
    # store=False evita que Google conserve esta consulta en el historial de interacciones.
    cuerpo = {
        "model": "gemini-3.6-flash",
        "input": prompt,
        "store": False,
        "generation_config": {"max_output_tokens": 2500, "thinking_level": "minimal"}
    }
    url = "https://generativelanguage.googleapis.com/v1beta/interactions"
    req = Request(
        url,
        data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": clave,
                 "User-Agent": "MiRadarMusical/1.0"},
        method="POST"
    )
    try:
        # Reintenta brevemente los errores 503 de saturación temporal de Google.
        respuesta = None
        for intento in range(3):
            try:
                with urlopen(req, timeout=45) as resp:
                    respuesta = json.loads(resp.read().decode("utf-8"))
                break
            except HTTPError as error:
                if error.code != 503 or intento == 2:
                    raise
                error.close()
                time.sleep(1 + intento * 2)
        if respuesta is None:
            return None, "Gemini no ha devuelto una respuesta. Inténtalo de nuevo."

        estado = str(respuesta.get("status") or "").lower()
        if estado == "incomplete":
            return None, "Gemini ha empezado la ficha, pero la respuesta ha quedado incompleta. Inténtalo de nuevo; no mostraremos una biografía cortada."
        if estado in ("failed", "cancelled"):
            return None, "Gemini no ha podido terminar la ficha. Inténtalo de nuevo."

        # La estructura de Interactions puede variar: extraemos todos los bloques de texto
        # sin depender de una única forma concreta de "steps" u "output".
        textos = []
        fuentes = []
        urls_vistas = set()

        def extraer_textos(obj):
            if isinstance(obj, dict):
                texto = obj.get("text")
                if isinstance(texto, str) and texto.strip():
                    textos.append(texto.strip())
                for clave_obj, valor_obj in obj.items():
                    if clave_obj not in ("text", "annotations"):
                        extraer_textos(valor_obj)
            elif isinstance(obj, list):
                for elemento in obj:
                    extraer_textos(elemento)

        extraer_textos(respuesta.get("steps") or respuesta.get("output") or [])
        resumen = "\n\n".join(dict.fromkeys(textos)).strip()
        if not resumen:
            resumen = str(respuesta.get("output_text") or "").strip()

        # Conserva enlaces anotados si el proveedor los incluye, aunque esta petición no usa búsqueda.
        def extraer_fuentes(obj):
            if isinstance(obj, dict):
                for anotacion in obj.get("annotations") or []:
                    if not isinstance(anotacion, dict):
                        continue
                    enlace = str(anotacion.get("url") or "").strip()
                    titulo = str(anotacion.get("title") or "Fuente consultada").strip()
                    if enlace.startswith("https://") and enlace not in urls_vistas:
                        urls_vistas.add(enlace)
                        fuentes.append({"titulo": titulo[:160], "url": enlace})
                for clave_obj, valor_obj in obj.items():
                    if clave_obj != "annotations":
                        extraer_fuentes(valor_obj)
            elif isinstance(obj, list):
                for elemento in obj:
                    extraer_fuentes(elemento)

        extraer_fuentes(respuesta)
        if not fuentes:
            # Algunas respuestas pueden incluir las anotaciones en la salida resumida.
            for bloque in respuesta.get("content") or []:
                if not isinstance(bloque, dict):
                    continue
                for anotacion in bloque.get("annotations") or []:
                    if not isinstance(anotacion, dict):
                        continue
                    enlace = str(anotacion.get("url") or "").strip()
                    titulo = str(anotacion.get("title") or "Fuente consultada").strip()
                    if enlace.startswith("https://") and enlace not in urls_vistas:
                        urls_vistas.add(enlace)
                        fuentes.append({"titulo": titulo[:160], "url": enlace})
                        if len(fuentes) >= 5:
                            break
        if len(resumen) < 80:
            return None, "Gemini no devolvió suficiente texto para crear la ficha. Inténtalo de nuevo."
        return ({
            "encontrado": True,
            "nombre": nombre,
            "titulo": nombre,
            "resumen": resumen[:7000],
            "biografia": resumen if tipo == "artista" else "",
            "informacion": resumen if tipo == "cancion" else "",
            "fuentes": fuentes,
            "fuente_tipo": "gemini",
            "fuente": "Gemini (sin búsqueda web)",
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
            mensaje = (
                "Google ha rechazado la consulta por cuota o límite (HTTP 429). "
                + (f"Detalle de Google: {detalle[:450]}" if detalle else "Google no ha enviado más detalles.")
            )
        elif error.code == 400:
            mensaje = "Gemini ha rechazado los parámetros de la petición (HTTP 400)."
            if detalle:
                mensaje += f" Detalle de Google: {detalle[:450]}"
        else:
            mensaje = f"Gemini devuelve HTTP {error.code}."
            if detalle:
                mensaje += f" Detalle de Google: {detalle[:450]}"
        app.logger.warning("%s Detalle API: %s", mensaje, detalle[:500])
        return None, mensaje
    except Exception as error:
        app.logger.warning("No se pudo consultar Gemini para %s: %s", nombre, error)
        return None, "No se ha podido conectar con Gemini en este momento."


def _buscar_groq_musical(tipo, nombre, artista=""):
    """Genera una ficha musical en español con Groq como alternativa a Gemini."""
    clave = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not clave:
        return None, "Gemini ha alcanzado su límite, pero falta configurar GROQ_API_KEY en Render."

    entidad = f"la canción «{nombre}» de {artista}" if tipo == "cancion" else f"el artista «{nombre}»"
    if tipo == "artista":
        instrucciones = (
            "Escribe una biografía informativa y concreta en español: comienzos, salto a la fama, "
            "éxitos, estilo musical, colaboraciones y evolución profesional cuando se conozcan. "
            "Termina con una curiosidad prudente si conoces una fiable."
        )
    else:
        instrucciones = (
            "Explica quién compuso e interpreta la canción, cuándo se publicó y en qué álbum si se sabe, "
            "su estilo, contexto, recepción e impacto. Distingue la versión original de versiones posteriores "
            "y termina con una curiosidad fiable si la conoces."
        )
    prompt = (
        f"Prepara una ficha musical útil sobre {entidad}. {instrucciones} "
        "Escribe en español natural entre 180 y 250 palabras. Usa los encabezados «Biografía» "
        "(o «Sobre la canción») y «Curiosidad». No inventes fechas, cifras, anécdotas ni fuentes; "
        "omite los detalles de los que no estés seguro. No incluyas enlaces ni afirmes haber consultado fuentes."
    )
    cuerpo = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": "Eres un asistente especializado en música. Responde en español y sé prudente con los datos no verificados."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4,
        "max_tokens": 1200
    }
    req = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + clave,
                 "User-Agent": "MiRadarMusical/1.0"},
        method="POST"
    )
    try:
        with urlopen(req, timeout=35) as resp:
            respuesta = json.loads(resp.read().decode("utf-8"))
        resumen = str((((respuesta.get("choices") or [{}])[0].get("message") or {}).get("content")) or "").strip()
        if len(resumen) < 80:
            return None, "Groq no ha devuelto suficiente texto para crear la ficha."
        return ({
            "encontrado": True,
            "nombre": nombre,
            "titulo": nombre,
            "resumen": resumen[:7000],
            "biografia": resumen if tipo == "artista" else "",
            "informacion": resumen if tipo == "cancion" else "",
            "fuentes": [],
            "fuente_tipo": "groq",
            "fuente": "Groq (alternativa automática a Gemini)",
            "motor": "groq",
            "aviso_gemini": "Gemini ha alcanzado su límite o cuota; esta ficha se ha generado automáticamente con Groq."
        }, None)
    except HTTPError as error:
        detalle = ""
        try:
            cuerpo_error = json.loads(error.read().decode("utf-8"))
            detalle = str((cuerpo_error.get("error") or {}).get("message") or "")
        except Exception:
            pass
        app.logger.warning("Groq devuelve HTTP %s: %s", error.code, detalle[:400])
        if error.code == 429:
            mensaje = "Groq también ha alcanzado su límite de uso. Inténtalo más tarde."
        elif error.code in (401, 403):
            mensaje = "Groq no acepta la clave API configurada en Render."
        else:
            mensaje = f"Groq devuelve HTTP {error.code}." + (f" {detalle[:300]}" if detalle else "")
        return None, mensaje
    except Exception as error:
        app.logger.warning("No se pudo consultar Groq para %s: %s", nombre, error)
        return None, "No se ha podido conectar con Groq en este momento."



_candado_cache_resumen = threading.Lock()

@app.get("/api/resumen-musical")
def api_resumen_musical():
    """Entrega solo fichas de Gemini y conserva las respuestas entre sesiones."""
    tipo = (request.args.get("tipo") or "").strip().lower()
    nombre = re.sub(r"\s+", " ", (request.args.get("nombre") or "").strip())[:180]
    artista = re.sub(r"\s+", " ", (request.args.get("artista") or "").strip())[:180]
    if tipo not in ("artista", "cancion") or not nombre or (tipo == "cancion" and not artista):
        return jsonify({"encontrado": False, "motor": "ninguno", "fuente_tipo": "ninguna",
                        "error": "Falta el artista o la canción."}), 400

    clave_cache = _clave_resumen(tipo, nombre, artista)
    ruta_cache = BASE / "resumenes_musicales.json"
    with _candado_cache_resumen:
        try:
            datos_cache = json.loads(ruta_cache.read_text(encoding="utf-8"))
            guardado = (datos_cache.get("items") or {}).get(clave_cache)
            if isinstance(guardado, dict) and guardado.get("encontrado") and guardado.get("fuente_tipo") in ("gemini", "groq"):
                return jsonify(guardado)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass

    resultado_gemini, error_gemini = _buscar_gemini_musical(tipo, nombre, artista)
    resultado_final = resultado_gemini
    error_final = error_gemini
    # El cambio automático a Groq se activa cuando Gemini devuelve HTTP 429 (cuota/límite).
    if not resultado_final and error_gemini and "HTTP 429" in error_gemini:
        resultado_final, error_groq = _buscar_groq_musical(tipo, nombre, artista)
        if not resultado_final:
            error_final = (error_gemini + " " + (error_groq or "")).strip()

    if resultado_final:
        with _candado_cache_resumen:
            try:
                datos_cache = json.loads(ruta_cache.read_text(encoding="utf-8"))
                if not isinstance(datos_cache, dict):
                    datos_cache = {"items": {}}
            except (OSError, json.JSONDecodeError):
                datos_cache = {"items": {}}
            if not isinstance(datos_cache.get("items"), dict):
                datos_cache["items"] = {}
            datos_cache["items"][clave_cache] = resultado_final
            datos_cache["actualizado"] = datetime.now(ZoneInfo("Europe/Madrid")).isoformat()
            temporal = ruta_cache.with_suffix(".tmp")
            try:
                temporal.write_text(json.dumps(datos_cache, ensure_ascii=False, indent=2), encoding="utf-8")
                temporal.replace(ruta_cache)
            except OSError as error_cache:
                app.logger.warning("No se pudo guardar la ficha Gemini en caché: %s", error_cache)
                try:
                    temporal.unlink(missing_ok=True)
                except OSError:
                    pass
        return jsonify(resultado_final)

    mensaje = error_final or "Gemini no ha podido generar una ficha con fuentes verificables."
    app.logger.warning("No se generó ficha Gemini para %s (%s): %s", nombre, tipo, mensaje)
    return jsonify({"encontrado": False, "nombre": nombre, "titulo": nombre,
                    "fuente_tipo": "ninguna", "motor": "ninguno",
                    "aviso_gemini": mensaje, "error": mensaje, "fuentes": []}), 503

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



# Las acciones que lanzan actualizaciones tienen límite de frecuencia.
# Si ADMIN_ACTION_TOKEN está configurado, también exigen ese secreto en una cabecera.
_VENTANA_ACCIONES_SEGUNDOS = 600
_MAX_ACCIONES_POR_VENTANA = 10
_acciones_por_ip = {}
_candado_acciones_ip = threading.Lock()


def _comprobar_permiso_actualizacion():
    token_configurado = (os.environ.get("ADMIN_ACTION_TOKEN") or "").strip()
    token_recibido = (request.headers.get("X-Admin-Token") or "").strip()
    if token_configurado and (
        not token_recibido or not secrets.compare_digest(token_recibido, token_configurado)
    ):
        return jsonify({"error": "Esta acción requiere el token de administración."}), 401

    # En Render, la actualización completa queda bloqueada hasta configurar un token.
    if request.path == "/api/actualizar" and os.environ.get("RENDER") and not token_configurado:
        return jsonify({
            "error": "La actualización manual está desactivada hasta configurar ADMIN_ACTION_TOKEN en el entorno del servidor."
        }), 503

    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "desconocida").split(",")[0].strip()
    ahora = time.time()
    with _candado_acciones_ip:
        recientes = [t for t in _acciones_por_ip.get(ip, []) if ahora - t < _VENTANA_ACCIONES_SEGUNDOS]
        if len(recientes) >= _MAX_ACCIONES_POR_VENTANA:
            return jsonify({
                "error": "Se han solicitado demasiadas actualizaciones. Espera unos minutos antes de volver a intentarlo."
            }), 429
        recientes.append(ahora)
        _acciones_por_ip[ip] = recientes
        if len(_acciones_por_ip) > 1000:
            for clave_ip in list(_acciones_por_ip):
                _acciones_por_ip[clave_ip] = [
                    t for t in _acciones_por_ip[clave_ip]
                    if ahora - t < _VENTANA_ACCIONES_SEGUNDOS
                ]
                if not _acciones_por_ip[clave_ip]:
                    _acciones_por_ip.pop(clave_ip, None)
    return None


@app.post("/api/actualizar")
def actualizar_radar():
    permiso = _comprobar_permiso_actualizacion()
    if permiso:
        return permiso
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
    permiso = _comprobar_permiso_actualizacion()
    if permiso:
        return permiso
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