import re
from flask import Flask, jsonify, send_from_directory, request
import csv
import json
import subprocess
import shutil
import threading
import time
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import unicodedata
import difflib
import os
import sqlite3
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
        # Ventana común para las fichas musicales: se mantiene al usuario en la página actual.
        modal_fichas = r"""
<style id="modal-fichas-musicales-estilos">
#mr-ficha-modal[hidden]{display:none!important}
#mr-ficha-modal{position:fixed;inset:0;z-index:999999;background:#05050bd9;display:flex;align-items:center;justify-content:center;padding:16px}
#mr-ficha-caja{width:min(760px,100%);max-height:88vh;overflow:auto;background:#171827;color:#f7f5ff;border:1px solid #ffffff30;border-radius:18px;padding:22px;box-shadow:0 18px 60px #000b}
#mr-ficha-cabecera{display:flex;align-items:center;justify-content:space-between;gap:12px;position:sticky;top:-22px;background:#171827;padding:4px 0 14px}
#mr-ficha-titulo{font-size:clamp(22px,4vw,30px);margin:0;overflow-wrap:anywhere}
#mr-ficha-cerrar{background:#34394a;color:white;border:1px solid #ffffff25;border-radius:10px;padding:10px 13px;flex-shrink:0}
#mr-ficha-contenido{white-space:pre-wrap;line-height:1.65;overflow-wrap:anywhere}
#mr-ficha-fuentes{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
#mr-ficha-fuentes a{color:#a9c7ff;overflow-wrap:anywhere}
#mr-ficha-estado{color:#c6c3da;line-height:1.5}
@media(max-width:520px){#mr-ficha-caja{padding:16px;max-height:92vh}#mr-ficha-cabecera{top:-16px}}
</style>
<div id="mr-ficha-modal" hidden role="dialog" aria-modal="true" aria-labelledby="mr-ficha-titulo">
 <section id="mr-ficha-caja">
  <div id="mr-ficha-cabecera"><h2 id="mr-ficha-titulo">Información musical</h2><button id="mr-ficha-cerrar" type="button">Cerrar ✕</button></div>
  <p id="mr-ficha-estado" role="status">Preparando la ficha…</p>
  <div id="mr-ficha-contenido"></div><div id="mr-ficha-fuentes"></div>
 </section>
</div>
<script id="mr-fichas-musicales-script">
(()=> {
 if(window.__mrFichasModalInstalado)return;window.__mrFichasModalInstalado=true;
 const modal=document.getElementById('mr-ficha-modal'),titulo=document.getElementById('mr-ficha-titulo'),estado=document.getElementById('mr-ficha-estado'),contenido=document.getElementById('mr-ficha-contenido'),fuentes=document.getElementById('mr-ficha-fuentes'),cerrar=document.getElementById('mr-ficha-cerrar');
 if(!modal)return;let focoAnterior=null,peticion=0;
 function ocultar(){modal.hidden=true;if(focoAnterior&&focoAnterior.isConnected)focoAnterior.focus()}
 cerrar.addEventListener('click',ocultar);modal.addEventListener('click',e=>{if(e.target===modal)ocultar()});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden)ocultar()});
 function textoCercano(b,selector){const n=b.closest(selector);return n?n.innerText||'':''}
 document.addEventListener('click',async e=>{
  const b=e.target.closest('button.wiki-icon,button.boton-wikipedia,button.wiki');if(!b)return;
  const tipo=(b.dataset.wikiTipo||'').toLowerCase();
  let nombre=(b.dataset.wikiNombre||'').trim(),artista=(b.dataset.wikiArtista||'').trim();
  if(!nombre){
   const etiqueta=(b.getAttribute('aria-label')||b.title||'').trim();
   const coincidencia=etiqueta.match(/información(?: sobre| de)?\s+(.+?)\s+de\s+(.+)$/i);
   if(coincidencia){nombre=coincidencia[1].trim();artista=coincidencia[2].trim()}
   else{
    const biografia=etiqueta.match(/biografía(?: y curiosidad)? de\s+(.+)$/i);
    if(biografia)nombre=biografia[1].trim();
   }
  }
  if(!nombre){
   const fila=b.closest('.pista,.fila-cancion,.tarjeta,.publicacion,.artista-mejor')||b.parentElement;
   const tituloNodo=fila&&fila.querySelector('.pista-titulo,.titulo-cancion,.titulo,.pista-titulo');
   const artistaNodo=fila&&fila.querySelector('.artista-cancion,.artista,.pista-meta');
   nombre=(tituloNodo&&tituloNodo.textContent||'').replace(/\s*[Wℹ️G]\s*$/,'').trim();
   artista=(artistaNodo&&artistaNodo.textContent||'').trim().split(' · ').filter(Boolean).slice(-1)[0]||'';
  }
  const tipoFinal=tipo==='artista'||/artista|biografía/i.test((b.title||'')+' '+(b.getAttribute('aria-label')||''))?'artista':'cancion';
  if(tipoFinal==='artista'&&!b.dataset.wikiNombre){nombre=(b.closest('.artista-mejor')?.querySelector('h2')?.textContent||nombre).trim()}
  if(!nombre){return}
  e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
  focoAnterior=b;const id=++peticion;
  titulo.textContent=tipoFinal==='artista'?nombre:nombre+(artista?' — '+artista:'');
  estado.textContent='Buscando información fiable…';contenido.replaceChildren();fuentes.replaceChildren();modal.hidden=false;cerrar.focus();
  try{
   const q=new URLSearchParams({tipo:tipoFinal,nombre:nombre});if(artista)q.set('artista',artista);
   const r=await fetch('/api/ficha-musical?'+q.toString(),{headers:{'Accept':'application/json'}});
   const d=await r.json();if(id!==peticion)return;
   const bloques=[];
   if(d.biografia)bloques.push('BIOGRAFÍA\n'+d.biografia);
   if(d.historia)bloques.push('INFORMACIÓN DE LA CANCIÓN\n'+d.historia);
   const dm=d.datos_musicales||{};
   const filas=[];
   if(dm.nombre_oficial||dm.titulo_oficial)filas.push('Nombre oficial: '+(dm.nombre_oficial||dm.titulo_oficial));
   if(dm.tipo_artista)filas.push('Tipo: '+dm.tipo_artista);
   if(dm.pais)filas.push('País: '+dm.pais);
   if(dm.formado_o_nacido)filas.push('Inicio: '+dm.formado_o_nacido);
   if(dm.fecha_publicacion)filas.push('Fecha: '+dm.fecha_publicacion);
   if(dm.album)filas.push('Álbum: '+dm.album);
   if(dm.artista_creditado)filas.push('Artista acreditado: '+dm.artista_creditado);
   if(dm.compositores)filas.push('Compositores: '+dm.compositores);
   if(filas.length)bloques.push('DATOS MUSICALES\n'+filas.join('\n'));
   if(d.curiosidad)bloques.push('CURIOSIDAD DOCUMENTADA\n'+d.curiosidad);
   contenido.textContent=bloques.join('\n\n');
   estado.textContent=d.desde_cache?'Ficha recuperada de la caché guardada.':(d.encontrado?'Información disponible. Revisa las fuentes originales indicadas abajo.':'No se ha encontrado información fiable suficiente.');
   for(const aviso of (d.avisos||[])){const p=document.createElement('p');p.textContent=aviso;contenido.appendChild(p)}
   for(const f of (d.fuentes||[])){if(!f.url)continue;const a=document.createElement('a');a.href=f.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=f.titulo||'Consultar fuente original';fuentes.appendChild(a)}
   if(!r.ok)estado.textContent=d.error||'No se ha podido recuperar la ficha.';
  }catch(err){if(id===peticion)estado.textContent='No se ha podido consultar la información ahora mismo. Puedes cerrar esta ventana e intentarlo más tarde.'}
 },true);
})();
</script>
"""
        if 'id="mr-ficha-modal"' not in html and "</body>" in html:
            html = html.replace("</body>", modal_fichas + "\n</body>", 1)
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
.barra-alfabetica .boton-estrella{font-size:17px;min-width:40px;background:#6c4b18;border:1px solid #f7c948;color:#ffe27a}
.barra-alfabetica .boton-estrella.activa{background:#f7c948;color:#26152e;box-shadow:0 0 12px #f7c94866}
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
    const r=await fetch('/api/wikipedia?'+q.toString(),{cache:'no-store',signal:AbortSignal.timeout(45000)});
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
 const anterior=contenedor.querySelector('.info-wikipedia');
 if(anterior){anterior.remove();return;}
 const caja=nodo('div','info-wikipedia');
 caja.style.cssText='margin:8px 0 12px;padding:12px 14px;border-radius:10px;background:#ffffff0d;border:1px solid #ffffff20;color:#d9e8f4;line-height:1.5;font-size:13px';
 const contenido=info.resumen||'';
 const p=nodo('p','',contenido);p.style.whiteSpace='pre-line';caja.appendChild(p);
 (info.fuentes||[]).forEach(f=>{
  if(!f.url||!(f.url.startsWith('https://')||f.url.startsWith('http://')))return;
  const a=nodo('a','','Fuente: '+(f.titulo||f.url)+' ↗');a.href=f.url;a.target='_blank';a.rel='noopener noreferrer';
  a.style.cssText='display:block;margin-top:6px;color:#9ecbff;font-weight:700';caja.appendChild(a);
 });
 contenedor.appendChild(caja);
}
let audioActivo=null;
let temporizador=null;
function nodo(tag,clase,texto){const n=document.createElement(tag);if(clase)n.className=clase;if(texto!==undefined)n.textContent=texto;return n;}
function mostrarArtistas(){
 const q=buscar.value.trim().toLocaleLowerCase('es');
 const filtrados=artistasBase.filter(a=>{const nombre=a.NombreOriginal||a.NombreNormalizado||'',ini=normalizarNombre(nombre).charAt(0)||'#';const coincide=!inicialSeleccionada||(inicialSeleccionada==='#'?!/^[A-Z]/.test(normalizarNombre(nombre)):ini===inicialSeleccionada);return nombre.toLocaleLowerCase('es').includes(q)&&coincide;}).sort((a,b)=>(a.NombreOriginal||a.NombreNormalizado||'').localeCompare(b.NombreOriginal||b.NombreNormalizado||'','es',{sensitivity:'base'}));
 contenedor.replaceChildren();
 for(const artista of filtrados){
  const nombre=artista.NombreOriginal||artista.NombreNormalizado;
  const caja=nodo('section','artista-mejor');
  const cabecera=nodo('div','cabecera-artista');
  cabecera.appendChild(nodo('h2','',nombre+(artista.cancionesEnColeccion?' · '+artista.cancionesEnColeccion+' canciones en tu colección':'')));
  const huecoWiki=nodo('span','');huecoWiki.style.marginRight='auto';
  const wikiArtista=nodo('button','boton-wikipedia','G');wikiArtista.type='button';
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
   }finally{wikiArtista.disabled=false;wikiArtista.textContent='G';}
  });
  huecoWiki.appendChild(wikiArtista);cabecera.appendChild(huecoWiki);
  const botonesRanking=nodo('div','botones-ranking');
  const boton=nodo('button','','⭐ Más populares (20)');
  boton.addEventListener('click',()=>cargarTop(nombre,caja,boton,'populares'));
  const botonRecientes=nodo('button','','🆕 Éxitos recientes (5)');
  botonRecientes.addEventListener('click',()=>cargarTop(nombre,caja,botonRecientes,'recientes'));
  botonesRanking.append(boton,botonRecientes);
  cabecera.appendChild(botonesRanking);
  caja.appendChild(cabecera);
  const canciones=nodo('div','canciones-artista canciones-populares');
  canciones.hidden=true;
  caja.appendChild(canciones);
  const recientes=nodo('div','canciones-artista canciones-recientes');
  recientes.hidden=true;
  caja.appendChild(recientes);
  contenedor.appendChild(caja);
 }
 estado.textContent=filtrados.length+' artistas. Pulsa «Ver sus 20 canciones» para consultar su ranking.';for(const b of alfabetoLoMejor.querySelectorAll('button'))b.classList.toggle('activa',b.dataset.letra===inicialSeleccionada);
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
    }finally{wiki.disabled=false;wiki.textContent='G';}
   });
   tituloLinea.appendChild(wiki);
   const descripcion=recientes?'Lanzamiento reciente entre los temas destacados de Deezer':'Popularidad en Deezer';
   detalle.appendChild(nodo('div','pista-meta',(pista.anio||'Año no disponible')+' · '+pista.artista+' · '+descripcion+(pista.album?' · '+pista.album:'')));
   const acciones=nodo('div','acciones-pista');
   const muestra=nodo('button','boton-30','▶ 30');
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



