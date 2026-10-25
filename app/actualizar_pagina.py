from pathlib import Path

p = Path.home() / "Desktop" / "Pagina radar musica" / "app" / "index.html"

html = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mi Radar Musical</title>
<style>
body{font-family:Arial,sans-serif;max-width:1000px;margin:35px auto;padding:0 18px;background:#10131b;color:#f2f4f8}
h1{color:#76e0c2}input,select{padding:12px;margin:5px;border-radius:8px;border:1px solid #444;background:#202633;color:white}
#total{color:#aaa;margin:15px 5px}.artista{padding:12px;margin:7px 0;background:#202633;border-radius:8px}
.estado{color:#76e0c2;font-size:13px}button{padding:10px;border-radius:8px;cursor:pointer}
</style>
</head>
<body>
<h1>Mi Radar Musical</h1>
<p>Tu lista de artistas, preparada para organizar el seguimiento musical.</p>
<input id="buscar" placeholder="Buscar artista..." style="width:60%">
<select id="estado"><option value="">Todos los estados</option></select>
<div id="total">Cargando artistas...</div>
<div id="lista"></div>
<script>
let artistas=[];
const buscar=document.getElementById('buscar');
const estado=document.getElementById('estado');
const lista=document.getElementById('lista');
const total=document.getElementById('total');
function mostrar(){
 const q=buscar.value.toLocaleLowerCase('es').trim();
 const e=estado.value;
 const filtrados=artistas.filter(a=>
  (a.NombreOriginal||'').toLocaleLowerCase('es').includes(q) &&
  (!e || a.Estado===e)
 );
 total.textContent=filtrados.length+' artistas';
 lista.innerHTML='';
 filtrados.forEach(a=>{
  const div=document.createElement('div');
  div.className='artista';
  const nombre=document.createElement('strong');
  nombre.textContent=a.NombreOriginal||a.NombreNormalizado||'Sin nombre';
  div.appendChild(nombre);
  if(a.Estado){
   const est=document.createElement('div');
   est.className='estado';
   est.textContent=a.Estado;
   div.appendChild(est);
  }
  if(a.Observaciones){
   const obs=document.createElement('div');
   obs.textContent=a.Observaciones;
   div.appendChild(obs);
  }
  lista.appendChild(div);
 });
}
fetch('/api/artistas').then(r=>{
 if(!r.ok) throw new Error('Error al cargar el CSV');
 return r.json();
}).then(datos=>{
 artistas=datos;
 [...new Set(artistas.map(a=>a.Estado).filter(Boolean))].sort().forEach(e=>{
  const op=document.createElement('option');op.value=e;op.textContent=e;estado.appendChild(op);
 });
 mostrar();
}).catch(()=>{
 total.textContent='No se ha podido cargar la lista. Comprueba que el servidor sigue abierto.';
});
buscar.addEventListener('input',mostrar);
estado.addEventListener('change',mostrar);
</script>
</body>
</html>
"""

p.write_text(html, encoding="utf-8")
print("Página actualizada:", p)
print("Tamaño:", p.stat().st_size, "bytes")
