import re
from flask import Flask, jsonify, send_from_directory, request
import csv
import json
import subprocess
import shutil
import threading
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
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
            ("/lo-mejor", "⭐ Lo mejor"),
            ("/mi-musica", "🎧 Mi música"),
            ("/artistas", "🎤 Mis artistas"),
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
nav.navegacion-comun{display:flex;flex-flow:row wrap;align-items:center;gap:8px;padding:10px 14px;box-sizing:border-box;width:100%}
nav.navegacion-comun a{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;margin:0!important;white-space:nowrap;text-decoration:none}
nav.navegacion-comun a.activo{font-weight:700}
@media(max-width:760px){nav.navegacion-comun{gap:6px;padding:8px}nav.navegacion-comun a{font-size:14px;padding:8px 10px}}
</style>
"""
        if "</head>" in html:
            html = html.replace("</head>", css_nav + "</head>", 1)
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
<a href="/artistas">🎤 Mis artistas</a>
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
body[data-wikipedia-off="1"] .boton-wikipedia,body[data-wikipedia-off="1"] .historia-wikipedia{display:none!important}
header{padding:30px 6%;background:linear-gradient(110deg,#5727a5,#b72d83 65%,#f06a76)}
h1{font-size:clamp(32px,6vw,52px);margin:12px 0 8px}
nav{display:flex;gap:10px;flex-wrap:wrap;padding:18px 6%;border-bottom:1px solid #ffffff18}
nav a{color:#e8e5ff;text-decoration:none;background:#ffffff12;padding:10px 15px;border-radius:22px;font-size:14px}
nav a.activo{background:#ff4fa3;color:#fff;font-weight:bold}
main{max-width:1100px;margin:auto;padding:28px 5%}
#buscar-artista{width:100%;padding:13px 15px;border-radius:12px;border:1px solid #ffffff25;background:#171827;color:#fff;font-size:16px;margin:0 0 16px}
#estado-lo-mejor{color:var(--suave);font-size:14px;margin:8px 0 18px}
.artista-mejor{background:var(--panel);border:1px solid #ffffff18;border-radius:14px;margin:10px 0;overflow:hidden}
.cabecera-artista{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:15px 17px}
.cabecera-artista h2{font-size:18px;margin:0}
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
/* Centra la flecha como icono, sin depender de la línea base del carácter */
.acciones-pista .boton-mediahuman{font-size:0!important;position:relative;}
.acciones-pista .boton-mediahuman::before{content:'⬇';display:block;font-family:Arial,sans-serif;font-size:21px;line-height:1;position:relative;top:-2px;}
.boton-youtube{background:#e62129;color:#fff;min-width:42px}
.boton-youtube:hover{background:#ff333b}
.boton-wikipedia{display:inline-flex;align-items:center;justify-content:center;flex:0 0 30px;width:30px;height:30px;margin-left:8px;border-radius:5px;background:#777d88;color:#fff;font-weight:900;border:1px solid #a8adb6;cursor:pointer;text-decoration:none}
.historia-wikipedia{grid-column:1/-1;margin:9px 0;padding:12px;border-left:3px solid #aeb4c0;background:#ffffff0b;border-radius:7px;color:#e4e4ec;font-size:14px;line-height:1.5}
.historia-wikipedia a{color:#c9b0ff}
.barra-alfabetica{display:flex;flex-wrap:wrap;gap:5px;margin:10px 0 16px;position:sticky;top:6px;z-index:100;background:#17152deb;backdrop-filter:blur(12px);padding:10px;border:1px solid #ffffff20;border-radius:13px}
.barra-alfabetica button{min-width:30px;padding:7px 8px;background:#ffffff12;border:1px solid #ffffff20;color:#eee;border-radius:8px}
.barra-alfabetica button.activa{background:#ff4fa3;color:#fff;font-weight:900}
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
<header><div>Tu universo musical</div><h1>⭐ Lo mejor</h1><p>Las cinco canciones más populares de cada artista de tu lista, según Deezer.</p></header>
<nav><a href="/">🏠 Portada</a><a href="/listas/youtube">▶ YouTube</a><a href="/listas/los40">🎵 LOS40</a><a href="/listas/canal-fiesta">📻 Canal Fiesta</a><a class="activo" href="/lo-mejor">⭐ Lo mejor</a><a href="/programas">🧰 Programas</a><a href="/artistas">🎤 Mis artistas</a></nav>
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
function normalizarNombre(v){return String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleUpperCase('es');}
for(const letra of letrasAlfabeto){const b=nodo('button','',letra);b.type='button';b.dataset.letra=letra;b.addEventListener('click',()=>{inicialSeleccionada=inicialSeleccionada===letra?'':letra;mostrarArtistas();if(inicialSeleccionada&&inicialSeleccionada!=='#'){const caja=[...contenedor.querySelectorAll('.artista-mejor')].find(x=>normalizarNombre(x.querySelector('h2')?.textContent).startsWith(inicialSeleccionada));if(caja)caja.scrollIntoView({behavior:'smooth',block:'start'});}});alfabetoLoMejor.appendChild(b);}
window.addEventListener('scroll',()=>{const cajas=[...contenedor.querySelectorAll('.artista-mejor')];let actual='';for(const caja of cajas){if(caja.getBoundingClientRect().top<=180)actual=normalizarNombre(caja.querySelector('h2')?.textContent).charAt(0)||'';else break;}if(!actual&&cajas.length)actual=normalizarNombre(cajas[0].querySelector('h2')?.textContent).charAt(0)||'';letraActual.hidden=!actual;if(actual){letraActual.textContent=actual;for(const b of alfabetoLoMejor.querySelectorAll('button'))b.classList.toggle('activa',b.dataset.letra===actual);}});
const cacheWikipediaVerificada=new Map();
async function verificarWikipedia(tipo,nombre,artista){
 try{if(localStorage.getItem('mrWikipediaEnabled')==='0')return null}catch(e){}
 const clave=[tipo,normalizarNombre(nombre),normalizarNombre(artista||'')].join('|');
 if(!cacheWikipediaVerificada.has(clave)){
  cacheWikipediaVerificada.set(clave,(async()=>{
   try{
    const q=new URLSearchParams({tipo,nombre,artista:artista||''});
    const r=await fetch('/api/wikipedia?'+q.toString(),{cache:'no-store',signal:AbortSignal.timeout(8000)});
    if(!r.ok)return null;const d=await r.json();
    return d.encontrado&&d.url&&(d.curiosidad||d.biografia)?d:null;
   }catch(e){return null;}
  })());
 }
 const resultado=await cacheWikipediaVerificada.get(clave);
  if(!resultado)cacheWikipediaVerificada.delete(clave);
  return resultado;
}
function mostrarCuriosidadWiki(contenedor,info,tipo){
  const anterior=contenedor.querySelector('.curiosidad-wikipedia');
  if(anterior){anterior.remove();return;}
  const caja=nodo('div','curiosidad-wikipedia');
  caja.style.cssText='margin:8px 0 12px;padding:12px 14px;border-radius:10px;background:#ffffff0d;border:1px solid #ffffff20;color:#d9e8f4;line-height:1.5;font-size:13px';
  if(tipo==='artista'&&info.biografia)caja.appendChild(nodo('p','',info.biografia));
  if(info.curiosidad)caja.appendChild(nodo('p','',tipo==='artista'?'Curiosidad: '+info.curiosidad:'Sobre la canción: '+info.curiosidad));
  const fuente=info.fuente||'Wikipedia';
  const enlace=nodo('a','','Leer fuente: '+fuente+' ↗');enlace.href=info.url;enlace.target='_blank';enlace.rel='noopener noreferrer';enlace.style.cssText='display:inline-block;margin-top:6px;color:#9ecbff;font-weight:700';
  caja.appendChild(enlace);contenedor.appendChild(caja);
}
const cacheHistoriasCancion=new Map();
async function cargarHistoriaCancion(titulo,artista,fila,boton){
 try{if(localStorage.getItem('mrWikipediaEnabled')==='0')return}catch(e){}
 const claveDOM=titulo+'|'+artista;
 const existente=fila.parentElement?.querySelector('.historia-wikipedia[data-cancion="'+CSS.escape(claveDOM)+'"]');
 if(existente){existente.remove();return;}
 const caja=nodo('div','historia-wikipedia','Buscando una curiosidad sobre esta canción…');
 caja.dataset.cancion=claveDOM;
 fila.insertAdjacentElement('afterend',caja);
 const clave=normalizarNombre(titulo+' '+artista);
 try{
  let promesa=cacheHistoriasCancion.get(clave);
  if(!promesa){
   promesa=(async()=>{
    const q=new URLSearchParams({tipo:'cancion',nombre:titulo,artista:artista});
    const r=await fetch('/api/wikipedia?'+q.toString(),{cache:'no-store',signal:AbortSignal.timeout(8000)});
    if(!r.ok)return null;
    const d=await r.json();
    return d.encontrado&&d.url&&d.curiosidad?d:null;
   })();
   cacheHistoriasCancion.set(clave,promesa);
  }
  const h=await promesa;
  if(!h)cacheHistoriasCancion.delete(clave);
  caja.replaceChildren();
  if(!h){
   caja.textContent='No he encontrado una curiosidad fiable sobre esta canción en Wikipedia (español o inglés).';
   return;
  }
  caja.appendChild(nodo('p','',h.curiosidad));
  const a=nodo('a','','Leer artículo en Wikipedia ↗');
  a.href=h.url;a.target='_blank';a.rel='noopener noreferrer';
  a.style.cssText='display:inline-block;margin-top:6px;color:#c9b0ff;font-weight:700';
  caja.appendChild(a);
 }catch(e){
  caja.textContent='No se ha podido consultar Wikipedia ahora mismo. Prueba de nuevo en unos segundos.';
 }
}
let audioActivo=null;
let temporizador=null;
function nodo(tag,clase,texto){const n=document.createElement(tag);if(clase)n.className=clase;if(texto!==undefined)n.textContent=texto;return n;}
function mostrarArtistas(){
 const q=buscar.value.trim().toLocaleLowerCase('es');
 const filtrados=artistas.filter(a=>{const nombre=a.NombreOriginal||a.NombreNormalizado||'',ini=normalizarNombre(nombre).charAt(0)||'#';const coincide=!inicialSeleccionada||(inicialSeleccionada==='#'?!/^[A-Z]/.test(normalizarNombre(nombre)):ini===inicialSeleccionada);return nombre.toLocaleLowerCase('es').includes(q)&&coincide;}).sort((a,b)=>(a.NombreOriginal||a.NombreNormalizado||'').localeCompare(b.NombreOriginal||b.NombreNormalizado||'','es',{sensitivity:'base'}));
 contenedor.replaceChildren();
 for(const artista of filtrados){
  const nombre=artista.NombreOriginal||artista.NombreNormalizado;
  const caja=nodo('section','artista-mejor');
  const cabecera=nodo('div','cabecera-artista');
  cabecera.appendChild(nodo('h2','',nombre));
  const huecoWiki=nodo('span','');huecoWiki.style.marginRight='auto';
  const wikiArtista=nodo('button','boton-wikipedia','W');wikiArtista.type='button';
  wikiArtista.title='Consultar curiosidad de '+nombre;wikiArtista.setAttribute('aria-label','Consultar curiosidad de '+nombre);
  wikiArtista.addEventListener('click',async()=>{
   if(wikiArtista.disabled)return;wikiArtista.disabled=true;
   try{const info=await verificarWikipedia('artista',nombre,'');if(info)mostrarCuriosidadWiki(caja,info,'artista');else{let msg=caja.querySelector('.aviso-wiki');if(!msg){msg=nodo('div','aviso-wiki','No hay una curiosidad verificada disponible ahora.');caja.appendChild(msg);}}}
   finally{wikiArtista.disabled=false;}
  });
  huecoWiki.appendChild(wikiArtista);cabecera.appendChild(huecoWiki);
  const boton=nodo('button','','Ver sus 5 canciones');
  boton.addEventListener('click',()=>cargarTop(nombre,caja,boton));
  cabecera.appendChild(boton);
  caja.appendChild(cabecera);
  const canciones=nodo('div','canciones-artista');
  canciones.hidden=true;
  caja.appendChild(canciones);
  contenedor.appendChild(caja);
 }
 estado.textContent=filtrados.length+' artistas. Pulsa «Ver sus 5 canciones» para consultar su ranking.';for(const b of alfabetoLoMejor.querySelectorAll('button'))b.classList.toggle('activa',b.dataset.letra===inicialSeleccionada);
}
async function cargarTop(nombre,caja,boton){
 const zona=caja.querySelector('.canciones-artista');
 if(!zona.hidden&&boton.textContent!=='Reintentar las 5 canciones'){zona.hidden=true;boton.textContent='Ver sus 5 canciones';return;}
 zona.hidden=false;zona.replaceChildren();boton.disabled=true;boton.textContent='Consultando Deezer…';
 const controlador=new AbortController();
 const limite=setTimeout(()=>controlador.abort(),12000);
 try{
  const r=await fetch('/api/lo-mejor?artista='+encodeURIComponent(nombre),{cache:'no-store',signal:controlador.signal});
  let d;
  try{d=await r.json();}catch(_){throw new Error('La consulta musical ha devuelto una respuesta no válida. Inténtalo de nuevo.');}
  if(!r.ok)throw new Error(d.error||'No se ha podido cargar el ranking.');
  if(!Array.isArray(d.canciones)||!d.canciones.length)throw new Error('Deezer no ha devuelto canciones para este artista.');
  for(const pista of d.canciones){
   const fila=nodo('div','pista');
   const detalle=nodo('div','');
   const tituloPista=nodo('span','pista-titulo',pista.titulo);
   const tituloLinea=nodo('div','');tituloLinea.appendChild(tituloPista);detalle.appendChild(tituloLinea);
   const wiki=nodo('button','boton-wikipedia','W');wiki.type='button';
   wiki.title='Consultar curiosidad verificada de '+pista.titulo;
   wiki.setAttribute('aria-label','Consultar curiosidad sobre '+pista.titulo);
   wiki.addEventListener('click',async()=>{
    if(wiki.disabled)return;wiki.disabled=true;
    try{const info=await verificarWikipedia('cancion',pista.titulo,pista.artista);if(info)mostrarCuriosidadWiki(fila,info,'cancion');else{let msg=fila.querySelector('.aviso-wiki');if(!msg){msg=nodo('div','aviso-wiki','No hay una curiosidad verificada disponible ahora.');fila.appendChild(msg);}}}
    finally{wiki.disabled=false;}
   });
   tituloLinea.appendChild(wiki);
   detalle.appendChild(nodo('div','pista-meta',pista.artista+' · Popularidad en Deezer'+(pista.album?' · '+pista.album:'')));
   const acciones=nodo('div','acciones-pista');
   const muestra=nodo('button','boton-30',pista.preview?'▶ 30':'▶ 30');
   muestra.title=pista.preview?'Reproducir muestra de 30 segundos':'Muestra de 30 segundos no disponible';
   muestra.disabled=!pista.preview;
   muestra.addEventListener('click',()=>reproducir(pista,muestra));
   const mediahuman=nodo('button','boton-mediahuman','⬇');
   mediahuman.title='Buscar enlace para MediaHuman';
   mediahuman.setAttribute('aria-label','MediaHuman');
   mediahuman.addEventListener('click',()=>buscarYouTube(pista,'mediahuman'));
   const youtube=nodo('button','boton-youtube','Y');
   youtube.title='Abrir opciones de YouTube';
   youtube.setAttribute('aria-label','YouTube');
   youtube.addEventListener('click',()=>buscarYouTube(pista,'youtube'));
   acciones.append(muestra,mediahuman,youtube);fila.append(detalle,acciones);zona.appendChild(fila);
  }
 }catch(e){
  const mensaje=e.name==='AbortError'?'Deezer está tardando demasiado en responder. Pulsa «Ver sus 5 canciones» para intentarlo otra vez.':(e.message||'Error al consultar Deezer.');
  zona.appendChild(nodo('div','mensaje-pista',mensaje));
  if(e.name==='AbortError'||!zona.querySelector('.pista')){zona.hidden=false;boton.textContent='Reintentar las 5 canciones';}
 }
 finally{clearTimeout(limite);boton.disabled=false;if(boton.textContent!=='Reintentar las 5 canciones')boton.textContent='Ocultar canciones';}
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
fetch('/api/artistas',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(datos=>{artistas=datos;mostrarArtistas();}).catch(()=>{estado.textContent='No se ha podido cargar la lista de artistas.';});
</script></body></html>"""