@app.get("/api/resumen-musical")
def api_resumen_musical():
    """Genera bajo demanda un resumen musical breve con Gemini y búsqueda web."""
    tipo = (request.args.get("tipo") or "").strip().lower()
    nombre = re.sub(r"\s+", " ", (request.args.get("nombre") or "").strip())[:180]
    artista = re.sub(r"\s+", " ", (request.args.get("artista") or "").strip())[:180]
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        archivo_clave = BASE / "gemini_api_key.txt"
        try:
            if archivo_clave.is_file():
                api_key = archivo_clave.read_text(encoding="utf-8").strip()
        except OSError:
            app.logger.warning("No se pudo leer el archivo local de la clave de Gemini.")
    if tipo not in ("artista", "cancion") or not nombre or (tipo == "cancion" and not artista):
        return jsonify({"encontrado": False, "error": "Falta el artista o la canción."}), 400
    if not api_key:
        return jsonify({"encontrado": False, "error": "Falta configurar la clave de Gemini (GEMINI_API_KEY) en Windows."}), 503

    if tipo == "artista":
        instruccion = (
            "Escribe en español un resumen biográfico breve y una curiosidad interesante y verificable "
            "sobre el artista o grupo indicado. Separa en dos apartados: «Resumen de su vida» y «Curiosidad». "
            "En grupos, resume la historia del grupo en vez de inventar una vida individual. "
        )
        objetivo = "Artista o grupo: " + nombre
    else:
        instruccion = (
            "Explica en español algo interesante y concreto sobre la canción indicada y su relación con el artista: "
            "contexto de creación o publicación, significado conocido, historia o impacto cultural. "
            "No inventes interpretaciones como si fueran declaraciones confirmadas. "
        )
        objetivo = "Canción: " + nombre + "\nArtista: " + artista
    prompt = (
        instruccion + "\nUsa búsqueda web para comprobar los datos. Si no encuentras fuentes fiables que "
        "confirmen que la persona/grupo o canción corresponde exactamente a la consulta, responde únicamente "
        "con el texto exacto NO_ENCONTRADO. No rellenes huecos inventando hechos. Máximo 130 palabras.\n\n"
        + objetivo
    )
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 450}
        }
        req = Request(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key,
                     "User-Agent": "MiRadarMusical/1.0"},
            method="POST"
        )
        with urlopen(req, timeout=25) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        candidatos = datos.get("candidates") or []
        partes = ((candidatos[0].get("content") or {}).get("parts") or []) if candidatos else []
        resumen = " ".join(str(p.get("text") or "").strip() for p in partes if p.get("text")).strip()
        if not resumen or "NO_ENCONTRADO" in resumen.upper():
            return jsonify({"encontrado": False, "error": "No se ha encontrado información fiable sobre este resultado."})
        # Solo se presentan enlaces que Gemini devuelve como fuentes de búsqueda.
        fuentes = []
        meta = candidatos[0].get("groundingMetadata") or {}
        for chunk in meta.get("groundingChunks") or []:
            web_info = chunk.get("web") or {}
            url_fuente = web_info.get("uri") or ""
            titulo_fuente = web_info.get("title") or "Fuente consultada"
            if url_fuente.startswith("https://") and all(x.get("url") != url_fuente for x in fuentes):
                fuentes.append({"titulo": titulo_fuente, "url": url_fuente})
        if not fuentes:
            return jsonify({"encontrado": False, "error": "Gemini no ha encontrado fuentes web que permitan verificar la información."})
        return jsonify({"encontrado": True, "resumen": resumen, "fuentes": fuentes[:4]})
    except HTTPError as error:
        # Mostrar el código real de Gemini para distinguir errores de modelo, clave y cuota.
        cuerpo = error.read().decode("utf-8", errors="replace")
        try:
            detalle = json.loads(cuerpo).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            detalle = ""
        app.logger.warning("Gemini HTTP %s para %s: %s", error.code, nombre, detalle or cuerpo[:500])
        mensajes = {
            400: "Gemini rechazó la petición (HTTP 400).",
            401: "Gemini no ha aceptado la autenticación (HTTP 401). Revisa que la clave configurada sea válida.",
            403: "Gemini ha denegado el acceso (HTTP 403). Revisa los permisos o el acceso a la API.",
            404: "Gemini no encuentra el modelo o recurso solicitado (HTTP 404).",
            429: "Gemini ha aplicado un límite de uso o cuota (HTTP 429).",
        }
        mensaje = mensajes.get(error.code, f"Gemini ha respondido con HTTP {error.code}.")
        if detalle:
            mensaje += " Detalle: " + detalle[:500]
        return jsonify({"encontrado": False, "error": mensaje, "codigo": error.code}), 502
    except Exception:
        app.logger.exception("Error consultando Gemini para %s", nombre)
        return jsonify({"encontrado": False, "error": "Fallo de conexión al consultar Gemini. Consulta los registros de Render para ver el detalle."}), 502


