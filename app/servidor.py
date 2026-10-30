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
from concurrent.futures import ThreadPoolExecutor, as_completed
import unicodedata
import difflib
import random
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
        # Solo estas cuatro secciones necesitan el ajuste: las otras páginas ya coinciden visualmente.
        if request.path.rstrip("/") in ("/lo-mejor", "/mi-musica", "/programas"):
            css_cabecera = """
/* Las cuatro secciones usan la misma geometría de cabecera que Portada.
   Se conserva el fondo y los colores propios de cada sección. */
header{
  position:relative!important;
  box-sizing:border-box!important;
  height:auto!important;
  min-height:0!important;
  max-height:none!important;
  display:block!important;
  padding:32px 6%!important;
  overflow:visible!important;
}
header>div,.marca{
  font-size:13px!important;
  font-weight:800!important;
  letter-spacing:3px!important;
  text-transform:uppercase!important;
}
header h1{
  font-size:clamp(32px,6vw,58px)!important;
  line-height:normal!important;
  margin:12px 0 8px!important;
}
header p{
  display:block!important;
  margin:0!important;
  max-width:none!important;
  overflow:visible!important;
  -webkit-line-clamp:unset!important;
  -webkit-box-orient:initial!important;
}
"""
            css_nav = css_nav.replace("</style>", css_cabecera + "\n</style>", 1)
        if "</head>" in html:
            # Elimina declaraciones antiguas o duplicadas: Android/Chrome puede
            # elegir el primer icono/manifiesto y conservar un acceso directo obsoleto.
            html = re.sub(
                r'<link\b(?=[^>]*\brel=["\'](?:icon|apple-touch-icon|manifest)["\'])[^>]*>\s*',
                "",
                html,
                flags=re.IGNORECASE,
            )
            enlaces_marca = """
<link rel="icon" type="image/png" sizes="192x192" href="/icono-mrm-192.png?v=13">
<link rel="icon" type="image/svg+xml" href="/icono-mrm.svg?v=13">
<link rel="apple-touch-icon" sizes="192x192" href="/icono-mrm-192.png?v=13">
<link rel="manifest" href="/manifest.webmanifest?v=13">
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
        script_guardadas_global = r"""