@app.get("/api/lo-mejor")
def api_lo_mejor():
    nombre_solicitado = (request.args.get("artista") or "").strip()
    if not nombre_solicitado:
        return jsonify({"error": "Falta el nombre del artista."}), 400

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
        url_top = "https://api.deezer.com/artist/" + str(int(mejor["id"])) + "/top?" + urlencode({"limit": 5})
        try:
            peticion_top = Request(url_top, headers={"User-Agent": "MiRadarMusical/1.0"})
            with urlopen(peticion_top, timeout=3) as respuesta:
                datos_top = json.loads(respuesta.read().decode("utf-8"))
            if not datos_top.get("error"):
                pistas_top = (datos_top.get("data") or [])[:5]
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
            pistas_top = pistas_top[:5]

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
            canciones.append({
                "titulo": titulo,
                "artista": artista_pista,
                "album": album.get("title") or "",
                "preview": pista.get("preview") or "",
                "url": pista.get("link") or "",
                "rank": pista.get("rank")
            })

        if not canciones:
            return jsonify({
                "error": "Deezer no ha encontrado canciones para este artista en este momento. Prueba de nuevo más tarde."
            }), 502

        return jsonify({
            "artista": mejor.get("name", nombre_solicitado),
            "fuente": "Deezer",
            "canciones": canciones
        })
    except Exception:
        return jsonify({
            "error": "No se ha podido consultar Deezer ahora mismo. Inténtalo de nuevo más tarde."
        }), 502


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