# Caché breve de Wikipedia: evita repetir consultas externas para las mismas canciones/artistas.
_cache_wikipedia = {}
_candado_cache_wikipedia = threading.Lock()

def cache_respuesta_wikipedia(vista):
    def envoltura(*args, **kwargs):
        tipo = (request.args.get("tipo") or "").strip().lower()
        nombre = re.sub(r"\s+", " ", (request.args.get("nombre") or "").strip())[:180]
        artista = re.sub(r"\s+", " ", (request.args.get("artista") or "").strip())[:180]
        clave = (tipo, unicodedata.normalize("NFKD", nombre).casefold(), unicodedata.normalize("NFKD", artista).casefold())
        ahora = time.time()
        with _candado_cache_wikipedia:
            entrada = _cache_wikipedia.get(clave)
            if entrada and entrada[0] > ahora:
                return jsonify(entrada[1]), entrada[2]
            if entrada:
                _cache_wikipedia.pop(clave, None)
        salida = vista(*args, **kwargs)
        try:
            respuesta, estado = salida if isinstance(salida, tuple) else (salida, 200)
            datos = respuesta.get_json()
            if isinstance(datos, dict):
                # Las biografías verificadas duran 30 min; los fallos/no coincidencias, 1 min.
                ttl = 1800 if datos.get("fuente_tipo") == "wikipedia" and datos.get("encontrado") else 60
                with _candado_cache_wikipedia:
                    _cache_wikipedia[clave] = (time.time() + ttl, datos, estado)
                    if len(_cache_wikipedia) > 500:
                        vencidas = [k for k, v in _cache_wikipedia.items() if v[0] <= time.time()]
                        for k in vencidas:
                            _cache_wikipedia.pop(k, None)
                        while len(_cache_wikipedia) > 500:
                            _cache_wikipedia.pop(next(iter(_cache_wikipedia)))
        except Exception:
            # La caché nunca debe impedir que se entregue una respuesta válida.
            pass
        return salida
    envoltura.__name__ = vista.__name__
    return envoltura