<script id="mr-guardadas-global">
(function(){
 const esRecomendaciones=location.pathname==='/recomendaciones';
 const clave=c=>String(c.artista||'').trim().toLocaleLowerCase('es')+' — '+String(c.titulo||'').trim().toLocaleLowerCase('es');
 const leer=()=>{try{const a=JSON.parse(localStorage.getItem('miRadarMusical_recomendacionesGuardadas_v1')||'[]');return Array.isArray(a)?a:[]}catch(e){return[]}};
 const escribir=a=>{try{localStorage.setItem('miRadarMusical_recomendacionesGuardadas_v1',JSON.stringify(a))}catch(e){}};
 const habilitado=()=>{try{return localStorage.getItem('mrGuardarEnabled')==='1'}catch(e){return false}};
 const svgPlay='<svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17"><path d="M8 5.5v13l10-6.5z" fill="currentColor"/></svg>';
 const svgDownload='<svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20"><path d="M12 3v11m-5-5 5 5 5-5M4 17v3h16v-3" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 const estilo=document.createElement('style');
 estilo.textContent=
 'body[data-wikipedia-off="1"] .wiki-icon,body[data-wikipedia-off="1"] .boton-wikipedia,body[data-wikipedia-off="1"] .wiki,body[data-wikipedia-off="1"] .info-btn{display:none!important}'+
 '.wiki-icon,.boton-wikipedia,.wiki,.info-btn{width:24px!important;height:24px!important;min-width:24px!important;max-width:24px!important;padding:0!important;margin-left:5px!important;border-radius:50%!important;font-size:13px!important;line-height:1!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;vertical-align:middle!important}'+
 '.mr-agregar,.guardar-btn{display:none!important}.mr-agregar.mr-visible,.guardar-btn.mr-visible{display:inline-flex!important;align-items:center!important;justify-content:center!important;width:29px!important;height:29px!important;min-width:29px!important;padding:0!important;margin:0 0 0 6px!important;border:1px solid #8eb8ff!important;border-radius:6px!important;background:#1769d2!important;color:white!important;font-size:21px!important;font-weight:900!important;line-height:1!important;cursor:pointer!important}'+
 '.mr-panel-guardadas{margin:24px auto;padding:16px;width:min(1100px,92%);border:1px solid #ffffff30;border-radius:16px;background:#171d2c;color:#fff}'+
 '.mr-pestana-guardadas{display:inline-flex;align-items:center;gap:8px;margin:24px auto 0 4%;padding:10px 17px;border:1px solid #ffffff35;border-radius:22px;background:#ffffff12;color:#fff;font-weight:800;cursor:pointer}'+
 '.mr-pestana-guardadas[aria-expanded="true"]{background:linear-gradient(135deg,#52677f,#8295aa);border-color:#c5d0dc}'+
 '.mr-grid-guardadas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}'+
 '.mr-grid-guardadas[hidden]{display:none!important}'+
 '.mr-cancion-guardada{display:grid;grid-template-columns:112px minmax(0,1fr);gap:14px;padding:13px;background:linear-gradient(125deg,#1b2234,#171c2a);border:1px solid #ffffff20;border-radius:15px;min-width:0}'+
 '.mr-portada-contenedor{width:112px;aspect-ratio:1;position:relative;overflow:hidden;border-radius:10px}.mr-portada-contenedor [hidden]{display:none!important}.mr-cancion-guardada .mr-portada{position:absolute;inset:0;width:100%;height:100%;aspect-ratio:1;object-fit:cover;border-radius:10px;background:#ffffff12;display:flex;align-items:center;justify-content:center;font-size:34px;color:#a6a8bd}'+
 '.mr-cancion-guardada .mr-info{min-width:0}.mr-cancion-guardada .mr-titulo{font-size:16px;font-weight:850;line-height:1.4;overflow-wrap:anywhere}.mr-cancion-guardada .mr-artista{margin-top:5px;color:#ded4f5;font-size:14px;overflow-wrap:anywhere}.mr-cancion-guardada .mr-meta{font-size:12px;color:#aeb2ca;margin-top:7px;line-height:1.5}'+
 '.mr-cancion-guardada .mr-acciones{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}.mr-cancion-guardada .mr-acciones button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-width:40px;min-height:39px;padding:8px 10px;border:1px solid #ffffff2a;border-radius:11px;color:#fff;font-weight:750;cursor:pointer}'+
 '.mr-cancion-guardada .mr-b30{background:linear-gradient(135deg,#7867ff,#9b45cf 52%,#d43e8f)}.mr-cancion-guardada .mr-descarga{background:linear-gradient(135deg,#168653,#20ad70)}.mr-cancion-guardada .mr-youtube{background:linear-gradient(135deg,#ff4545,#d80d20)}.mr-cancion-guardada .mr-quitar{background:linear-gradient(135deg,#238dba,#3862bd);font-size:20px}'+
 '.mr-guardadas-vacio{padding:22px;border:1px dashed #ffffff30;border-radius:14px;color:#d5c2ce;grid-column:1/-1}'+
 '.mr-modal-guardadas[hidden]{display:none!important}.mr-modal-guardadas{position:fixed;inset:0;z-index:50000;background:#000b;display:flex;align-items:center;justify-content:center;padding:16px}.mr-modal-guardadas .mr-caja-modal{width:min(700px,100%);max-height:85vh;overflow:auto;padding:18px;background:#171d2c;border:1px solid #ffffff35;border-radius:16px;color:#fff}.mr-modal-guardadas .mr-cabecera-modal{display:flex;align-items:center;justify-content:space-between;gap:12px}.mr-modal-guardadas h2{font-size:20px;margin:0}.mr-modal-guardadas button{border-radius:10px;padding:9px 12px}.mr-modal-guardadas .mr-resultado{display:block;width:100%;margin:8px 0;text-align:left;background:#243047;color:#fff}.mr-modal-guardadas .mr-resultado span{display:block;margin-top:5px;font-size:12px;color:#b8bad0}.mr-modal-guardadas .mr-texto-modal{white-space:pre-line;line-height:1.65}'+
 '@media(max-width:800px){.mr-grid-guardadas{grid-template-columns:1fr}}@media(max-width:480px){.mr-cancion-guardada{grid-template-columns:82px minmax(0,1fr);gap:10px;padding:10px}.mr-cancion-guardada .mr-portada-contenedor{width:82px!important}.mr-cancion-guardada .mr-portada{width:100%}.mr-cancion-guardada .mr-acciones button{flex:1}.mr-cancion-guardada .mr-titulo{font-size:15px}}';
 document.head.appendChild(estilo);
 const estiloAcciones=document.createElement('style');
 estiloAcciones.textContent='.acciones-radar,.acciones-cancion{grid-template-columns:42px 42px 32px!important;min-width:123px!important}.acciones-radar .mr-agregar,.acciones-cancion .mr-agregar{grid-column:3!important;grid-row:2!important}.acciones-pista{grid-template-columns:82px 42px 42px 32px 42px!important;min-width:264px!important}.acciones-pista .mr-agregar{grid-column:4!important;grid-row:1!important}.acciones-pista .boton-completa{grid-column:5!important;grid-row:1!important}';
 document.head.appendChild(estiloAcciones);
 let panel=null,tab=null,zona=null,modal=null,modalTitulo=null,estadoModal=null,resultadosModal=null;
 if(!esRecomendaciones){
  tab=document.createElement('button');tab.type='button';tab.className='mr-pestana-guardadas';tab.innerHTML='<span aria-hidden="true">▣</span> Guardadas <span id="mr-total-guardadas">0</span>';tab.setAttribute('aria-expanded','false');
  panel=document.createElement('section');panel.className='mr-panel-guardadas';panel.innerHTML='<h2>🎵 Guardadas</h2><div class="mr-grid-guardadas" id="mr-grid-guardadas"></div>';
  zona=panel.querySelector('#mr-grid-guardadas');
  const footer=document.querySelector('footer');
  (footer||document.body).insertAdjacentElement(footer?'beforebegin':'beforeend',tab);
  (footer||document.body).insertAdjacentElement(footer?'beforebegin':'beforeend',panel);
  panel.hidden=true;
  tab.addEventListener('click',()=>{const abierto=!panel.hidden;panel.hidden=abierto;tab.setAttribute('aria-expanded',String(!abierto));if(!abierto){dibujar();panel.scrollIntoView({behavior:'smooth',block:'start'})}});
 }
 function crearModal(){
  if(modal)return;
  modal=document.createElement('div');modal.className='mr-modal-guardadas';modal.hidden=true;modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');
  modal.innerHTML='<div class="mr-caja-modal"><div class="mr-cabecera-modal"><h2 id="mr-modal-titulo">Opciones</h2><button type="button" id="mr-modal-cerrar">Cerrar ✕</button></div><p class="mr-texto-modal" id="mr-modal-estado"></p><div id="mr-modal-resultados"></div></div>';
  document.body.appendChild(modal);modalTitulo=modal.querySelector('#mr-modal-titulo');estadoModal=modal.querySelector('#mr-modal-estado');resultadosModal=modal.querySelector('#mr-modal-resultados');
  modal.querySelector('#mr-modal-cerrar').addEventListener('click',()=>modal.hidden=true);modal.addEventListener('click',e=>{if(e.target===modal)modal.hidden=true});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&modal)modal.hidden=true});
 }
 function abrirModal(t,m){crearModal();modalTitulo.textContent=t;estadoModal.textContent=m;resultadosModal.replaceChildren();modal.hidden=false}
 function boton(texto,clase,titulo,accion){const b=document.createElement('button');b.type='button';b.className=clase;b.innerHTML=texto;b.title=titulo;b.setAttribute('aria-label',titulo);b.addEventListener('click',()=>accion(b));return b}
 async function refrescar(){try{const r=await fetch('/api/recomendaciones/guardadas',{cache:'no-store'});if(r.ok){const d=await r.json();if(Array.isArray(d.canciones)){escribir(d.canciones);return d.canciones}}}catch(e){}return leer()}
 async function guardar(c){let a=leer();if(!a.some(x=>clave(x)===clave(c)))a.unshift(c);escribir(a);try{const r=await fetch('/api/recomendaciones/guardadas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({canciones:[c]})});if(!r.ok)throw new Error();const d=await r.json();if(Array.isArray(d.canciones))escribir(d.canciones)}catch(e){}dibujar();actualizarBotones()}
 async function quitar(c){escribir(leer().filter(x=>clave(x)!==clave(c)));dibujar();actualizarBotones();try{const r=await fetch('/api/recomendaciones/guardadas',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({titulo:c.titulo,artista:c.artista})});if(r.ok){const d=await r.json();if(Array.isArray(d.canciones))escribir(d.canciones);dibujar();actualizarBotones()}}catch(e){}}
 async function buscarVideos(c,modo,b){if(b)b.disabled=true;abrirModal(modo==='youtube'?'Elegir versión de YouTube':'Descargar con MediaHuman','Buscando resultados para '+c.artista+' — '+c.titulo+'…');try{const q=new URLSearchParams({titulo:c.titulo,artista:c.artista});const r=await fetch('/api/youtube/buscar?'+q);const d=await r.json();if(!r.ok)throw new Error(d.error||'No se encontraron resultados.');resultadosModal.replaceChildren();if(!(d.resultados||[]).length)throw new Error('No se encontraron resultados.');estadoModal.textContent=modo==='youtube'?'Pulsa una versión para abrirla en YouTube.':'Elige una versión: se copiará su enlace para pegarlo en MediaHuman YouTube Downloader.';for(const v of d.resultados){const btn=document.createElement('button');btn.type='button';btn.className='mr-resultado';const t=document.createElement('strong');t.textContent=v.titulo||'Vídeo sin título';const sub=document.createElement('span');sub.textContent=v.canal||'Canal desconocido';btn.append(t,sub);btn.addEventListener('click',async()=>{if(modo==='youtube'){window.open(v.url,'_blank','noopener,noreferrer');return}try{await navigator.clipboard.writeText(v.url);estadoModal.textContent='Enlace copiado. Pégalo en MediaHuman YouTube Downloader.';btn.textContent='✓ Enlace copiado: '+(v.titulo||'canción')}catch(e){window.prompt('Copia el enlace para MediaHuman:',v.url)}});resultadosModal.appendChild(btn)}}catch(e){estadoModal.textContent=e.message||'No se pudo consultar YouTube.'}finally{if(b)b.disabled=false}}
 async function escuchar(c,b){if(b)b.disabled=true;const original=b?b.innerHTML:'';if(b)b.textContent='Buscando…';try{let url=c.preview||'',nota='';let artista=c.artista,titulo=c.titulo;if(!url){const q=new URLSearchParams({titulo,artista});const r=await fetch('/api/muestra?'+q);const d=await r.json();if(!r.ok)throw new Error(d.error||'No hay muestra disponible.');url=d.previewUrl;artista=d.artista||artista;titulo=d.titulo||titulo;nota=d.nota||''}if(!url)throw new Error('No hay muestra de 30 segundos disponible para esta canción.');abrirModal('Muestra de 30 segundos',artista+' — '+titulo);if(nota){const aviso=document.createElement('p');aviso.textContent=nota;aviso.style.margin='8px 0';aviso.style.color='#f0c878';resultadosModal.appendChild(aviso)}const audio=document.createElement('audio');audio.controls=true;audio.preload='none';audio.src=url;audio.style.width='100%';resultadosModal.appendChild(audio);await audio.play();setTimeout(()=>{audio.pause();audio.currentTime=0},30000)}catch(e){abrirModal('Muestra no disponible',e.message||'No se ha podido reproducir la muestra.')}finally{if(b){b.disabled=false;b.innerHTML=original}}}
 async function informacion(c,b){if(b)b.disabled=true;abrirModal('Información sobre '+c.titulo,'Consultando información musical…');try{const q=new URLSearchParams({tipo:'cancion',nombre:c.titulo,artista:c.artista});const r=await fetch('/api/resumen-musical?'+q);const d=await r.json();estadoModal.textContent=d.resumen||d.informacion||d.error||'No se ha encontrado información.';for(const f of (d.fuentes||[])){if(!f.url||!f.url.startsWith('https://'))continue;const a=document.createElement('a');a.href=f.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=f.titulo||'Consultar fuente';a.style.display='block';a.style.color='#d2b8ff';resultadosModal.appendChild(a)}}catch(e){estadoModal.textContent='No se ha podido consultar la información ahora mismo.'}finally{if(b)b.disabled=false}}
 function crearTarjeta(c){
  const f=document.createElement('article');f.className='mr-cancion-guardada';
  const miniatura=document.createElement('div');miniatura.className='mr-portada-contenedor';miniatura.style.position='relative';miniatura.style.width='112px';miniatura.style.aspectRatio='1';miniatura.style.overflow='hidden';miniatura.style.borderRadius='10px';
  const img=document.createElement('img');img.className='mr-portada';img.alt='Portada de '+(c.titulo||'la canción');img.loading='lazy';img.decoding='async';img.referrerPolicy='no-referrer';
  const fallback=document.createElement('div');fallback.className='mr-portada';fallback.textContent='♪';fallback.setAttribute('role','img');fallback.setAttribute('aria-label','Portada no disponible');
  if(c.portada){img.src=String(c.portada).replace(/^http:\/\//i,'https://');img.addEventListener('load',()=>{img.hidden=false;fallback.hidden=true});img.addEventListener('error',()=>{img.hidden=true;fallback.hidden=false})}else img.hidden=true;
  if(!c.portada)fallback.hidden=false;
  miniatura.append(img,fallback);
  const info=document.createElement('div');info.className='mr-info';
  const titulo=document.createElement('div');titulo.className='mr-titulo';titulo.textContent=c.anio?c.titulo+' ('+c.anio+')':(c.titulo||'Canción');
  const artista=document.createElement('div');artista.className='mr-artista';artista.textContent=c.artista||'Artista desconocido';
  const meta=document.createElement('div');meta.className='mr-meta';meta.textContent=(c.genero||'Estilo relacionado')+' · Similar a '+(c.relacionado_con||'tus gustos')+(c.album?' · '+c.album:'')+(c.anio?' · Año '+c.anio:'');
  const acciones=document.createElement('div');acciones.className='mr-acciones';
  acciones.append(boton(svgPlay+'<span>30 s</span>','mr-b30','Escuchar muestra de 30 segundos',b=>escuchar(c,b)),boton(svgDownload,'mr-descarga','Buscar enlace para descargar con MediaHuman',b=>buscarVideos(c,'mediahuman',b)),boton(svgPlay,'mr-youtube','Buscar en YouTube',b=>buscarVideos(c,'youtube',b)));
  if(localStorage.getItem('mrWikipediaEnabled')==='1')acciones.append(boton('ℹ','info-btn','Consultar información de la canción',b=>informacion(c,b)));
  acciones.append(boton('−','mr-quitar','Quitar de Guardadas',()=>quitar(c)));
  info.append(titulo,artista,meta,acciones);f.append(miniatura,info);return f;
 }
 function dibujar(){if(!panel)return;const a=leer();tab.querySelector('#mr-total-guardadas').textContent=String(a.length);zona.hidden=false;zona.replaceChildren();if(!a.length){const v=document.createElement('div');v.className='mr-guardadas-vacio';v.textContent='Todavía no has guardado canciones. Pulsa el botón + de cualquier canción para añadirla aquí.';zona.appendChild(v);return}a.forEach(c=>zona.appendChild(crearTarjeta(c)))}
 function datos(n){
  const w=n.querySelector('[data-wiki-tipo="cancion"]'),info=n.querySelector('[data-resumen-tipo="cancion"]');
  const titulo=n.dataset.titulo||w?.dataset.wikiNombre||info?.dataset.resumenNombre||n.querySelector('.pista-titulo,.titulo-cancion,.titulo')?.textContent?.trim()||'';
  const meta=n.querySelector('.pista-meta,.meta')?.textContent||'',partes=meta.split(' · ');
  const artistaBruto=n.dataset.artista||w?.dataset.wikiArtista||info?.dataset.resumenArtista||n.querySelector('.artista-cancion,.artista')?.textContent?.trim()||(meta.includes('Publicación de ')?meta.split('Publicación de ').pop():partes.length>1?partes[1]:partes[0])||'';
  const artista=artistaBruto.replace(/[ℹ]+$/,'').trim();
  const img=n.querySelector('img'),anioEncontrado=meta.match(/(?:19|20)\d{2}/);
  return {titulo:titulo.replace(/^[+ℹ]\s*/,'').trim(),artista,portada:img?.currentSrc||img?.src||'',anio:n.dataset.anio||(anioEncontrado?anioEncontrado[0]:''),genero:n.dataset.genero||(partes.length?partes[0]:''),album:n.dataset.album||''};
 }
 function actualizarBotones(){document.querySelectorAll('.mr-agregar').forEach(b=>{let c={};try{c=JSON.parse(b.dataset.cancion||'{}')}catch(e){}const guardada=leer().some(x=>clave(x)===clave(c));b.textContent=guardada?'✓':'+';b.title=guardada?'Ya está guardada':'Añadir a Guardadas';b.setAttribute('aria-label',b.title);b.classList.toggle('guardada',guardada)})}
 function aplicarVisibilidad(){const on=habilitado();document.body.dataset.wikipediaOff=(localStorage.getItem('mrWikipediaEnabled')==='1'?'0':'1');document.querySelectorAll('.mr-agregar,.guardar-btn').forEach(b=>b.classList.toggle('mr-visible',on))}
 function botones(){
  aplicarVisibilidad();if(esRecomendaciones)return;
  document.querySelectorAll('.tarjeta,.pista,.fila-cancion,.publicacion-mejor,.cancion').forEach(n=>{
   if(n.closest('.mr-panel-guardadas')||n.querySelector('.mr-agregar'))return;
   const c=datos(n);if(!c.titulo||!c.artista)return;
   const b=document.createElement('button');b.type='button';b.className='mr-agregar';b.textContent=leer().some(x=>clave(x)===clave(c))?'✓':'+';b.title='Añadir a Guardadas';b.dataset.cancion=JSON.stringify(c);b.setAttribute('aria-label','Añadir '+c.titulo+' a Guardadas');b.addEventListener('click',()=>guardar(datos(n)));
   const youtube=n.querySelector('.boton-youtube,.youtube,a[href*="youtube.com"],a[href*="youtu.be"]');
   if(youtube)youtube.insertAdjacentElement('afterend',b);else{const acciones=n.querySelector('.acciones-pista,.acciones-radar,.acciones,.acciones-cancion,.acciones-publicacion');if(acciones)acciones.appendChild(b);else n.appendChild(b)}
  });
 }
 dibujar();refrescar().then(a=>{escribir(a);dibujar();actualizarBotones()});botones();new MutationObserver(botones).observe(document.body,{childList:true,subtree:true});window.addEventListener('mrGuardarAjuste',botones);window.addEventListener('storage',e=>{if(e.key==='miRadarMusical_recomendacionesGuardadas_v1'){dibujar();actualizarBotones()}if(e.key==='mrGuardarEnabled'||e.key==='mrWikipediaEnabled')botones()});
})();
</script>
"""
        if "</body>" in html and "mr-guardadas-global" not in html:
            html = html.replace("</body>", script_guardadas_global + "</body>", 1)
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



@app.get("/api/portada/recomendados")
def api_portada_recomendados():
    """Últimas publicaciones de los 50 artistas con más canciones en Mi música."""
    try:
        cantidad = int(request.args.get("cantidad", "12"))
    except (TypeError, ValueError):
        cantidad = 12
    if cantidad not in (12, 32):
        cantidad = 12

    ruta_biblioteca = BASE / "mi_musica.json"
    try:
        with ruta_biblioteca.open("r", encoding="utf-8") as archivo:
            biblioteca = json.load(archivo)
        if not isinstance(biblioteca, list):
            raise ValueError("La biblioteca no contiene una lista.")
    except (OSError, json.JSONDecodeError, ValueError):
        app.logger.exception("No se pudo leer la biblioteca para las publicaciones recomendadas.")
        return jsonify({"error": "No se ha podido leer tu biblioteca musical."}), 503

    conteo_artistas = {}
    for pista in biblioteca:
        if not isinstance(pista, dict):
            continue
        artista = str(pista.get("artista") or "").strip()
        if not artista:
            continue
        clave = normalizar_texto(artista)
        if not clave:
            continue
        entrada = conteo_artistas.setdefault(clave, {"nombre": artista, "total": 0})
        entrada["total"] += 1

    top_artistas = sorted(
        conteo_artistas.items(),
        key=lambda item: (-item[1]["total"], item[1]["nombre"].casefold())
    )[:50]
    claves_top = {clave for clave, _ in top_artistas}

    ruta_portada = BASE / "portada.json"
    try:
        mtime = ruta_portada.stat().st_mtime_ns
        with _candado_cache_portada:
            if _cache_portada["mtime"] != mtime:
                datos = json.loads(ruta_portada.read_text(encoding="utf-8"))
                if not isinstance(datos, list):
                    raise ValueError("El archivo de portada no contiene una lista.")
                _cache_portada["publicaciones"] = datos
                _cache_portada["mtime"] = mtime
            publicaciones = list(_cache_portada["publicaciones"])
    except (OSError, json.JSONDecodeError, ValueError):
        app.logger.exception("No se pudo cargar el catálogo para las publicaciones recomendadas.")
        return jsonify({"error": "No se han podido cargar las publicaciones."}), 503

    filtradas = []
    for publicacion in publicaciones:
        if not isinstance(publicacion, dict):
            continue
        tipo = _tipo_normalizado_portada(publicacion.get("tipo"))
        if tipo not in ("Single", "Album"):
            continue
        artista = normalizar_texto(publicacion.get("artista") or "")
        if not artista or artista not in claves_top:
            continue
        fecha = str(publicacion.get("fecha") or "").strip()
        clave_fecha = _fecha_clave_portada(fecha)
        if fecha and clave_fecha is None:
            continue
        filtradas.append((clave_fecha or (0, 0, 0), publicacion))

    filtradas.sort(
        key=lambda item: (
            bool(item[0][0]),
            item[0],
            str(item[1].get("titulo") or "").casefold()
        ),
        reverse=True
    )
    respuesta = jsonify({
        "tipo": "Recomendados",
        "total_artistas": len(top_artistas),
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
header{box-sizing:border-box;height:152px;min-height:152px;display:flex;flex-direction:column;justify-content:center;overflow:hidden;padding:24px 6%;background:linear-gradient(110deg,#d95a12 0%,#ff982b 65%,#ffd166 100%);color:#281506}
h1{font-size:clamp(32px,6vw,52px);line-height:1.1;margin:10px 0 8px;color:#281506}header p{margin:0;color:#38200d;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
nav{display:flex;gap:10px;flex-wrap:wrap;padding:18px 6%;border-bottom:1px solid #ffffff18}
nav a{color:#e8e5ff;text-decoration:none;background:#ffffff12;padding:10px 15px;border-radius:22px;font-size:14px}
nav a.activo{background:#c94f79;color:#fff;font-weight:bold}
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
<title>Cantantes · Mi Radar Musical</title>
<style>
:root{color-scheme:dark;--suave:#b8b6cf;--panel:#1b1b2d;--verde:#55e6bd}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(140deg,#17152d,#10101c 55%,#26152e);color:#f7f5ff;font-family:Segoe UI,Arial,sans-serif;min-height:100vh}

header{box-sizing:border-box;height:152px;min-height:152px;display:flex;flex-direction:column;justify-content:center;overflow:hidden;padding:24px 6%;background:linear-gradient(110deg,#76233f 0%,#c94f79 65%,#f2a0a0 100%);color:#fff7fa}
h1{font-size:clamp(32px,6vw,52px);line-height:1.1;margin:10px 0 8px;color:#fff7fa}header p{color:#fff0f4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
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
<header><div>Tu universo musical</div><h1>🎤 Cantantes</h1><p>Canciones más populares · Éxitos recientes · Últimas publicaciones</p></header>
<nav><a href="/">🏠 Portada</a><a href="/listas/youtube">▶ YouTube</a><a href="/listas/los40">🎵 LOS40</a><a href="/listas/canal-fiesta">📻 Canal Fiesta</a><a class="activo" href="/lo-mejor">🎤 Cantantes</a><a href="/programas">🧰 Programas</a></nav>
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
   const fila=nodo('div','pista');
   const detalle=nodo('div','');
   const tituloLinea=nodo('div','');
   const tituloPista=nodo('strong','pista-titulo',p.titulo||'Sin título');
   tituloLinea.appendChild(tituloPista);
   const info=nodo('button','boton-wikipedia','I');info.type='button';
   info.title='Consultar información sobre esta publicación';
   info.setAttribute('aria-label','Consultar información sobre '+(p.titulo||'esta publicación'));
   info.addEventListener('click',async()=>{
    if(info.disabled)return;info.disabled=true;info.textContent='…';
    try{
     const resumen=await consultarGemini('cancion',p.titulo||'',nombre);
     if(resumen.encontrado)mostrarInfoWikipedia(fila,resumen,'cancion');
     else{const aviso=nodo('div','info-wikipedia',resumen.mensaje||'No se ha encontrado información sobre esta publicación.');fila.insertAdjacentElement('afterend',aviso);}
    }finally{info.disabled=false;info.textContent='I';}
   });
   tituloLinea.appendChild(info);detalle.appendChild(tituloLinea);
   const meta=[p.fecha,p.tipo].filter(Boolean).join(' · ');
   if(meta)detalle.appendChild(nodo('div','pista-meta',meta+' · Publicación de '+nombre));
   const acciones=nodo('div','acciones-pista');
   const muestra=nodo('button','boton-30','');muestra.innerHTML='<svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" focusable="false"><path d="M8 5.5v13l10-6.5z" fill="currentColor"/></svg><span>30 s</span>';
   muestra.title='Buscar una muestra de 30 segundos de esta publicación';
   muestra.addEventListener('click',async()=>{
    muestra.disabled=true;
    try{
     const r=await fetch('/api/publicaciones/preview?'+new URLSearchParams({artista:nombre,titulo:p.titulo||''}),{cache:'no-store'});
     const d=await r.json();
     if(!r.ok||!d.preview)throw new Error(d.error||'No hay una muestra de 30 segundos disponible para esta publicación.');
     reproducir({preview:d.preview,titulo:d.titulo||p.titulo,artista:nombre},muestra);
    }catch(e){estado.textContent=e.message||'No se ha podido obtener la muestra.';muestra.disabled=false;}
   });
   const mediahuman=nodo('button','boton-mediahuman','');mediahuman.innerHTML='<svg aria-hidden="true" viewBox="0 0 24 24" width="21" height="21" focusable="false"><path d="M12 3v11m-5-5 5 5 5-5M4 17v3h16v-3" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
   mediahuman.title='Buscar enlace para MediaHuman';mediahuman.setAttribute('aria-label','Descargar con MediaHuman');
   mediahuman.addEventListener('click',()=>buscarYouTube({titulo:p.titulo||'',artista:nombre},'mediahuman'));
   const youtube=nodo('button','boton-youtube','');youtube.innerHTML='<svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" focusable="false"><path d="M8 5.5v13l10-6.5z" fill="currentColor"/></svg>';
   youtube.title='Abrir opciones de YouTube';youtube.setAttribute('aria-label','YouTube');
   youtube.addEventListener('click',()=>buscarYouTube({titulo:p.titulo||'',artista:nombre},'youtube'));
   acciones.append(muestra,mediahuman,youtube);fila.append(detalle,acciones);item.appendChild(fila);zona.appendChild(item);
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
   const descripcion=recientes?'Lanzamiento reciente (Deezer + Apple/iTunes)':'Popularidad según '+(d.fuente||'Deezer');
   detalle.appendChild(nodo('div','pista-meta',(pista.fecha||pista.anio||'Fecha no disponible')+' · '+pista.artista+' · '+descripcion+(pista.album?' · '+pista.album:'')));
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
                "anio": anio,
                "fecha": fecha[:10] if len(fecha) >= 4 and fecha[:4].isdigit() else ""
            })

        # Para «Más populares», combinar el ranking de Deezer con Last.fm cuando
        # exista LASTFM_API_KEY. Apple/iTunes se reserva para verificar fechas,
        # porque su endpoint de búsqueda no publica un ranking de popularidad por artista.
        lastfm_usado = False
        if tipo == "populares":
            clave_lastfm = (os.environ.get("LASTFM_API_KEY") or "").strip()
            if clave_lastfm:
                try:
                    parametros_lastfm = urlencode({
                        "method": "artist.gettoptracks", "artist": nombre_deezer,
                        "api_key": clave_lastfm, "format": "json", "limit": 50
                    })
                    datos_lastfm = consultar(
                        "https://ws.audioscrobbler.com/2.0/?" + parametros_lastfm,
                        timeout=5
                    )
                    pistas_lastfm = ((datos_lastfm.get("toptracks") or {}).get("track") or [])
                    if isinstance(pistas_lastfm, dict):
                        pistas_lastfm = [pistas_lastfm]
                    if pistas_lastfm:
                        canciones.sort(key=lambda c: int(c.get("rank") or 0), reverse=True)
                        por_titulo = {}
                        for posicion, cancion in enumerate(canciones):
                            llave = normalizar_texto(cancion.get("titulo"))
                            cancion["_pos_deezer"] = posicion
                            cancion["_pos_lastfm"] = None
                            por_titulo.setdefault(llave, cancion)
                        for posicion, pista_lastfm in enumerate(pistas_lastfm):
                            titulo_lastfm = str(pista_lastfm.get("name") or "").strip()
                            llave = normalizar_texto(titulo_lastfm)
                            if not llave:
                                continue
                            existente = por_titulo.get(llave)
                            if existente:
                                existente["_pos_lastfm"] = posicion
                                continue
                            artista_lastfm = pista_lastfm.get("artist") or {}
                            if isinstance(artista_lastfm, dict):
                                artista_lastfm = artista_lastfm.get("name") or nombre_deezer
                            canciones.append({
                                "titulo": titulo_lastfm,
                                "artista": str(artista_lastfm or nombre_deezer),
                                "album": "",
                                "preview": "",
                                "url": str(pista_lastfm.get("url") or ""),
                                "rank": 0,
                                "anio": anios_locales.get(llave),
                                "fecha": "",
                                "_pos_deezer": None,
                                "_pos_lastfm": posicion
                            })
                            por_titulo[llave] = canciones[-1]
                        for cancion in canciones:
                            posicion_deezer = cancion.get("_pos_deezer")
                            posicion_lastfm = cancion.get("_pos_lastfm")
                            puntuacion = 0.0
                            if posicion_deezer is not None:
                                puntuacion += 1.0 / (60 + posicion_deezer)
                            if posicion_lastfm is not None:
                                puntuacion += 1.0 / (60 + posicion_lastfm)
                            cancion["_puntuacion_fuentes"] = puntuacion
                        canciones.sort(key=lambda c: c.get("_puntuacion_fuentes", 0), reverse=True)
                        lastfm_usado = True
                except Exception as error_lastfm:
                    app.logger.info("Last.fm no pudo completar el ranking de %s: %s", nombre_deezer, error_lastfm)

        # Apple/iTunes completa fechas exactas cuando Deezer no las ofrece.
        if not lastfm_usado:
            canciones.sort(key=lambda c: int(c.get("rank") or 0), reverse=True)

        def completar_fecha_apple(cancion):
            if cancion.get("fecha") and len(cancion["fecha"]) >= 10:
                return None
            artista_busqueda = str(cancion.get("artista") or nombre_deezer)
            titulo_busqueda = str(cancion.get("titulo") or "")
            if not artista_busqueda or not titulo_busqueda:
                return None
            parametros_apple = urlencode({
                "term": artista_busqueda + " " + titulo_busqueda,
                "country": "ES", "entity": "song", "limit": 10
            })
            try:
                peticion_apple = Request(
                    "https://itunes.apple.com/search?" + parametros_apple,
                    headers={"User-Agent": "MiRadarMusical/1.0"}
                )
                with urlopen(peticion_apple, timeout=4) as respuesta_apple:
                    catalogo = json.loads(respuesta_apple.read().decode("utf-8"))
                objetivo_artista = normalizar_texto(artista_busqueda)
                objetivo_titulo = normalizar_texto(titulo_busqueda)
                mejor_apple = None
                mejor_puntuacion = -1
                for item in catalogo.get("results") or []:
                    artista_apple = normalizar_texto(item.get("artistName"))
                    titulo_apple = normalizar_texto(item.get("trackName"))
                    if not artista_apple or not titulo_apple:
                        continue
                    puntuacion = (
                        4 if artista_apple == objetivo_artista else
                        2 if difflib.SequenceMatcher(None, objetivo_artista, artista_apple).ratio() >= 0.88 else 0
                    )
                    puntuacion += (
                        5 if titulo_apple == objetivo_titulo else
                        2 if difflib.SequenceMatcher(None, objetivo_titulo, titulo_apple).ratio() >= 0.85 else 0
                    )
                    if puntuacion > mejor_puntuacion:
                        mejor_apple, mejor_puntuacion = item, puntuacion
                if not mejor_apple or mejor_puntuacion < 7:
                    return None
                fecha_apple = str(mejor_apple.get("releaseDate") or "")[:10]
                if not re.match(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$", fecha_apple):
                    fecha_apple = ""
                return (
                    cancion, fecha_apple,
                    fecha_apple[:4] if fecha_apple else "",
                    str(mejor_apple.get("collectionName") or "")
                )
            except Exception as error_apple:
                app.logger.debug("Apple/iTunes no pudo completar la fecha de %s: %s", titulo_busqueda, error_apple)
                return None

        # Limitar la consulta extra a los 30 temas mejor clasificados y paralelizarla
        # para no convertir la carga de la lista en decenas de esperas consecutivas.
        pendientes_fecha = [c for c in canciones[:30] if len(str(c.get("fecha") or "")) < 10]
        if pendientes_fecha:
            with ThreadPoolExecutor(max_workers=6) as executor:
                tareas_fecha = [executor.submit(completar_fecha_apple, c) for c in pendientes_fecha]
                for tarea in as_completed(tareas_fecha):
                    resultado_fecha = tarea.result()
                    if not resultado_fecha:
                        continue
                    cancion_fecha, fecha_apple, anio_apple, album_apple = resultado_fecha
                    if fecha_apple:
                        cancion_fecha["fecha"] = fecha_apple
                        cancion_fecha["anio"] = anio_apple
                    if not cancion_fecha.get("album") and album_apple:
                        cancion_fecha["album"] = album_apple

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
            # La puntuación combina posiciones de Deezer y Last.fm cuando ambas fuentes responden.
            canciones = canciones[:20]
            mensaje_vacio = "No se han encontrado canciones populares para este artista en las fuentes disponibles."

        if not canciones:
            return jsonify({"error": mensaje_vacio}), 502

        for cancion in canciones:
            for clave_interna in ("_pos_deezer", "_pos_lastfm", "_puntuacion_fuentes"):
                cancion.pop(clave_interna, None)
        fuente_resultado = (
            "Deezer + Last.fm (ranking combinado) + Apple/iTunes (fechas cuando están disponibles)"
            if lastfm_usado else
            "Deezer (popularidad) + Apple/iTunes (fechas cuando están disponibles)"
        )
        return jsonify({
            "artista": mejor.get("name", nombre_solicitado),
            "fuente": fuente_resultado,
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


# Las canciones guardadas se almacenan en el servidor para compartirlas entre móvil y ordenador.
_RUTA_GUARDADAS_RECOMENDACIONES = BASE / "recomendaciones_guardadas.json"
_CANDADO_GUARDADAS_RECOMENDACIONES = threading.Lock()


def _clave_guardada_recomendacion(cancion):
    return normalizar_texto(cancion.get("artista")) + "|" + normalizar_texto(cancion.get("titulo"))


def _url_bd_recomendaciones():
    return (os.environ.get("DATABASE_URL") or os.environ.get("RENDER_DATABASE_URL") or "").strip()


def _preparar_tablas_recomendaciones(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recomendaciones_guardadas (
            clave TEXT PRIMARY KEY,
            cancion JSONB NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recomendaciones_guardadas_estado (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            inicializado BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    cursor.execute("""
        INSERT INTO recomendaciones_guardadas_estado (id, inicializado)
        VALUES (1, FALSE) ON CONFLICT (id) DO NOTHING
    """)


def _fila_cancion_a_dict(valor):
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            return None
    return valor if isinstance(valor, dict) else None


def _leer_guardadas_recomendaciones_bd():
    import psycopg
    with psycopg.connect(_url_bd_recomendaciones(), connect_timeout=10) as conexion:
        with conexion.cursor() as cursor:
            _preparar_tablas_recomendaciones(cursor)
            cursor.execute("SELECT inicializado FROM recomendaciones_guardadas_estado WHERE id = 1")
            fila_estado = cursor.fetchone()
            inicializado = bool(fila_estado and fila_estado[0])
            # Conserva los datos del antiguo JSON si aún existen al conectar la base de datos.
            if not inicializado:
                try:
                    antiguo = json.loads(_RUTA_GUARDADAS_RECOMENDACIONES.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    antiguo = {}
                antiguas = antiguo.get("canciones", []) if isinstance(antiguo, dict) else []
                if isinstance(antiguo, dict) and isinstance(antiguas, list) and antiguo.get("inicializado"):
                    for cancion in antiguas:
                        if isinstance(cancion, dict) and cancion.get("titulo") and cancion.get("artista"):
                            cursor.execute(
                                """INSERT INTO recomendaciones_guardadas (clave, cancion)
                                   VALUES (%s, %s::jsonb) ON CONFLICT (clave) DO NOTHING""",
                                (_clave_guardada_recomendacion(cancion), json.dumps(cancion, ensure_ascii=False))
                            )
                    cursor.execute("UPDATE recomendaciones_guardadas_estado SET inicializado = TRUE WHERE id = 1")
                    inicializado = True
            cursor.execute("SELECT cancion FROM recomendaciones_guardadas ORDER BY creado_en DESC")
            canciones = [_fila_cancion_a_dict(f[0]) for f in cursor.fetchall()]
            return {"inicializado": inicializado, "canciones": [c for c in canciones if c and c.get("titulo") and c.get("artista")]}


def _anadir_guardadas_recomendaciones_bd(nuevas):
    import psycopg
    with psycopg.connect(_url_bd_recomendaciones(), connect_timeout=10) as conexion:
        with conexion.cursor() as cursor:
            _preparar_tablas_recomendaciones(cursor)
            for cancion in nuevas:
                cursor.execute(
                    """INSERT INTO recomendaciones_guardadas (clave, cancion)
                       VALUES (%s, %s::jsonb) ON CONFLICT (clave) DO NOTHING""",
                    (_clave_guardada_recomendacion(cancion), json.dumps(cancion, ensure_ascii=False))
                )
            cursor.execute("UPDATE recomendaciones_guardadas_estado SET inicializado = TRUE WHERE id = 1")
    return _leer_guardadas_recomendaciones_bd()


def _quitar_guardada_recomendaciones_bd(clave):
    import psycopg
    with psycopg.connect(_url_bd_recomendaciones(), connect_timeout=10) as conexion:
        with conexion.cursor() as cursor:
            _preparar_tablas_recomendaciones(cursor)
            cursor.execute("DELETE FROM recomendaciones_guardadas WHERE clave = %s", (clave,))
            cursor.execute("UPDATE recomendaciones_guardadas_estado SET inicializado = TRUE WHERE id = 1")
    return _leer_guardadas_recomendaciones_bd()


def _leer_guardadas_recomendaciones():
    if _url_bd_recomendaciones():
        return _leer_guardadas_recomendaciones_bd()
    try:
        datos = json.loads(_RUTA_GUARDADAS_RECOMENDACIONES.read_text(encoding="utf-8"))
        if not isinstance(datos, dict):
            return {"inicializado": False, "canciones": []}
        canciones = datos.get("canciones")
        if not isinstance(canciones, list):
            canciones = []
        return {"inicializado": bool(datos.get("inicializado")), "canciones": [
            c for c in canciones if isinstance(c, dict) and c.get("titulo") and c.get("artista")
        ]}
    except (OSError, json.JSONDecodeError):
        return {"inicializado": False, "canciones": []}


def _guardar_estado_recomendaciones(estado):
    temporal = _RUTA_GUARDADAS_RECOMENDACIONES.with_suffix(".tmp")
    temporal.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(_RUTA_GUARDADAS_RECOMENDACIONES)


@app.get("/api/recomendaciones/guardadas")
def api_leer_guardadas_recomendaciones():
    with _CANDADO_GUARDADAS_RECOMENDACIONES:
        estado = _leer_guardadas_recomendaciones()
    return jsonify(estado)


@app.post("/api/recomendaciones/guardadas")
def api_anadir_guardadas_recomendaciones():
    cuerpo = request.get_json(silent=True) or {}
    canciones = cuerpo.get("canciones")
    if not isinstance(canciones, list) or len(canciones) > 1000:
        return jsonify({"error": "La lista de canciones no es válida."}), 400
    nuevas = []
    for cancion in canciones:
        if not isinstance(cancion, dict):
            continue
        titulo = str(cancion.get("titulo") or "").strip()[:300]
        artista = str(cancion.get("artista") or "").strip()[:300]
        if not titulo or not artista:
            continue
        nuevas.append({
            "titulo": titulo,
            "artista": artista,
            "anio": str(cancion.get("anio") or "")[:20],
            "genero": str(cancion.get("genero") or "")[:120],
            "relacionado_con": str(cancion.get("relacionado_con") or "")[:300],
            "album": str(cancion.get("album") or "")[:300],
            "portada": str(cancion.get("portada") or "")[:2000],
            "preview": str(cancion.get("preview") or "")[:2000],
        })
    with _CANDADO_GUARDADAS_RECOMENDACIONES:
        try:
            if _url_bd_recomendaciones():
                estado = _anadir_guardadas_recomendaciones_bd(nuevas)
            else:
                estado = _leer_guardadas_recomendaciones()
                existentes = {_clave_guardada_recomendacion(c): c for c in estado["canciones"]}
                for cancion in nuevas:
                    clave = _clave_guardada_recomendacion(cancion)
                    if clave not in existentes:
                        estado["canciones"].insert(0, cancion)
                        existentes[clave] = cancion
                estado["inicializado"] = True
                _guardar_estado_recomendaciones(estado)
        except Exception:
            app.logger.exception("No se pudieron guardar las recomendaciones.")
            return jsonify({"error": "No se han podido guardar las canciones. Comprueba la conexión de almacenamiento."}), 500
    return jsonify(estado)


@app.delete("/api/recomendaciones/guardadas")
def api_quitar_guardada_recomendacion():
    cuerpo = request.get_json(silent=True) or {}
    titulo = str(cuerpo.get("titulo") or "").strip()
    artista = str(cuerpo.get("artista") or "").strip()
    if not titulo or not artista:
        return jsonify({"error": "Faltan el título y el artista."}), 400
    clave_objetivo = normalizar_texto(artista) + "|" + normalizar_texto(titulo)
    with _CANDADO_GUARDADAS_RECOMENDACIONES:
        try:
            if _url_bd_recomendaciones():
                estado = _quitar_guardada_recomendaciones_bd(clave_objetivo)
            else:
                estado = _leer_guardadas_recomendaciones()
                estado["canciones"] = [
                    c for c in estado["canciones"]
                    if _clave_guardada_recomendacion(c) != clave_objetivo
                ]
                estado["inicializado"] = True
                _guardar_estado_recomendaciones(estado)
        except Exception:
            app.logger.exception("No se pudo quitar la recomendación guardada.")
            return jsonify({"error": "No se ha podido actualizar la lista del servidor."}), 500
    return jsonify(estado)


@app.get("/api/recomendaciones")
def api_recomendaciones():
    """Recomienda temas ajenos a la biblioteca usando una muestra aleatoria de toda la colección."""
    genero_solicitado = (request.args.get("genero") or "").strip()
    decada_solicitada = (request.args.get("decada") or "").strip()
    if decada_solicitada and not re.fullmatch(r"(19|20)\d0", decada_solicitada):
        decada_solicitada = ""
    try:
        semilla_azar = int(request.args.get("azar") or 0)
    except (TypeError, ValueError):
        semilla_azar = 0
    # La misma semilla mantiene las recomendaciones estables al paginar;
    # al pulsar «Buscar recomendaciones», el navegador genera otra semilla.
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
    semillas = semillas[:5]
    if not semillas:
        return jsonify({"canciones": [], "generos": generos, "total_biblioteca": len(biblioteca),
                        "error": "No hay suficientes artistas en tu colección para ese género."}), 200

    candidatos = {}
    cache_peticion = {}

    def consultar(url, timeout=4):
        # Todas las recomendaciones deben quedar acotadas: Gunicorn mata el
        # trabajador si una cadena de catálogos externos tarda demasiado.
        timeout = min(timeout, 1.0 if decada_solicitada else 1.5)
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

    def añadir_candidata(pista, semilla, peso, fuente, completar_datos=True):
        titulo = str(pista.get("title") or pista.get("titulo") or pista.get("name") or "").strip()
        artista_info = pista.get("artist") or {}
        nombre_artista = str(artista_info.get("name") or pista.get("artista") or "").strip()
        if not titulo or not nombre_artista:
            return
        llave = (clave(nombre_artista), clave(titulo))
        if llave in existentes:
            return
        # Si la recomendación viene de Last.fm sin ID de Deezer, buscar una ficha
        # fiable por artista y título para recuperar portada, álbum y fecha.
        album_inicial = pista.get("album") or {}
        fecha_inicial = (pista.get("release_date") or album_inicial.get("release_date") or
                         pista.get("releaseDate") or pista.get("date") or "")
        portada_inicial = (album_inicial.get("cover_xl") or album_inicial.get("cover_big") or
                           album_inicial.get("cover_medium") or album_inicial.get("cover") or
                           pista.get("cover_xl") or pista.get("cover_big") or "")
        if completar_datos and (not pista.get("id") or not fecha_inicial or not portada_inicial):
            consulta_dz = urlencode({"q": 'artist:"' + nombre_artista + '" track:"' + titulo + '"', "limit": 10})
            resultados_dz = consultar("https://api.deezer.com/search/track?" + consulta_dz).get("data") or []
            objetivo_artista, objetivo_titulo = clave(nombre_artista), clave(titulo)
            posibles = []
            for resultado_dz in resultados_dz:
                artista_dz = clave((resultado_dz.get("artist") or {}).get("name") or "")
                titulo_dz = clave(resultado_dz.get("title") or "")
                similitud_dz = difflib.SequenceMatcher(None, objetivo_titulo, titulo_dz).ratio()
                if artista_dz == objetivo_artista and (titulo_dz == objetivo_titulo or similitud_dz >= 0.72):
                    posibles.append((int(titulo_dz == objetivo_titulo), similitud_dz, resultado_dz))
            if posibles:
                mejor_dz = max(posibles, key=lambda x: (x[0], x[1]))[2]
                pista = {**mejor_dz, **pista} if pista.get("id") else mejor_dz
        # Completar los datos con Deezer: la búsqueda resumida no siempre incluye
        # fecha ni una portada de tamaño utilizable.
        album = pista.get("album") or {}
        fecha_lanzamiento = (pista.get("release_date") or album.get("release_date") or
                             pista.get("releaseDate") or pista.get("date") or "")
        tiene_portada = bool(album.get("cover_xl") or album.get("cover_big") or
                             album.get("cover_medium") or album.get("cover") or
                             pista.get("cover_xl") or pista.get("cover_big"))
        if completar_datos and pista.get("id") and (not fecha_lanzamiento or not tiene_portada or not pista.get("preview")):
            detalle = consultar("https://api.deezer.com/track/" + str(pista["id"]), timeout=5)
            if detalle:
                pista = {**pista, **detalle}
                album = pista.get("album") or album
                fecha_lanzamiento = (pista.get("release_date") or album.get("release_date") or
                                     pista.get("releaseDate") or pista.get("date") or fecha_lanzamiento)
        # La fecha suele estar en la ficha del álbum, aunque falte en la canción.
        if completar_datos and album.get("id") and (not fecha_lanzamiento or not (album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium") or album.get("cover"))):
            detalle_album = consultar("https://api.deezer.com/album/" + str(album["id"]), timeout=5)
            if detalle_album:
                album = {**album, **detalle_album}
                pista["album"] = album
                fecha_lanzamiento = (pista.get("release_date") or album.get("release_date") or
                                     pista.get("releaseDate") or pista.get("date") or fecha_lanzamiento)
        portada = (album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium") or
                   album.get("cover") or pista.get("cover_xl") or pista.get("cover_big") or "")
        if not portada:
            imagenes = pista.get("image") or []
            if isinstance(imagenes, list):
                portada = next((im.get("#text") or im.get("url") for im in reversed(imagenes)
                                if isinstance(im, dict) and (im.get("#text") or im.get("url"))), "")
        # Normalizar URLs antiguas/protocol-relative antes de enviarlas al navegador.
        if isinstance(portada, str):
            portada = portada.strip()
            if portada.startswith("//"):
                portada = "https:" + portada
            elif portada.startswith("http://"):
                portada = "https://" + portada[len("http://"):]
            if not portada.startswith("https://"):
                portada = ""
        else:
            portada = ""
        puntaje = peso * 100 + min(int(pista.get("rank") or 0) / 100000, 30)
        actual = candidatos.get(llave)
        if actual and actual["puntuacion"] >= puntaje:
            return
        coincidencia_anio = re.search(r"(?:19|20)\d{2}", str(fecha_lanzamiento))
        anio = coincidencia_anio.group(0) if coincidencia_anio else ""
        candidatos[llave] = {
            "titulo": titulo,
            "artista": nombre_artista,
            "album": album.get("title") or "",
            "album_id": str(album.get("id") or ""),
            "portada": portada,
            "preview": pista.get("preview") or "",
            "anio": anio,
            "url": pista.get("link") or pista.get("url") or "",
            "genero": genero_solicitado or (max(semilla["generos"], key=semilla["generos"].get) if semilla.get("generos") else ""),
            "relacionado_con": semilla["nombre"],
            "puntuacion": puntaje,
            "fuente_recomendacion": fuente
        }

    # Primera opción: similitud entre canciones en Last.fm. Reutiliza LASTFM_API_KEY,
    # que ya emplea la aplicación para consultar información musical.
    clave_lastfm = (os.environ.get("LASTFM_API_KEY") or "").strip()
    semillas_pistas = []
    for pista in biblioteca:
        if not isinstance(pista, dict):
            continue
        artista = str(pista.get("artista") or "").strip()
        titulo = str(pista.get("titulo") or "").strip()
        genero = str(pista.get("genero") or "").strip()
        if not artista or not titulo:
            continue
        if genero_solicitado and genero.casefold() != genero_solicitado.casefold():
            continue
        anio_pista = str(pista.get("anio") or "").strip()
        if decada_solicitada and not anio_pista.startswith(decada_solicitada[:3]):
            continue
        semillas_pistas.append({
            "nombre": artista, "titulo": titulo, "genero": genero, "anio": anio_pista
        })
    # En una búsqueda por década, las semillas salen exclusivamente de canciones
    # de esa época presentes en la biblioteca. En la búsqueda general se mantiene
    # la selección aleatoria de toda la colección.
    # La semilla del navegador hace que las páginas siguientes mantengan la misma selección.
    random.Random(semilla_azar).shuffle(semillas_pistas)
    semillas_lastfm = []
    artistas_semilla = set()
    # Ampliar las referencias por década para que la personalización no dependa
    # de solo dos canciones. El conjunto de semillas sigue siendo diverso por artista.
    limite_semillas = 5 if decada_solicitada else 3
    for pista_semilla in semillas_pistas:
        artista_clave = clave(pista_semilla["nombre"])
        if artista_clave in artistas_semilla:
            continue
        semillas_lastfm.append(pista_semilla)
        artistas_semilla.add(artista_clave)
        if len(semillas_lastfm) >= limite_semillas:
            break

    if clave_lastfm:
        for indice, semilla in enumerate(semillas_lastfm):
            params = urlencode({
                "method": "track.getSimilar",
                "artist": semilla["nombre"],
                "track": semilla["titulo"],
                "api_key": clave_lastfm,
                "format": "json",
                "autocorrect": 1,
                "limit": 12
            })
            datos = consultar("https://ws.audioscrobbler.com/2.0/?" + params, timeout=6)
            similares = (datos.get("similartracks") or {}).get("track") or []
            if isinstance(similares, dict):
                similares = [similares]
            for similar in similares[:12 if decada_solicitada else 4]:
                titulo = str(similar.get("name") or "").strip()
                artista_info = similar.get("artist") or {}
                nombre_artista = str(artista_info.get("name") or "").strip()
                if not titulo or not nombre_artista or (clave(nombre_artista), clave(titulo)) in existentes:
                    continue
                # Last.fm descubre el tema; Deezer aporta portada, álbum, enlace y muestra.
                # En búsquedas por década, guardar el descubrimiento de Last.fm sin
                # consultas Deezer individuales; reservar tiempo para comprobar los años.
                if decada_solicitada:
                    añadir_candidata({
                        "titulo": titulo, "artist": {"name": nombre_artista},
                        "url": similar.get("url") or "", "image": similar.get("image") or []
                    }, semilla, max(0.5, float(similar.get("match") or 0.5)), "Last.fm",
                       completar_datos=False)
                    continue
                q = urlencode({"q": 'artist:"' + nombre_artista + '" track:"' + titulo + '"', "limit": 8})
                resultados_deezer = consultar("https://api.deezer.com/search/track?" + q).get("data") or []
                objetivo_artista, objetivo_titulo = clave(nombre_artista), clave(titulo)
                mejor = None
                mejor_puntuacion = 0.0
                for resultado in resultados_deezer:
                    artista_dz = str((resultado.get("artist") or {}).get("name") or "")
                    titulo_dz = str(resultado.get("title") or "")
                    puntuacion = difflib.SequenceMatcher(None, objetivo_artista, clave(artista_dz)).ratio() * 0.45
                    puntuacion += difflib.SequenceMatcher(None, objetivo_titulo, clave(titulo_dz)).ratio() * 0.55
                    if objetivo_artista == clave(artista_dz):
                        puntuacion += 0.25
                    if objetivo_titulo == clave(titulo_dz):
                        puntuacion += 0.30
                    if puntuacion > mejor_puntuacion:
                        mejor, mejor_puntuacion = resultado, puntuacion
                # La coincidencia exacta de título era demasiado estricta: versiones,
                # signos o subtítulos podían dejar fuera resultados válidos de Deezer.
                # Exigir el mismo artista y una similitud razonable del título evita
                # asignar portadas de otro artista sin perder variantes legítimas.
                similitud_titulo = (difflib.SequenceMatcher(
                    None, objetivo_titulo, clave((mejor or {}).get("title") or "")
                ).ratio() if mejor else 0.0)
                if (mejor and objetivo_artista == clave((mejor.get("artist") or {}).get("name"))
                        and (objetivo_titulo == clave(mejor.get("title")) or similitud_titulo >= 0.72)):
                    # La búsqueda de Deezer ya aporta portada, álbum y muestra.
                    # Evitar una consulta extra por canción: Render estaba agotando
                    # el tiempo de la petición al encadenar llamadas externas.
                    añadir_candidata(mejor, semilla, max(0.5, float(similar.get("match") or 0.5)) * 1.2,
                                     "Last.fm", completar_datos=False)
                else:
                    # Si Deezer no encuentra una coincidencia fiable, conservar los
                    # datos originales de Last.fm, sin atribuirle la portada de otro tema.
                    añadir_candidata({
                        "titulo": titulo, "artist": {"name": nombre_artista},
                        "url": similar.get("url") or "",
                        "image": similar.get("image") or []
                    }, semilla, max(0.5, float(similar.get("match") or 0.5)), "Last.fm",
                       completar_datos=False)

    fuente_final = "Last.fm + Deezer + tu biblioteca" if candidatos else "Deezer + tu biblioteca"

    # Si Last.fm no está configurado o no devuelve suficientes temas, completar con el
    # sistema anterior de artistas relacionados de Deezer.
    if len(candidatos) < 10 or decada_solicitada:
        semillas_artistas = list(artistas.values())
        if genero_solicitado:
            semillas_artistas = [a for a in semillas_artistas if a["generos"] and
                                 max(a["generos"], key=a["generos"].get).casefold() == genero_solicitado.casefold()]
        if decada_solicitada:
            artistas_con_canciones_de_decada = {
                clave(str(p.get("artista") or ""))
                for p in biblioteca
                if isinstance(p, dict)
                and str(p.get("artista") or "").strip()
                and str(p.get("anio") or "").strip().startswith(decada_solicitada[:3])
                and (not genero_solicitado or
                     str(p.get("genero") or "").strip().casefold() == genero_solicitado.casefold())
            }
            semillas_artistas = [
                a for a in semillas_artistas
                if clave(a["nombre"]) in artistas_con_canciones_de_decada
            ]
        # En búsquedas por década, las referencias de Deezer también deben proceder
        # de artistas que tengas en la biblioteca durante esa época. La búsqueda
        # general conserva su selección previa.
        random.Random(semilla_azar ^ 0x5F3759DF).shuffle(semillas_artistas)
        semillas_artistas = semillas_artistas[:4 if decada_solicitada else 3]
        for semilla in semillas_artistas:
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
            # Al filtrar por década hace falta una muestra más amplia: el top 8
            # habitual suele dejar fuera canciones antiguas o con fecha disponible.
            limite_relacionados = 3 if decada_solicitada else 2
            relacionados = consultar("https://api.deezer.com/artist/" + str(coincidencia.get("id")) +
                                     "/related?" + urlencode({"limit": limite_relacionados})).get("data") or []
            objetivos = [(a, 1.0) for a in relacionados[:limite_relacionados]] or [(coincidencia, 0.55)]
            for artista_rel, peso in objetivos:
                id_rel = artista_rel.get("id")
                if not id_rel:
                    continue
                limite_top = 40 if decada_solicitada else 6
                top = consultar("https://api.deezer.com/artist/" + str(id_rel) +
                                "/top?" + urlencode({"limit": limite_top})).get("data") or []
                for pista in top:
                    # Las pistas del top de Deezer ya incluyen datos básicos; no
                    # hacer búsquedas de detalle/álbum por cada resultado.
                    añadir_candidata(pista, semilla, peso, "Deezer", completar_datos=False)

    # No rellenar las búsquedas por década con canciones genéricas de MusicBrainz:
    # las recomendaciones visibles deben proceder de similitudes con tu biblioteca.

    if decada_solicitada:
        # Deezer a menudo no incluye fecha. Completar los años por tandas y seguir
        # avanzando mientras no haya suficientes canciones de la década solicitada.
        # La versión anterior solo consultaba 60 candidatas: si encontraba 3 años 80,
        # descartaba el resto aunque hubiera más canciones válidas detrás.
        from concurrent.futures import ThreadPoolExecutor
        objetivo_resultados = inicio + 10
        # Mantener el orden de descubrimiento cuando la puntuación empata.
        # Ordenar por artista/título alfabéticamente sesgaba las 60 consultas de año.
        candidatos_ordenados = sorted(
            candidatos.values(),
            key=lambda p: -p.get("puntuacion", 0)
        )
        # Revisar también años fuera de la década: pueden venir de una reedición.
        pendientes_anio = [p for p in candidatos_ordenados
                           if not str(p.get("anio") or "").strip().startswith(decada_solicitada[:3])]
        anios_diagnostico = {"consultas": 0, "respuestas": 0, "coincidencias": 0, "con_anio": 0, "errores": 0}
        bloqueo_diagnostico = threading.Lock()
        app.logger.warning(
            "Recomendaciones por década: década=%s, candidatos=%s, ya_con_año=%s, pendientes_de_verificar=%s",
            decada_solicitada, len(candidatos_ordenados),
            len(candidatos_ordenados) - len(pendientes_anio), len(pendientes_anio)
        )
        # Límite conservador para evitar que Gunicorn mate al trabajador por tiempo.
        # Revisar más candidatas y repartir las consultas por toda la lista; las primeras
        # por puntuación suelen ser éxitos recientes y sesgan las décadas antiguas.
        candidatas_para_anio = list(pendientes_anio)
        random.Random(semilla_azar ^ 0x6A09E667).shuffle(candidatas_para_anio)
        max_consultas_anio = min(len(candidatas_para_anio), 120)

        def completar_anio_decada(pista):
            # Si falta el año, aprovechar primero el álbum que ya devuelve Deezer.
            # Si el álbum da un año de otra década, contrastarlo con Apple antes de descartarlo.
            anio_actual = str(pista.get("anio") or "").strip()
            album_id = str(pista.get("album_id") or "").strip()
            if album_id and not anio_actual:
                try:
                    peticion_album = Request(
                        "https://api.deezer.com/album/" + album_id,
                        headers={"User-Agent": "MiRadarMusical/1.0"}
                    )
                    with urlopen(peticion_album, timeout=2.0) as respuesta_album:
                        datos_album = json.loads(respuesta_album.read().decode("utf-8"))
                    fecha_album = str(datos_album.get("release_date") or "")
                    coincidencia_album = re.search(r"(?:19|20)\d{2}", fecha_album)
                    if coincidencia_album:
                        pista["anio"] = coincidencia_album.group(0)
                        if not pista.get("album"):
                            pista["album"] = str(datos_album.get("title") or "")
                        anio_actual = pista["anio"]
                        with bloqueo_diagnostico:
                            anios_diagnostico["respuestas"] += 1
                            anios_diagnostico["con_anio"] += 1
                        if anio_actual.startswith(decada_solicitada[:3]):
                            return
                except Exception as error_album:
                    app.logger.debug("No se pudo recuperar el año del álbum Deezer %s: %s", album_id, error_album)

            # Reutilizar el método de la web: consultar los catálogos español y
            # estadounidense y aceptar solo coincidencias fiables de artista y título.
            def consultar_itunes_decada(pais):
                parametros = urlencode({
                    "term": str(pista.get("artista") or "") + " " + str(pista.get("titulo") or ""),
                    "country": pais, "media": "music", "entity": "song", "limit": 50
                })
                try:
                    peticion = Request("https://itunes.apple.com/search?" + parametros,
                                       headers={"User-Agent": "MiRadarMusical/1.0"})
                    with urlopen(peticion, timeout=2.5) as respuesta:
                        datos_pais = json.loads(respuesta.read().decode("utf-8"))
                    with bloqueo_diagnostico:
                        anios_diagnostico["respuestas"] += 1
                    return datos_pais
                except Exception as error_pais:
                    with bloqueo_diagnostico:
                        anios_diagnostico["errores"] += 1
                    app.logger.debug("Recomendaciones: iTunes %s no respondió para una candidata: %s", pais, error_pais)
                    return {}

            try:
                with bloqueo_diagnostico:
                    anios_diagnostico["consultas"] += 2
                # Una caída regional no debe descartar la respuesta del otro catálogo.
                with ThreadPoolExecutor(max_workers=2) as executor_itunes:
                    consultas_itunes = list(executor_itunes.map(consultar_itunes_decada, ("es", "us")))
                resultados_itunes = []
                for datos_itunes in consultas_itunes:
                    resultados_itunes.extend(datos_itunes.get("results") or [])
                mejor = _coincidencia_itunes_segura(
                    pista.get("artista"), pista.get("titulo"), resultados_itunes
                )
                if mejor:
                    with bloqueo_diagnostico:
                        anios_diagnostico["coincidencias"] += 1
                    fecha_itunes = str(mejor.get("releaseDate") or "")
                    coincidencia = re.search(r"(?:19|20)\d{2}", fecha_itunes)
                    if coincidencia:
                        # Apple puede aportar un año distinto al de una reedición de Deezer.
                        pista["anio"] = coincidencia.group(0)
                        with bloqueo_diagnostico:
                            anios_diagnostico["con_anio"] += 1
                    if not pista.get("portada") and mejor.get("artworkUrl100"):
                        pista["portada"] = str(mejor["artworkUrl100"]).replace("100x100bb", "600x600bb")
                    if not pista.get("album"):
                        pista["album"] = str(mejor.get("collectionName") or "")
            except Exception as error:
                app.logger.debug("Recomendaciones: no se pudo recuperar año de iTunes: %s", error)
        # Consultar primero las canciones mejor puntuadas y ampliar por lotes de 40
        # hasta llenar la tanda o agotar el límite de consultas, no solo las primeras 60.
        consultadas = 0
        tamano_lote = 24
        # No contar MusicBrainz para decidir si ya hay suficientes resultados:
        # esas canciones sirven de respaldo, pero no prueban afinidad con la biblioteca.
        resultados_personalizados = [
            p for p in candidatos_ordenados
            if p.get("fuente_recomendacion") != "MusicBrainz"
            and p.get("anio") and p["anio"].startswith(decada_solicitada[:3])
        ]
        with ThreadPoolExecutor(max_workers=12) as executor:
            while consultadas < max_consultas_anio and len(resultados_personalizados) < objetivo_resultados:
                lote = candidatas_para_anio[consultadas:min(consultadas + tamano_lote, max_consultas_anio)]
                list(executor.map(completar_anio_decada, lote))
                consultadas += len(lote)
                resultados_personalizados = [
                    p for p in candidatos_ordenados
                    if p.get("fuente_recomendacion") != "MusicBrainz"
                    and p.get("anio") and p["anio"].startswith(decada_solicitada[:3])
                ]
                if len(resultados_personalizados) >= objetivo_resultados:
                    break

        ordenadas = [p for p in candidatos_ordenados
                     if p.get("anio") and p["anio"].startswith(decada_solicitada[:3])]
        distribucion_anios = {}
        ejemplos_anios = []
        for pista_con_anio in candidatos_ordenados:
            anio_recuperado = str(pista_con_anio.get("anio") or "")
            if anio_recuperado:
                distribucion_anios[anio_recuperado[:3] + "0s"] = distribucion_anios.get(anio_recuperado[:3] + "0s", 0) + 1
                if len(ejemplos_anios) < 8:
                    ejemplos_anios.append(
                        str(pista_con_anio.get("artista") or "") + " — " +
                        str(pista_con_anio.get("titulo") or "") + " (" + anio_recuperado + ")"
                    )
        app.logger.warning(
            "Recomendaciones por década resultado: década=%s, candidatas=%s, consultas_itunes=%s, respuestas_totales=%s, coincidencias_itunes_fiables=%s, años_recuperados=%s, errores_itunes=%s, resultados_de_la_decada=%s, distribucion_anios=%s, ejemplos=%s",
            decada_solicitada, len(candidatos_ordenados),
            anios_diagnostico["consultas"], anios_diagnostico["respuestas"],
            anios_diagnostico["coincidencias"], anios_diagnostico["con_anio"],
            anios_diagnostico["errores"], len(ordenadas),
            distribucion_anios, ejemplos_anios
        )
    else:
        ordenadas = list(candidatos.values())
    # En búsquedas por década solo quedan recomendaciones derivadas de la biblioteca.
    # No se añaden rellenos genéricos de catálogos externos.
    try:
        semilla_azar = int(request.args.get("azar") or "0")
    except (TypeError, ValueError):
        semilla_azar = 0
    if decada_solicitada:
        # Deduplicar por pareja artista+título, nunca por artista solamente:
        # se permiten varios temas del mismo artista si son canciones distintas.
        unicas = {}
        for pista in ordenadas:
            llave = (clave(pista.get("artista") or ""), clave(pista.get("titulo") or ""))
            if llave in existentes or llave in unicas:
                continue
            unicas[llave] = pista
        ordenadas = list(unicas.values())
        random.Random(semilla_azar).shuffle(ordenadas)
    else:
        ordenadas.sort(key=lambda p: (-p["puntuacion"], clave(p["artista"]), clave(p["titulo"])))
        random.Random(semilla_azar).shuffle(ordenadas)
    return jsonify({"canciones": ordenadas[inicio:inicio + 10], "generos": generos,
                    "total_candidatas": len(ordenadas), "total_biblioteca": len(biblioteca),
                    "inicio": inicio, "decada": decada_solicitada, "fuente": fuente_final,
                    "aviso": "Se prioriza la similitud entre canciones de Last.fm cuando está configurado; Deezer completa los datos disponibles. Si no, se usan artistas relacionados de Deezer. Las canciones de tu biblioteca se excluyen."})


def _coincidencia_itunes_segura(artista, titulo, resultados):
    """Selecciona una grabación de Apple solo si artista y título coinciden con suficiente seguridad."""
    artista_objetivo = normalizar_texto(str(artista or ""))
    titulo_objetivo = normalizar_texto(str(titulo or ""))
    mejor = None
    mejor_puntuacion = -1.0

    for item in resultados or []:
        artista_catalogo = normalizar_texto(str(item.get("artistName") or ""))
        titulo_catalogo = normalizar_texto(str(item.get("trackName") or ""))
        if not artista_catalogo or not titulo_catalogo:
            continue

        similitud_artista = difflib.SequenceMatcher(
            None, artista_objetivo, artista_catalogo
        ).ratio()
        similitud_titulo = difflib.SequenceMatcher(
            None, titulo_objetivo, titulo_catalogo
        ).ratio()
        artista_exacto = artista_catalogo == artista_objetivo
        titulo_exacto = titulo_catalogo == titulo_objetivo

        # Una coincidencia parcial solo se admite si el texto compartido es
        # suficientemente largo; evita confundir títulos cortos o canciones distintas.
        titulo_contenido = (
            len(titulo_objetivo) >= 8 and
            (titulo_objetivo in titulo_catalogo or titulo_catalogo in titulo_objetivo)
        )
        if not (
            (artista_exacto or similitud_artista >= 0.90) and
            (titulo_exacto or similitud_titulo >= 0.82 or
             (titulo_contenido and similitud_titulo >= 0.78))
        ):
            continue

        puntuacion = (
            (1.0 if artista_exacto else similitud_artista) * 0.45 +
            (1.0 if titulo_exacto else similitud_titulo) * 0.55
        )
        if puntuacion > mejor_puntuacion:
            mejor = item
            mejor_puntuacion = puntuacion

    return mejor


@app.get("/api/recomendaciones/datos")
def api_recomendaciones_datos():
    """Completa portada y año con una coincidencia prudente en Apple/iTunes."""
    artista = (request.args.get("artista") or "").strip()
    titulo = (request.args.get("titulo") or "").strip()
    if not artista or not titulo:
        return jsonify({"error": "Faltan artista o título."}), 400

    try:
        resultados = []
        # Consultar España y Estados Unidos en paralelo: la página cancela la
        # petición tras 7 segundos y dos consultas secuenciales podían superar ese límite.
        from concurrent.futures import ThreadPoolExecutor

        def consultar_itunes(pais):
            parametros = urlencode({
                "term": artista + " " + titulo,
                "country": pais,
                "media": "music",
                "entity": "song",
                "limit": 50
            })
            peticion = Request(
                "https://itunes.apple.com/search?" + parametros,
                headers={"User-Agent": "MiRadarMusical/1.0"}
            )
            with urlopen(peticion, timeout=5) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))

        with ThreadPoolExecutor(max_workers=2) as executor:
            consultas = list(executor.map(consultar_itunes, ("es", "us")))
        # Priorizar España para que, si ambas tiendas tienen la misma grabación,
        # prevalezca su ficha local; Estados Unidos sirve como catálogo adicional.
        for datos in consultas:
            resultados.extend(datos.get("results") or [])

        mejor = _coincidencia_itunes_segura(artista, titulo, resultados)
        if not mejor:
            return jsonify({"anio": "", "portada": "", "album": ""})

        fecha = str(mejor.get("releaseDate") or "")
        coincidencia = re.search(r"(?:19|20)\d{2}", fecha)
        imagen = str(mejor.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
        if imagen.startswith("http://"):
            imagen = "https://" + imagen[7:]
        if not imagen.startswith("https://"):
            imagen = ""

        return jsonify({
            "anio": coincidencia.group(0) if coincidencia else "",
            "portada": imagen,
            "album": str(mejor.get("collectionName") or "")
        })
    except Exception as error:
        app.logger.info(
            "Recomendaciones: no se pudo completar año/portada con iTunes: %s", error
        )
        return jsonify({"anio": "", "portada": "", "album": ""})

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
    """Busca muestras de 30 segundos y permite versiones alternativas verificadas."""
    titulo = (request.args.get("titulo") or "").strip()
    artista = (request.args.get("artista") or "").strip()

    if not titulo or not artista:
        return jsonify({"error": "Falta el título o el artista."}), 400

    # Separa la canción de los añadidos habituales en títulos de vídeos o ediciones.
    titulo_sin_lanzamiento = re.sub(
        r"\s*[-–—]\s*(?:single|ep|album)\s*$|\s*\((?:single|ep|album)\)\s*$",
        "", titulo, flags=re.IGNORECASE
    ).strip() or titulo
    titulo_base = re.sub(
        r"\s*\((?=[^)]*(?:live|en directo|from|acoustic|acústic|remix|remaster|version|versión|edit|sped up|slowed|instrumental|karaoke))[^)]*\)\s*$",
        "", titulo_sin_lanzamiento, flags=re.IGNORECASE
    ).strip()
    titulo_base = re.sub(
        r"\s*[-–—]\s*(?:live(?:\s+from\s+.*)?|en directo|acoustic|acústic|remix|remaster(?:ed)?|radio edit|sped up|slowed|instrumental|karaoke)\s*$",
        "", titulo_base, flags=re.IGNORECASE
    ).strip() or titulo_sin_lanzamiento

    variantes_titulo = list(dict.fromkeys(
        normalizar_texto(x) for x in (titulo_sin_lanzamiento, titulo_base) if x
    ))
    artista_objetivo = normalizar_texto(artista)
    artistas_objetivo = [
        normalizar_texto(x) for x in re.split(
            r"\s*(?:,|&|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bx\b|\bcon\b)\s*",
            artista, flags=re.IGNORECASE
        ) if normalizar_texto(x)
    ] or [artista_objetivo]

    consultas = list(dict.fromkeys([
        f"{artista} {titulo_sin_lanzamiento}",
        f"{artistas_objetivo[0]} {titulo_base}",
        titulo_base
    ]))

    def buscar_en_catalogo(url, fuente):
        peticion = Request(
            url,
            headers={"User-Agent": "MiRadarMusical/1.0", "Accept": "application/json"}
        )
        with urlopen(peticion, timeout=8) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))

        resultados = datos.get("data", []) if fuente == "Deezer" else datos.get("results", [])
        mejor = None
        mejor_puntuacion = 0.0

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

            similitud_titulo = max(
                difflib.SequenceMatcher(None, variante, titulo_resultado).ratio()
                for variante in variantes_titulo
            )
            if any(
                variante and (variante in titulo_resultado or titulo_resultado in variante)
                for variante in variantes_titulo
            ):
                similitud_titulo = max(similitud_titulo, 0.94)

            # Compara cada colaborador por separado: un catálogo puede mostrar
            # solo al artista principal aunque la ficha de origen liste varios.
            similitud_artista = max(
                difflib.SequenceMatcher(None, candidato, artista_resultado).ratio()
                for candidato in artistas_objetivo
            )
            if any(
                candidato and (
                    candidato in artista_resultado or artista_resultado in candidato
                )
                for candidato in artistas_objetivo
            ):
                similitud_artista = max(similitud_artista, 0.90)

            puntuacion = similitud_titulo * 0.65 + similitud_artista * 0.35
            if puntuacion > mejor_puntuacion:
                mejor_puntuacion = puntuacion
                mejor = {
                    "previewUrl": preview,
                    "trackViewUrl": enlace,
                    "titulo": titulo_original,
                    "artista": artista_original,
                    "fuente": fuente,
                    "_similitud_titulo": similitud_titulo,
                    "_similitud_artista": similitud_artista
                }

        if (
            not mejor or mejor_puntuacion < 0.76
            or mejor["_similitud_titulo"] < 0.72
            or mejor["_similitud_artista"] < 0.60
        ):
            return None

        mejor.pop("_similitud_titulo", None)
        mejor.pop("_similitud_artista", None)
        return mejor

    errores = []
    proveedores = [
        ("Deezer", "https://api.deezer.com/search?", "q", 50),
        ("Apple Music/iTunes", "https://itunes.apple.com/search?", "term", 50)
    ]

    for fuente, base_url, parametro, limite in proveedores:
        for consulta in consultas:
            parametros = {parametro: consulta, "limit": limite}
            if fuente != "Deezer":
                parametros.update({"country": "es", "media": "music", "entity": "song"})
            try:
                resultado = buscar_en_catalogo(
                    base_url + urlencode(parametros), fuente
                )
                if resultado:
                    # Si se pidió un directo y solo existe muestra de estudio,
                    # lo avisamos en la interfaz en vez de presentarlo como directo.
                    titulo_pedido = normalizar_texto(titulo)
                    titulo_encontrado = normalizar_texto(resultado.get("titulo"))
                    pedido_directo = any(
                        marca in titulo_pedido
                        for marca in ("live", "en directo", "from")
                    )
                    encontrado_directo = any(
                        marca in titulo_encontrado
                        for marca in ("live", "en directo")
                    )
                    if pedido_directo and not encontrado_directo:
                        resultado["nota"] = (
                            "Se ha encontrado la versión de estudio; no es la grabación en directo."
                        )
                    return jsonify({**resultado, "duracion": 30})
            except Exception:
                if fuente not in errores:
                    errores.append(fuente)

    if len(errores) == 2:
        return jsonify({
            "error": "No se ha podido consultar Deezer ni Apple Music/iTunes ahora mismo."
        }), 502

    return jsonify({
        "error": "No he encontrado una muestra de 30 segundos que coincida con seguridad en Deezer ni en Apple Music/iTunes."
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


@app.get("/api/publicaciones/preview")
def preview_publicacion():
    """Busca una muestra de Deezer para una publicación por artista y título."""
    artista = (request.args.get("artista") or "").strip()
    titulo = (request.args.get("titulo") or "").strip()
    if not artista or not titulo:
        return jsonify({"error": "Faltan artista o título de la publicación."}), 400
    try:
        consulta = urlencode({"q": artista + " " + titulo, "limit": 25})
        peticion = Request("https://api.deezer.com/search/track?" + consulta,
                           headers={"User-Agent": "MiRadarMusical/1.0"})
        with urlopen(peticion, timeout=4) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        objetivo_artista = normalizar_texto(artista)
        objetivo_titulo = normalizar_texto(titulo)
        mejor = None
        mejor_puntuacion = 0.0
        for pista in datos.get("data") or []:
            nombre_artista = normalizar_texto((pista.get("artist") or {}).get("name") or "")
            nombre_titulo = normalizar_texto(pista.get("title") or "")
            similitud_artista = difflib.SequenceMatcher(None, objetivo_artista, nombre_artista).ratio()
            similitud_titulo = difflib.SequenceMatcher(None, objetivo_titulo, nombre_titulo).ratio()
            if similitud_artista < 0.86 or similitud_titulo < 0.72:
                continue
            puntuacion = similitud_artista * 0.45 + similitud_titulo * 0.55
            if puntuacion > mejor_puntuacion:
                mejor, mejor_puntuacion = pista, puntuacion
        if mejor and mejor.get("preview"):
            return jsonify({"preview": mejor.get("preview"), "titulo": mejor.get("title") or titulo})

        # Si el título es un álbum/EP y no una canción, buscar el lanzamiento
        # y usar la primera pista con muestra disponible.
        consulta_album = urlencode({"q": artista + " " + titulo, "limit": 15})
        peticion_album = Request("https://api.deezer.com/search/album?" + consulta_album,
                                 headers={"User-Agent": "MiRadarMusical/1.0"})
        with urlopen(peticion_album, timeout=4) as respuesta_album:
            datos_album = json.loads(respuesta_album.read().decode("utf-8"))
        mejor_album = None
        puntuacion_album = 0.0
        for album in datos_album.get("data") or []:
            nombre_album = normalizar_texto(album.get("title") or "")
            nombre_artista = normalizar_texto((album.get("artist") or {}).get("name") or "")
            sim_artista = difflib.SequenceMatcher(None, objetivo_artista, nombre_artista).ratio()
            sim_titulo = difflib.SequenceMatcher(None, objetivo_titulo, nombre_album).ratio()
            if sim_artista < 0.86 or sim_titulo < 0.72:
                continue
            puntuacion = sim_artista * 0.45 + sim_titulo * 0.55
            if puntuacion > puntuacion_album:
                mejor_album, puntuacion_album = album, puntuacion
        if mejor_album and mejor_album.get("id"):
            peticion_pistas = Request(
                "https://api.deezer.com/album/" + str(mejor_album["id"]) + "/tracks",
                headers={"User-Agent": "MiRadarMusical/1.0"}
            )
            with urlopen(peticion_pistas, timeout=4) as respuesta_pistas:
                datos_pistas = json.loads(respuesta_pistas.read().decode("utf-8"))
            pista_preview = next((p for p in (datos_pistas.get("data") or []) if p.get("preview")), None)
            if pista_preview:
                return jsonify({"preview": pista_preview["preview"],
                                "titulo": pista_preview.get("title") or titulo})
        return jsonify({"error": "Deezer no ofrece una muestra de 30 segundos para esta publicación."}), 404
    except Exception as error:
        app.logger.info("No se pudo buscar una muestra de publicación: %s", error)
        return jsonify({"error": "No se ha podido consultar la muestra ahora mismo."}), 502


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