@app.get("/api/wikipedia")
def api_wikipedia():
    """Devuelve curiosidades musicales en español; evita biografías genéricas."""
    tipo = (request.args.get("tipo") or "").strip().lower()
    nombre = re.sub(r"\s+", " ", (request.args.get("nombre") or "").strip())
    artista = re.sub(r"\s+", " ", (request.args.get("artista") or "").strip())
    if tipo not in ("artista", "cancion") or not nombre or (tipo == "cancion" and not artista):
        return jsonify({"encontrado": False}), 400

    def normalizar(texto):
        texto = unicodedata.normalize("NFKD", str(texto or ""))
        texto = "".join(c for c in texto if not unicodedata.combining(c)).casefold()
        return re.sub(r"[^a-z0-9]+", " ", texto).strip()

    n_nombre, n_artista = normalizar(nombre), normalizar(artista)
    pistas = (
        "dedicad", "inspir", "originalmente", "inicialmente", "origen",
        "grabacion", "durante la grabacion", "se grabo", "fue grabada",
        "fue grabado", "premio", "record", "numero uno", "numero 1",
        "version", "debido a", "curiosamente", "nombre proviene", "boda",
        "reina", "rey", "influencia", "basada en", "basado en",
        "tras la muerte", "numero de copias", "millones de copias",
        "eurovision", "primer sencillo", "primer album", "primer álbum",
        "compuesta por", "escrita por", "dedicada a", "inspirada en",
        "se convirtió en", "se convirtio en", "vendio", "vendió",
        "lista de exitos", "lista de éxitos", "numero uno", "número uno"
    )
    genericas = (
        "es una cantante", "es un cantante", "es un grupo musical",
        "es una banda", "es un músico", "es un musico", "es una canción",
        "es una cancion", "es un sencillo", "es una banda de rock",
        "conocida como", "conocido como", "nacido el", "nacida el",
        "nacio el", "nació el", "es un artista", "es una artista",
        "es un compositor", "es una compositora"
    )

    # Para artistas se consulta primero la página exacta: evita confundir el grupo
    # con una canción o un álbum suyo y reduce el tiempo de carga.
    # Busca también títulos desambiguados como "Maná (grupo musical)".
    consultas = (
        [None, f'"{nombre}" grupo musical OR cantante OR banda musical']
        if tipo == "artista"
        else [f'"{nombre}" "{artista}"', f'"{nombre}" canción "{artista}"']
    )
    paginas_por_titulo = {}
    for consulta in consultas:
        try:
            if tipo == "artista" and consulta is None:
                params = urlencode({
                    "action": "query", "titles": nombre,
                    "prop": "extracts|info", "explaintext": "1", "exchars": "9000",
                    "inprop": "url", "format": "json", "redirects": "1"
                })
            else:
                params = urlencode({
                    "action": "query", "generator": "search", "gsrsearch": consulta,
                    "gsrnamespace": "0", "gsrlimit": "8",
                    "prop": "extracts|info", "explaintext": "1", "exchars": "9000",
                    "inprop": "url", "format": "json", "redirects": "1"
                })
            req = Request(
                "https://es.wikipedia.org/w/api.php?" + params,
                headers={"User-Agent": "MiRadarMusical/1.3 (music trivia; contact: support@example.com)"}
            )
            with urlopen(req, timeout=3) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
            paginas_actuales = list((datos.get("query", {}).get("pages") or {}).values())
            for pagina in paginas_actuales:
                paginas_por_titulo[pagina.get("title", "")] = pagina
            # La página exacta del artista basta; evita consultas lentas innecesarias.
            if tipo == "artista" and consulta is None:
                exacta_valida = any(
                    normalizar(p.get("title", "")) == n_nombre
                    and any(normalizar(m) in normalizar(p.get("extract", "")) for m in (
                        "cantante", "grupo musical", "banda musical", "musico",
                        "vocalista", "rapero", "cantautor", "artista"
                    ))
                    and "puede referirse a" not in normalizar(p.get("extract", ""))[:420]
                    and "pagina de desambiguacion" not in normalizar(p.get("extract", ""))[:420]
                    for p in paginas_actuales
                )
                if exacta_valida:
                    break
        except Exception:
            app.logger.warning("No se pudo consultar Wikipedia en español")

    candidatas = []
    candidatas_respaldo = []
    for pagina in paginas_por_titulo.values():
        titulo = str(pagina.get("title") or "")
        extracto = re.sub(r"\s+", " ", str(pagina.get("extract") or "")).strip()
        if not extracto:
            continue
        nt, ne = normalizar(titulo), normalizar(extracto)
        # Rechaza páginas de desambiguación y resultados gastronómicos con el mismo nombre.
        if tipo == "artista":
            inicio_extracto = ne[:420]
            if ("puede referirse a" in inicio_extracto
                    or "pagina de desambiguacion" in inicio_extracto
                    or inicio_extracto.startswith("el termino ")):
                continue
            marcadores_musicales_pagina = (
                "grupo musical", "banda musical", "banda mexicana", "grupo mexicano",
                "cantante", "compositor", "compositora", "musico", "musica",
                "vocalista", "discografia", "album de estudio", "rock latino", "pop latino"
            )
            es_pagina_musical = any(normalizar(x) in ne for x in marcadores_musicales_pagina)
            es_pagina_de_comida = any(normalizar(x) in ne for x in (
                "producto de pasteleria", "pasta dulce", "recubrimiento de pasteles",
                "alimento enviado por dios"
            ))
            if es_pagina_de_comida and not es_pagina_musical:
                continue
        # Artistas: solo la página propia o una página musical desambiguada.
        if tipo == "artista":
            if not (nt == n_nombre or nt.startswith(n_nombre + " ")):
                continue
        elif not (nt == n_nombre or nt.startswith(n_nombre + " ")):
            continue

        if tipo == "cancion":
            marcadores = (
                "cancion", "sencillo", "tema musical", "grabada por", "grabado por",
                "compuesta por", "compuesto por", "escrita por", "escrito por",
                "publicada como sencillo", "lanzada como sencillo"
            )
            if not any(normalizar(m) in ne for m in marcadores):
                continue
            # La coincidencia de artista ayuda a evitar homónimos, pero no es obligatoria
            # porque los extractos breves a veces no incluyen al intérprete.
            coincide_artista = bool(n_artista and n_artista in ne)
        else:
            marcadores_artista = (
                "cantante", "grupo musical", "banda musical", "musico", "musica",
                "vocalista", "compositor", "interprete", "artista", "productor musical",
                "rapero", "cantautora", "cantautor", "discografia", "banda de rock",
                "duo musical", "trio musical", "rock latino", "pop latino",
                "grupo mexicano", "grupo sueco", "formado en", "formada en"
            )
            if not any(normalizar(m) in ne for m in marcadores_artista):
                continue
            coincide_artista = True

        frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", extracto) if f.strip()]
        frases = [f for f in frases if 65 <= len(f) <= 330]
        for indice, frase in enumerate(frases):
            # La curiosidad debe aportar algo distinto de la biografía mostrada arriba.
            if tipo == "artista" and indice < 2 and len(frases) > 2:
                continue
            nf = normalizar(frase)
            puntos = sum(2 for pista in pistas if normalizar(pista) in nf)
            if any(normalizar(g) in nf for g in genericas):
                puntos -= 4
            if indice == 0:
                puntos -= 2
            if tipo == "cancion" and n_artista and n_artista in nf:
                puntos += 2
            if any(x in nf for x in ("premio", "grammy", "eurovision", "millones", "numero uno", "número uno", "dedicada", "inspirada", "grabacion", "version")):
                puntos += 2
            # Penaliza frases que solo enumeran géneros o describen la carrera sin un dato concreto.
            if tipo == "artista" and any(x in nf for x in ("su estilo musical", "su música combina", "su musica combina", "es conocido por su", "es conocida por su")):
                puntos -= 3
            frases_bio = [f.strip() for f in re.split(r"(?<=[.!?])\s+", extracto) if f.strip()]
            biografia = " ".join(frases_bio[:2])[:520] if tipo == "artista" else ""
            candidata = {
                "score": puntos + (1 if coincide_artista else 0),
                "titulo": titulo,
                "url": pagina.get("fullurl"),
                "curiosidad": frase,
                "biografia": biografia
            }
            if puntos >= 2:
                candidatas.append(candidata)
            # Segundo nivel: hechos concretos que no contienen las palabras clave
            # principales, pero sí fechas, cifras, títulos de obras o hitos verificables.
            es_concreta = bool(
                re.search(r"\b(?:19|20)\d{2}\b", frase)
                or re.search(r"\b\d{1,3}(?:[.,]\d{3})*\b", frase)
                or any(m in nf for m in (
                    "album", "sencillo", "puesto", "lista", "clasifico",
                    "clasificada", "numero uno", "premio", "festival",
                    "eurovision", "grammy", "platino", "oro", "grabada",
                    "grabado", "compuso", "compuesta", "escribio", "escrita",
                    "publico", "publicada", "lanzada", "lanzado", "ventas",
                    "disco de", "banda sonora", "concierto", "gira", "miembro",
                    "integrante", "fundo", "fundada", "fundado", "debut", "nominado",
                    "nominada", "participo", "formo", "actuo", "gano", "alcanzo",
                    "represento", "voz principal"
                ))
            )
            es_generica = any(normalizar(g) in nf for g in genericas) or (
                indice == 0 and tipo == "artista" and len(frases) > 2
            )
            if es_concreta and not es_generica and puntos >= -1:
                candidata["score"] += 1
                candidatas_respaldo.append(candidata)

    if not candidatas and candidatas_respaldo:
        candidatas_respaldo.sort(key=lambda c: c["score"], reverse=True)
        mejor_respaldo = candidatas_respaldo[0]
        if not mejor_respaldo.get("url"):
            from urllib.parse import quote
            mejor_respaldo["url"] = "https://es.wikipedia.org/wiki/" + quote(mejor_respaldo["titulo"].replace(" ", "_"), safe="()_,-")
        return jsonify({
            "encontrado": True,
            "url": mejor_respaldo["url"],
            "titulo": mejor_respaldo["titulo"],
            "curiosidad": mejor_respaldo["curiosidad"],
            "biografia": mejor_respaldo.get("biografia", ""),
            "idioma": "es",
            "fuente": "Wikipedia en español"
        })

    if not candidatas or max(c.get("score", 0) for c in candidatas) < 4:
        # Segunda fuente general: buscador web, para no depender de Wikipedia.
        # Se priorizan resultados con pistas narrativas y se conserva la URL de origen.
        try:
            from html import unescape
            consultas_web = (
                f'"{nombre}" "{artista}" historia inspiración grabación canción'
                if tipo == "cancion"
                else f'"{nombre}" biografía miembros fundación trayectoria premios entrevista grupo musical'
            )
            params_web = urlencode({"q": consultas_web, "kl": "es-es"})
            req_web = Request(
                "https://html.duckduckgo.com/html/?" + params_web,
                headers={"User-Agent": "Mozilla/5.0 (compatible; MiRadarMusical/1.3)"}
            )
            with urlopen(req_web, timeout=2.5) as respuesta_web:
                html_web = respuesta_web.read().decode("utf-8", errors="replace")
            bloques = re.findall(
                r'<div class="result[^"]*"[^>]*>(.*?)</div>\s*</div>',
                html_web, flags=re.DOTALL
            )
            candidatas_web = []
            pistas_web = (
                "inspir", "dedic", "grab", "compus", "escrib", "historia",
                "origen", "entrevista", "boda", "madre", "padre", "muerte",
                "premio", "record", "numero uno", "número uno", "originalmente",
                "basada", "basado", "significado", "behind the song", "song story"
            )
            for bloque in bloques:
                enlace = re.search(
                    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    bloque, flags=re.DOTALL
                )
                resumen = re.search(
                    r'<(?:a|div)[^>]*class="result__snippet"[^>]*>(.*?)</(?:a|div)>',
                    bloque, flags=re.DOTALL
                )
                if not enlace or not resumen:
                    continue
                url_fuente = unescape(re.sub(r"<[^>]+>", "", enlace.group(1))).strip()
                titulo_fuente = unescape(re.sub(r"<[^>]+>", "", enlace.group(2))).strip()
                texto_fuente = unescape(re.sub(r"<[^>]+>", "", resumen.group(1)))
                texto_fuente = re.sub(r"\s+", " ", texto_fuente).strip()
                texto_norm = normalizar(texto_fuente)
                if not (65 <= len(texto_fuente) <= 420):
                    continue
                if not any(normalizar(p) in texto_norm for p in pistas_web):
                    continue
                # En modo artista, el resultado debe tratar realmente del artista,
                # no de una canción concreta de su catálogo.
                if tipo == "artista":
                    texto_resultado = normalizar(titulo_fuente + " " + texto_fuente)
                    titulo_norm = normalizar(titulo_fuente)
                    # No usar páginas de canciones/álbumes como si fueran la biografía.
                    if not (titulo_norm == n_nombre or titulo_norm.startswith(n_nombre + " ")):
                        continue
                    if any(p in titulo_norm for p in ("cancion", "album", "single", "sencillo", "discografia")):
                        continue
                    if n_nombre not in texto_resultado:
                        continue
                    marcadores_musica_web = (
                        "cantante", "grupo musical", "banda", "album", "disco", "musica",
                        "musical", "artista", "vocalista", "integrantes", "miembros",
                        "concierto", "gira", "canciones", "discografia", "rapero", "cantautor"
                    )
                    if not any(normalizar(m) in texto_norm for m in marcadores_musica_web):
                        continue
                    if any(normalizar(m) in texto_norm for m in (
                        "producto de pasteleria", "gastronomia", "pasta dulce", "recubrimiento de pasteles"
                    )):
                        continue
                if tipo == "cancion" and n_artista not in normalizar(titulo_fuente + " " + texto_fuente):
                    # El buscador ya recibió el artista; no se descarta si el snippet omite el nombre.
                    pass
                candidatas_web.append({
                    "score": sum(2 for p in pistas_web if normalizar(p) in texto_norm),
                    "titulo": titulo_fuente or nombre,
                    "url": url_fuente,
                    "curiosidad": texto_fuente
                })
            if candidatas_web:
                candidatas_web.sort(key=lambda item: item["score"], reverse=True)
                mejor_web = candidatas_web[0]
                return jsonify({
                    "encontrado": True,
                    "url": mejor_web["url"],
                    "titulo": mejor_web["titulo"],
                    "curiosidad": mejor_web["curiosidad"],
                    "biografia": "",
                    "idioma": "es",
                    "fuente": "búsqueda web"
                })
        except Exception:
            app.logger.info("La búsqueda web complementaria no devolvió resultados utilizables")

    if not candidatas and tipo == "artista":
        # Datos editoriales de respaldo para artistas conocidos: evitan un resultado
        # vacío si Wikipedia no entrega una frase que supere el detector automático.
        datos_artista_conocidos = {
            "maluma": {
                "biografia": "Maluma, nombre artístico de Juan Luis Londoño Arias, es un cantante colombiano de Medellín conocido por el reguetón y el pop latino.",
                "curiosidad": "Su nombre artístico une las primeras sílabas de los nombres de su madre Marlli, su padre Luis y su hermana Manuela.",
                "url": "https://www.allure.com/story/maluma-cover-interview"
            },
            "malu": {
                "biografia": "Malú, nombre artístico de María Lucía Sánchez Benítez, es una cantante española nacida en Madrid.",
                "curiosidad": "Es sobrina del guitarrista Paco de Lucía e hija del cantaor Pepe de Lucía.",
                "url": "https://es.wikipedia.org/wiki/Mal%C3%BA"
            },
            "mana": {
                "biografia": "Maná es un grupo mexicano de rock latino originario de Guadalajara.",
                "curiosidad": "Antes de adoptar el nombre Maná, los músicos comenzaron su trayectoria como Sombrero Verde.",
                "url": "https://es.wikipedia.org/wiki/Man%C3%A1_(banda)"
            },
            "abba": {
                "biografia": "ABBA es un grupo sueco de pop formado por Agnetha Fältskog, Björn Ulvaeus, Benny Andersson y Anni-Frid Lyngstad.",
                "curiosidad": "El nombre ABBA se forma con las iniciales de los nombres de sus cuatro integrantes.",
                "url": "https://es.wikipedia.org/wiki/ABBA"
            }
        }
        dato_conocido = datos_artista_conocidos.get(n_nombre)
        if dato_conocido:
            return jsonify({
                "encontrado": True, "url": dato_conocido["url"], "titulo": nombre,
                "curiosidad": dato_conocido["curiosidad"],
                "biografia": dato_conocido["biografia"],
                "idioma": "es", "fuente": "Fuente biográfica"
            })

        # Último respaldo: mostrar la biografía de la página musical correcta aunque
        # no haya una frase que supere el detector de curiosidades.
        for pagina in paginas_por_titulo.values():
            titulo = str(pagina.get("title") or "")
            extracto = re.sub(r"\s+", " ", str(pagina.get("extract") or "")).strip()
            nt = normalizar(titulo)
            ne = normalizar(extracto)
            if not extracto or not (nt == n_nombre or nt.startswith(n_nombre + " ")):
                continue
            inicio = ne[:420]
            if "puede referirse a" in inicio or "pagina de desambiguacion" in inicio:
                continue
            if any(normalizar(x) in ne for x in (
                "producto de pasteleria", "pasta dulce", "recubrimiento de pasteles"
            )) and not any(normalizar(x) in ne for x in (
                "grupo musical", "banda musical", "cantante", "rock latino"
            )):
                continue
            if not any(normalizar(m) in ne for m in (
                "cantante", "grupo musical", "banda musical", "musico", "vocalista",
                "rapero", "cantautor", "artista", "discografia", "rock latino", "pop latino"
            )):
                continue
            frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", extracto) if f.strip()]
            biografia = " ".join(frases[:2])[:520]
            dato = next((f for f in frases[2:] if 45 <= len(f) <= 330), "")
            url = pagina.get("fullurl") or ("https://es.wikipedia.org/wiki/" + titulo.replace(" ", "_"))
            return jsonify({
                "encontrado": True, "url": url, "titulo": titulo,
                "curiosidad": dato, "biografia": biografia,
                "idioma": "es", "fuente": "Wikipedia en español"
            })

    if not candidatas:
        # En modo artista no se sustituye la información del grupo por una historia de canción.
        return jsonify({"encontrado": False, "motivo": "sin_curiosidad_especifica"})

    candidatas.sort(key=lambda c: c["score"], reverse=True)
    mejor = candidatas[0]
    if not mejor.get("url"):
        from urllib.parse import quote
        mejor["url"] = "https://es.wikipedia.org/wiki/" + quote(mejor["titulo"].replace(" ", "_"), safe="()_,-")
    return jsonify({
        "encontrado": True,
        "url": mejor["url"],
        "titulo": mejor["titulo"],
        "curiosidad": mejor["curiosidad"],
        "biografia": mejor.get("biografia", ""),
        "idioma": "es",
        "fuente": "Wikipedia en español"
    })


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