@app.get("/api/wikipedia")
@cache_respuesta_wikipedia
def api_wikipedia():
    """Busca datos musicales y descarta páginas que no correspondan al artista o canción consultados."""
    tipo = (request.args.get("tipo") or "").strip().lower()
    nombre = re.sub(r"\s+", " ", (request.args.get("nombre") or "").strip())[:180]
    artista = re.sub(r"\s+", " ", (request.args.get("artista") or "").strip())[:180]
    if tipo not in ("artista", "cancion") or not nombre or (tipo == "cancion" and not artista):
        return jsonify({"encontrado": False, "fuente_tipo": "ninguna", "error": "Faltan el nombre o el artista de la canción."}), 400

    cabeceras = {"User-Agent": "MiRadarMusical/4.2 (comprobación de identidad musical)"}

    def normalizar(texto):
        texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii").casefold()
        return re.sub(r"[^a-z0-9]+", " ", texto).strip()

    def contiene_frase(texto, frase):
        t, f = " " + normalizar(texto) + " ", " " + normalizar(frase) + " "
        return bool(f.strip()) and f in t

    terminos_musicales = (
        "cantante", "cantautor", "cantautora", "musico", "musica", "grupo musical",
        "banda", "vocalista", "compositor", "compositora", "interprete", "rapero",
        "rapera", "artista musical", "discografia", "album", "sencillo", "cancion",
        "pop", "flamenco", "regueton", "rock", "orquesta", "duo musical", "solista",
        "guitarrista", "baterista", "productor musical", "productora musical"
    )
    indicadores_no_musicales = (
        # Profesiones y ámbitos que suelen producir homónimos en las búsquedas.
        "jugador de balonmano", "jugadora de balonmano", "handball player",
        "futbolista", "footballer", "soccer player", "baloncestista",
        "basketball player", "tenista", "tennis player", "atleta olimpico",
        "atleta olimpica", "olympic athlete", "politico", "politica",
        "politician", "ministro", "ministra", "presidente de", "militar",
        "actor pornografico", "handball", "balonmano"
    )

    def es_musical(texto):
        n = normalizar(texto)
        return any(normalizar(p) in n for p in terminos_musicales)

    def es_claramente_otro_ambito(texto):
        n = normalizar(texto)
        return any(normalizar(p) in n for p in indicadores_no_musicales)

    # Frases típicas de páginas de desambiguación o artículos sobre nombres,
    # que no deben confundirse con la biografía de un cantante (p. ej. Camilo).
    indicadores_desambiguacion = (
        "es un nombre de pila", "es tanto un nombre", "nombre de pila y un apellido",
        "personas notables con el nombre", "puede referirse a", "puede hacer referencia a",
        "este nombre puede referirse", "is a given name", "given name and surname",
        "notable people with the name", "may refer to", "may also refer to"
    )

    def es_desambiguacion(texto):
        n = normalizar(texto)
        return any(normalizar(p) in n for p in indicadores_desambiguacion)

    def respuesta_ok(titulo, extracto, url, idioma="es"):
        texto = re.sub(r"\s+", " ", str(extracto or "")).strip()
        if not texto:
            return None

        # En vez del resumen de una frase de la API REST, recuperar el artículo
        # de Wikipedia y mostrar sus primeras 300 palabras. Se consulta la misma
        # página validada para evitar rellenar con información de un homónimo.
        try:
            params_articulo = urlencode({
                "action": "query", "prop": "extracts", "explaintext": "1",
                "exchars": "15000", "titles": titulo, "redirects": "1",
                "format": "json", "utf8": "1"
            })
            req_articulo = Request(
                "https://" + idioma + ".wikipedia.org/w/api.php?" + params_articulo,
                headers=cabeceras
            )
            with urlopen(req_articulo, timeout=8) as resp:
                paginas = json.loads(resp.read().decode("utf-8")).get("query", {}).get("pages", {})
            for pagina in paginas.values():
                articulo = re.sub(r"\s+", " ", str(pagina.get("extract") or "")).strip()
                if articulo and len(articulo) > len(texto):
                    texto = articulo
                    break
        except Exception as error:
            app.logger.info("No se pudo recuperar el artículo completo de %s: %s", titulo, error)

        # Limitar por palabras, no por caracteres: unas 300 palabras de contenido real.
        palabras = texto.split()
        texto = " ".join(palabras[:300])

        if idioma == "en":
            try:
                # Traducir en fragmentos para no cortar la biografía a mitad del texto.
                fragmentos = []
                restante = texto
                while restante:
                    trozo = restante[:1800]
                    corte = trozo.rfind(" ")
                    if corte > 900 and len(restante) > 1800:
                        trozo = trozo[:corte]
                    params = urlencode({
                        "client": "gtx", "sl": "en", "tl": "es", "dt": "t", "q": trozo
                    })
                    req = Request(
                        "https://translate.googleapis.com/translate_a/single?" + params,
                        headers=cabeceras
                    )
                    with urlopen(req, timeout=6) as resp:
                        traduccion = json.loads(resp.read().decode("utf-8"))
                    traducido = "".join(
                        str(p[0]) for p in (traduccion[0] or []) if p and p[0]
                    ).strip()
                    if not traducido:
                        raise ValueError("La traducción devolvió un texto vacío")
                    fragmentos.append(traducido)
                    restante = restante[len(trozo):].lstrip()
                texto = " ".join(fragmentos)
            except Exception as error:
                app.logger.info("No se pudo traducir completamente %s: %s", titulo, error)
                # No presentar una traducción parcial como si estuviera completa.
                return jsonify({
                    "encontrado": True,
                    "resumen": "He encontrado la página de Wikipedia, pero no he podido traducir el artículo completo al español.",
                    "titulo": titulo, "url": url,
                    "fuentes": [{"titulo": "Abrir artículo de Wikipedia", "url": url}],
                    "fuente_tipo": "wikipedia", "mensaje": "Traducción no disponible."
                }), 200

        fuente = "Wikipedia en español" if idioma == "es" else "Wikipedia en inglés (traducida al español)"
        return jsonify({
            "encontrado": True, "resumen": texto, "titulo": titulo, "url": url,
            "biografia": texto if tipo == "artista" else "",
            "informacion": texto if tipo == "cancion" else "",
            "idioma": idioma, "fuente": fuente,
            "fuentes": [{"titulo": fuente, "url": url}],
            "fuente_tipo": "wikipedia", "traducido": idioma == "en",
            "tipo_contenido": "biografia" if tipo == "artista" else "informacion_cancion"
        })

    nombre_n = normalizar(nombre)
    artista_n = normalizar(artista)

    def resultado_valido(titulo, extracto):
        titulo_n = normalizar(titulo)
        texto_n = normalizar(titulo + " " + extracto)
        if tipo == "artista":
            # El título debe identificar a la persona/grupo buscado.
            titulo_coincide = (titulo_n == nombre_n or titulo_n.startswith(nombre_n + " ") or nombre_n.startswith(titulo_n + " "))
            if not titulo_coincide:
                return False
            # No aceptar páginas de desambiguación/nombres propios como si fueran artistas.
            if es_desambiguacion(titulo + " " + extracto):
                return False
            # Aceptar una referencia musical y rechazar homónimos de otra profesión.
            if es_musical(extracto):
                return True
            if es_claramente_otro_ambito(extracto):
                return False
            # Si el extracto no confirma que sea un artista, no dar por válida la página
            # solo porque el título coincida; la búsqueda alternativa probará otros resultados.
            return False
        # Para canciones exigimos el título de la canción y alguna referencia al artista o a música.
        cancion_coincide = (titulo_n == nombre_n or titulo_n.startswith(nombre_n + " ") or nombre_n.startswith(titulo_n + " "))
        artista_mencionado = contiene_frase(titulo + " " + extracto, artista)
        return cancion_coincide and artista_mencionado and es_musical(extracto)

    # Intentar páginas exactas, pero no aceptar una coincidencia solo por compartir nombre.
    titulos_directos = [nombre]
    if tipo == "cancion":
        titulos_directos = [nombre + " (canción)", nombre + " (" + artista + " canción)", nombre]
    for idioma in ("es", "en"):
        for titulo_busqueda in titulos_directos:
            try:
                url_api = "https://" + idioma + ".wikipedia.org/api/rest_v1/page/summary/" + quote(titulo_busqueda.replace(" ", "_"), safe="()_,.-")
                req = Request(url_api, headers=cabeceras)
                with urlopen(req, timeout=5) as resp:
                    dato = json.loads(resp.read().decode("utf-8"))
                titulo_real = str(dato.get("title") or titulo_busqueda)
                extracto = str(dato.get("extract") or "")
                pagina = ((dato.get("content_urls") or {}).get("desktop") or {}).get("page") or ("https://" + idioma + ".wikipedia.org/wiki/" + quote(titulo_real.replace(" ", "_"), safe="()_,.-"))
                if dato.get("type") == "disambiguation" or not resultado_valido(titulo_real, extracto):
                    continue
                salida = respuesta_ok(titulo_real, extracto, pagina, idioma)
                if salida:
                    return salida
            except Exception as error:
                app.logger.info("Resumen directo Wikipedia descartado/no disponible (%s): %s", titulo_busqueda, error)

    # Búsqueda flexible: solo se aceptan resultados que superen la misma comprobación de identidad.
    for idioma in ("es", "en"):
        if tipo == "artista":
            consultas = [nombre + " cantante", nombre + " músico", nombre + " grupo musical"]
        else:
            consultas = ['"' + nombre + '" "' + artista + '"', nombre + " " + artista + " canción"]
        for consulta in consultas:
            try:
                params = urlencode({"action": "query", "list": "search", "srsearch": consulta,
                                    "srnamespace": "0", "srlimit": "8", "format": "json", "utf8": "1"})
                req = Request("https://" + idioma + ".wikipedia.org/w/api.php?" + params, headers=cabeceras)
                with urlopen(req, timeout=6) as resp:
                    resultados = json.loads(resp.read().decode("utf-8")).get("query", {}).get("search", [])
                for resultado in resultados:
                    titulo_real = str(resultado.get("title") or "").strip()
                    if not titulo_real:
                        continue
                    params = urlencode({"action": "query", "prop": "extracts|info", "explaintext": "1",
                                        "exintro": "1", "exchars": "1800", "inprop": "url",
                                        "titles": titulo_real, "redirects": "1", "format": "json", "utf8": "1"})
                    req = Request("https://" + idioma + ".wikipedia.org/w/api.php?" + params, headers=cabeceras)
                    with urlopen(req, timeout=6) as resp:
                        pages = json.loads(resp.read().decode("utf-8")).get("query", {}).get("pages", {})
                    for page in pages.values():
                        extracto = str(page.get("extract") or "").strip()
                        titulo_pagina = str(page.get("title") or titulo_real)
                        if not extracto or not resultado_valido(titulo_pagina, extracto):
                            continue
                        url_pagina = page.get("fullurl") or ("https://" + idioma + ".wikipedia.org/wiki/" + quote(titulo_pagina.replace(" ", "_"), safe="()_,.-"))
                        salida = respuesta_ok(titulo_pagina, extracto, url_pagina, idioma)
                        if salida:
                            return salida
            except Exception as error:
                app.logger.info("Búsqueda Wikipedia descartada/no disponible (%s): %s", consulta, error)

    # Sin coincidencia fiable: ofrecer una búsqueda específica, nunca una biografía de un homónimo.
    consulta_web = (nombre + " " + artista + " canción historia" if tipo == "cancion" else nombre + " cantante OR grupo musical biografía")
    url_busqueda = "https://www.google.com/search?" + urlencode({"q": consulta_web, "hl": "es"})
    return jsonify({
        "encontrado": True,
        "resumen": "No he encontrado una biografía musical que pueda confirmar como perteneciente a este artista. Pulsa «Buscar información en español» para consultar resultados más específicos.",
        "fuentes": [{"titulo": "Buscar información en español", "url": url_busqueda}],
        "fuente_tipo": "busqueda_web", "mensaje": "No se mostró una coincidencia dudosa."
    }), 200


# Fichas musicales reutilizables. La ruta de la base de datos se puede fijar
# con MR_FICHAS_DB para usar un disco persistente en el servicio de alojamiento.
_RUTA_FICHAS_DB = Path(os.environ.get("MR_FICHAS_DB", str(BASE.parent / "fichas_musicales.sqlite3")))
_CANDADO_FICHAS_DB = threading.Lock()
_CANDADO_MUSICBRAINZ = threading.Lock()
_ULTIMA_PETICION_MUSICBRAINZ = 0.0
_CANDADOS_FICHA = {}
_CANDADOS_FICHA_LOCK = threading.Lock()


def _inicializar_db_fichas():
    try:
        _RUTA_FICHAS_DB.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(_RUTA_FICHAS_DB), timeout=5) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS fichas_musicales (
                    clave TEXT PRIMARY KEY,
                    datos TEXT NOT NULL,
                    actualizado REAL NOT NULL
                )
            """)
            db.commit()
        return True
    except Exception as error:
        app.logger.warning("No se pudo inicializar la base de fichas: %s", error)
        return False


def _leer_ficha_guardada(clave):
    try:
        with _CANDADO_FICHAS_DB:
            with sqlite3.connect(str(_RUTA_FICHAS_DB), timeout=5) as db:
                fila = db.execute(
                    "SELECT datos FROM fichas_musicales WHERE clave = ?", (clave,)
                ).fetchone()
        return json.loads(fila[0]) if fila else None
    except Exception as error:
        app.logger.warning("No se pudo leer la caché de fichas: %s", error)
        return None


def _guardar_ficha(clave, datos):
    try:
        serializado = json.dumps(datos, ensure_ascii=False)
        with _CANDADO_FICHAS_DB:
            with sqlite3.connect(str(_RUTA_FICHAS_DB), timeout=5) as db:
                db.execute(
                    "INSERT INTO fichas_musicales(clave, datos, actualizado) VALUES(?, ?, ?) "
                    "ON CONFLICT(clave) DO UPDATE SET datos=excluded.datos, actualizado=excluded.actualizado",
                    (clave, serializado, time.time())
                )
                db.commit()
        return True
    except Exception as error:
        app.logger.warning("No se pudo guardar la ficha musical: %s", error)
        return False


def _consulta_json(url, user_agent="MiRadarMusical/1.0 (fichas musicales; contacto: configuracion del sitio)"):
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(req, timeout=7) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _musicbrainz_consultar(url):
    global _ULTIMA_PETICION_MUSICBRAINZ
    # Coordina también entre procesos Gunicorn mediante SQLite, no solo con un lock local.
    with _CANDADO_MUSICBRAINZ:
        try:
            _RUTA_FICHAS_DB.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(_RUTA_FICHAS_DB), timeout=15) as db:
                db.execute("CREATE TABLE IF NOT EXISTS musicbrainz_rate_limit (id INTEGER PRIMARY KEY CHECK(id=1), ultima_peticion REAL NOT NULL)")
                db.execute("BEGIN IMMEDIATE")
                fila = db.execute("SELECT ultima_peticion FROM musicbrainz_rate_limit WHERE id=1").fetchone()
                ahora = time.time()
                if fila:
                    espera = 1.05 - (ahora - float(fila[0]))
                    if espera > 0:
                        time.sleep(espera)
                momento = time.time()
                db.execute("INSERT INTO musicbrainz_rate_limit(id, ultima_peticion) VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET ultima_peticion=excluded.ultima_peticion", (momento,))
                db.commit()
        except Exception as error:
            app.logger.warning("No se pudo coordinar el límite de MusicBrainz en SQLite: %s", error)
            espera = 1.05 - (time.monotonic() - _ULTIMA_PETICION_MUSICBRAINZ)
            if espera > 0:
                time.sleep(espera)
        try:
            return _consulta_json(url, "MiRadarMusical/1.0 (fichas musicales)")
        finally:
            _ULTIMA_PETICION_MUSICBRAINZ = time.monotonic()


def _limitar_palabras(texto, maximo=180):
    palabras = str(texto or "").split()
    return " ".join(palabras[:maximo])


def _lastfm_consultar(metodo, parametros):
    clave_api = os.environ.get("LASTFM_API_KEY", "").strip()
    if not clave_api:
        return None
    valores = dict(parametros)
    valores.update({"method": metodo, "api_key": clave_api, "format": "json", "autocorrect": "1"})
    try:
        return _consulta_json("https://ws.audioscrobbler.com/2.0/?" + urlencode(valores))
    except Exception as error:
        app.logger.info("Last.fm no disponible para %s: %s", metodo, error)
        return None


def _texto_lastfm(valor):
    if isinstance(valor, dict):
        return re.sub(r"<[^>]*>", " ", str(valor.get("#text") or "")).strip()
    return re.sub(r"<[^>]*>", " ", str(valor or "")).strip()


@app.get("/api/ficha-musical")
def api_ficha_musical():
    tipo = (request.args.get("tipo") or "").strip().lower()
    nombre = re.sub(r"\s+", " ", (request.args.get("nombre") or "").strip())[:180]
    artista = re.sub(r"\s+", " ", (request.args.get("artista") or "").strip())[:180]
    if tipo not in ("artista", "cancion") or not nombre or (tipo == "cancion" and not artista):
        return jsonify({"error": "Indica si es artista o canción, el nombre y, para canciones, el artista."}), 400

    def normalizar_clave(valor):
        return unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode("ascii").casefold().strip()

    clave = "|".join((tipo, normalizar_clave(nombre), normalizar_clave(artista)))
    if not _inicializar_db_fichas():
        app.logger.warning("La ficha seguirá disponible sin almacenamiento duradero en esta petición.")

    guardado = _leer_ficha_guardada(clave)
    if guardado and guardado.get("version") == 1:
        guardado["desde_cache"] = True
        return jsonify(guardado)

    with _CANDADOS_FICHA_LOCK:
        candado = _CANDADOS_FICHA.setdefault(clave, threading.Lock())
    with candado:
        guardado = _leer_ficha_guardada(clave)
        if guardado and guardado.get("version") == 1:
            guardado["desde_cache"] = True
            return jsonify(guardado)

        fuentes = []
        datos = {
            "version": 1, "tipo": tipo, "nombre": nombre, "artista": artista,
            "biografia": "", "historia": "", "curiosidad": "",
            "datos_musicales": {}, "fuentes": [], "avisos": [],
            "encontrado": False, "desde_cache": False
        }

        # MusicBrainz aporta identificación y metadatos estructurados, no relatos inventados.
        try:
            if tipo == "artista":
                consulta = urlencode({"query": nombre, "fmt": "json", "limit": "5"})
                mb = _musicbrainz_consultar("https://musicbrainz.org/ws/2/artist/?" + consulta)
                candidatos = mb.get("artists", [])
                esperado = normalizar_clave(nombre)
                candidato = next((x for x in candidatos if normalizar_clave(x.get("name", "")) == esperado), None)
                if candidato:
                    datos["datos_musicales"].update({
                        "nombre_oficial": candidato.get("name", ""),
                        "tipo_artista": candidato.get("type", ""),
                        "pais": candidato.get("country", ""),
                        "formado_o_nacido": candidato.get("life-span", {}).get("begin", ""),
                        "disuelto_o_fallecido": candidato.get("life-span", {}).get("end", ""),
                        "musicbrainz_id": candidato.get("id", "")
                    })
                    fuentes.append({"titulo": "MusicBrainz — ficha del artista", "url": "https://musicbrainz.org/artist/" + candidato["id"]})
            else:
                consulta = urlencode({"query": 'recording:"' + nombre + '" AND artist:"' + artista + '"', "fmt": "json", "limit": "5"})
                mb = _musicbrainz_consultar("https://musicbrainz.org/ws/2/recording/?" + consulta)
                candidatos = mb.get("recordings", [])
                n_cancion, n_artista = normalizar_clave(nombre), normalizar_clave(artista)
                candidato = next((x for x in candidatos if normalizar_clave(x.get("title", "")) == n_cancion and any(normalizar_clave(a.get("name", "")) == n_artista for a in x.get("artist-credit", []) if isinstance(a, dict))), None)
                if candidato:
                    creditos = candidato.get("artist-credit", [])
                    artistas_mb = " ".join(str(a.get("name", "")) for a in creditos if isinstance(a, dict))
                    releases = candidato.get("releases", [])
                    datos["datos_musicales"].update({
                        "titulo_oficial": candidato.get("title", ""),
                        "artista_creditado": artistas_mb,
                        "fecha_publicacion": (releases[0].get("date", "") if releases else ""),
                        "album": (releases[0].get("title", "") if releases else ""),
                        "musicbrainz_id": candidato.get("id", "")
                    })
                    fuentes.append({"titulo": "MusicBrainz — grabación", "url": "https://musicbrainz.org/recording/" + candidato["id"]})
        except Exception as error:
            app.logger.info("MusicBrainz no disponible para %s: %s", nombre, error)
            datos["avisos"].append("No se ha podido consultar MusicBrainz ahora mismo.")

        # Last.fm solo se consulta cuando el administrador ha configurado una clave válida.
        try:
            if tipo == "artista":
                last = _lastfm_consultar("artist.getinfo", {"artist": nombre, "lang": "es"})
                info = (last or {}).get("artist", {})
                wiki = info.get("bio", {}).get("content", "") or info.get("bio", {}).get("summary", "")
                wiki = re.sub(r"<a\b[^>]*>.*?</a>", "", str(wiki), flags=re.I | re.S)
                wiki = re.sub(r"<[^>]*>", " ", wiki).strip()
                if wiki:
                    datos["biografia"] = wiki[:4000]
                    url_last = info.get("url") or ("https://www.last.fm/music/" + quote(nombre.replace(" ", "+")))
                    fuentes.append({"titulo": "Last.fm — información del artista", "url": url_last})
            else:
                last = _lastfm_consultar("track.getinfo", {"artist": artista, "track": nombre})
                track = (last or {}).get("track", {})
                album = track.get("album", {}) if isinstance(track.get("album"), dict) else {}
                if track:
                    datos["datos_musicales"].setdefault("album", album.get("title", ""))
                    datos["datos_musicales"]["oyentes_lastfm"] = track.get("listeners", "")
                    datos["datos_musicales"]["reproducciones_lastfm"] = track.get("playcount", "")
                    url_last = track.get("url") or ("https://www.last.fm/music/" + quote(artista.replace(" ", "+")) + "/_/" + quote(nombre.replace(" ", "+")))
                    fuentes.append({"titulo": "Last.fm — información de la canción", "url": url_last})
                    wiki = track.get("wiki", {}) if isinstance(track.get("wiki"), dict) else {}
                    historia = wiki.get("content", "") or wiki.get("summary", "")
                    historia = re.sub(r"<a\b[^>]*>.*?</a>", "", str(historia), flags=re.I | re.S)
                    historia = re.sub(r"<[^>]*>", " ", historia).strip()
                    if historia:
                        datos["historia"] = historia[:4000]
        except Exception as error:
            app.logger.info("Last.fm no disponible para %s: %s", nombre, error)
            datos["avisos"].append("Last.fm no ha devuelto información para esta consulta.")

        # Reutiliza la comprobación de identidad de la ruta de Wikipedia ya existente.
        try:
            with app.test_request_context(
                "/api/wikipedia?" + urlencode({"tipo": tipo, "nombre": nombre, "artista": artista})
            ):
                respuesta_wiki = api_wikipedia()
                resp, status = respuesta_wiki if isinstance(respuesta_wiki, tuple) else (respuesta_wiki, 200)
                wiki = resp.get_json() if hasattr(resp, "get_json") else {}
            if status < 400 and wiki and wiki.get("encontrado") and wiki.get("fuente_tipo") == "wikipedia":
                texto_wiki = str(wiki.get("resumen") or "").strip()
                if tipo == "artista" and not datos["biografia"]:
                    datos["biografia"] = texto_wiki[:4000]
                elif tipo == "cancion" and not datos["historia"]:
                    datos["historia"] = texto_wiki[:4000]
                for fuente in wiki.get("fuentes", []):
                    if fuente.get("url"):
                        fuentes.append(fuente)
                datos["encontrado"] = bool(texto_wiki or datos["datos_musicales"])
        except Exception as error:
            app.logger.info("Wikipedia no disponible para la ficha %s: %s", nombre, error)
            datos["avisos"].append("Wikipedia no ha podido consultarse ahora mismo.")

        datos["biografia"] = _limitar_palabras(datos["biografia"], 180)
        datos["historia"] = _limitar_palabras(datos["historia"], 180)

        # No se fabrican curiosidades: hasta integrar una fuente documentada, se indica claramente.
        if not datos["curiosidad"]:
            datos["avisos"].append("No se muestra una curiosidad porque todavía no hay una fuente documental específica confirmada.")

        unicas = []
        urls = set()
        for fuente in fuentes:
            url = str(fuente.get("url") or "").strip()
            if url and url not in urls:
                urls.add(url)
                unicas.append({"titulo": str(fuente.get("titulo") or "Fuente original"), "url": url})
        datos["fuentes"] = unicas
        datos["encontrado"] = bool(datos["biografia"] or datos["historia"] or datos["datos_musicales"])
        datos["guardado"] = _guardar_ficha(clave, datos) if datos["encontrado"] else False
        return jsonify(datos)


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