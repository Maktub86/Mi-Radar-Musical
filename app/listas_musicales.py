import json
import re
import threading
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
CACHE = BASE / "listas_cache"
CACHE.mkdir(exist_ok=True)

FUENTES = {
    "los40": {
        "nombre": "LOS40",
        "url": "https://los40.com/lista40/",
        "tipo": "los40",
    },
    "canal-fiesta": {
        "nombre": "Canal Fiesta · Top 50",
        "url": "https://www.canalsur.es/radio/canal-fiesta/top-50/",
        "tipo": "canal",
    },
    "youtube": {
        "nombre": "Tendencias musicales de YouTube",
        "url": "https://charts.youtube.com/charts/TrendingVideos/es",
        "tipo": "youtube",
    },
}

_LOCKS = {k: threading.Lock() for k in FUENTES}


class TextoHTML(HTMLParser):
    """Extrae texto visible y títulos HTML sin depender de paquetes externos."""
    BLOQUES = {
        "p", "div", "li", "h1", "h2", "h3", "h4", "section", "article",
        "br", "tr", "td", "span"
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lineas = []
        self.actual = []
        self.titulo = []
        self.en_titulo = False
        self.titulos = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOQUES:
            self._cortar()
        if tag in ("h1", "h2", "h3"):
            self.en_titulo = True
            self.titulo = []

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3"):
            texto = " ".join(" ".join(self.titulo).split())
            if texto:
                self.titulos.append(texto)
            self.en_titulo = False
        if tag in self.BLOQUES:
            self._cortar()

    def handle_data(self, data):
        dato = " ".join(data.split())
        if not dato:
            return
        self.actual.append(dato)
        if self.en_titulo:
            self.titulo.append(dato)

    def _cortar(self):
        texto = " ".join(" ".join(self.actual).split())
        if texto:
            self.lineas.append(texto)
        self.actual = []

    def cerrar(self):
        super().close()
        self._cortar()


def _leer(url, timeout=25):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
    })
    with urlopen(req, timeout=timeout) as respuesta:
        return respuesta.read()


def _texto_html(raw):
    parser = TextoHTML()
    parser.feed(raw.decode("utf-8", errors="replace"))
    parser.cerrar()
    return parser


def _limpiar_canciones(items, limite):
    salida = []
    vistos = set()
    for item in items:
        titulo = " ".join(str(item.get("titulo", "")).split()).strip()
        artista = " ".join(str(item.get("artista", "")).split()).strip()
        if not titulo or not artista:
            continue
        if titulo.casefold() in {"escuchar", "play", "desplegar", "¡vota!"}:
            continue
        clave = (titulo.casefold(), artista.casefold())
        if clave in vistos:
            continue
        vistos.add(clave)
        item["puesto"] = len(salida) + 1
        item["titulo"] = titulo
        item["artista"] = artista
        salida.append(item)
        if len(salida) >= limite:
            break
    if not salida:
        raise RuntimeError("La página de origen no devolvió canciones reconocibles.")
    return salida


def obtener_los40():
    parser = _texto_html(_leer(FUENTES["los40"]["url"]))
    items = []
    lineas = parser.lineas
    titulos = parser.titulos
    ignorar = {
        "sube", "baja", "igual", "nueva", "vota", "¡vota!", "desplegar",
        "escuchar", "play", "semanas en lista", "mejor posición",
        "anterior posición", "lista los40", "los40"
    }

    # Los40 publica el nombre de la canción como encabezado y el artista
    # inmediatamente después en el contenido de cada entrada.
    dentro_lista = False
    for titulo in titulos:
        t = titulo.strip()
        if "lista los40" in t.casefold():
            dentro_lista = True
            continue
        if not dentro_lista:
            continue
        if len(t) < 2 or t.casefold() in ignorar:
            continue
        try:
            idx = lineas.index(t)
        except ValueError:
            # En algunos encabezados, el texto puede contener más de un nodo.
            idx = next((i for i, x in enumerate(lineas) if x.casefold() == t.casefold()), -1)
        if idx < 0:
            continue
        artista = ""
        for candidato in lineas[idx + 1:idx + 7]:
            low = candidato.casefold()
            if low in ignorar or re.fullmatch(r"\d{1,2}", candidato):
                continue
            if candidato.casefold() == t.casefold():
                continue
            if "semanas en lista" in low or "mejor posición" in low or "anterior posición" in low:
                continue
            artista = candidato
            break
        if artista:
            items.append({"titulo": t, "artista": artista, "url": FUENTES["los40"]["url"]})
    return {
        "canciones": _limpiar_canciones(items, 40),
        "fuente": FUENTES["los40"]["url"],
        "nombre": FUENTES["los40"]["nombre"],
    }


def obtener_canal_fiesta():
    parser = _texto_html(_leer(FUENTES["canal-fiesta"]["url"]))
    lineas = parser.lineas
    items = []

    def numero_suelto(texto):
        return re.fullmatch(r"\s*(\d{1,2})\s*\.?\s*", texto)

    def marcador_puesto(indice):
        if indice >= len(lineas):
            return None
        linea = lineas[indice].strip()
        doble = re.fullmatch(r"(\d{1,2})\s*\.?\s+(\d{1,2})", linea)
        if doble:
            return int(doble.group(1)), indice + 1
        simple = numero_suelto(linea)
        if not simple:
            return None
        puesto = int(simple.group(1))
        siguiente = indice + 1
        # Canal Sur puede separar la posición actual y la anterior en dos nodos HTML.
        if siguiente < len(lineas) and numero_suelto(lineas[siguiente].strip()):
            siguiente += 1
        return puesto, siguiente

    ignorar = {"top 50", "escuchar", "play", "votar", "¡vota!", "imagen"}

    i = 0
    while i < len(lineas):
        marcador = marcador_puesto(i)
        if not marcador:
            i += 1
            continue

        puesto, inicio_datos = marcador
        if not 1 <= puesto <= 50:
            i += 1
            continue

        siguientes = []
        j = inicio_datos
        while j < len(lineas):
            # Detecta la siguiente canción aunque Canal Sur entregue los números
            # en dos nodos separados, y no solo cuando aparecen "1. 1" juntos.
            if marcador_puesto(j) and len(siguientes) >= 2:
                break

            valor = lineas[j].strip()
            if valor and valor.casefold() not in ignorar:
                siguientes.append(valor)

            # No dejar que un número suelto se convierta en el artista o título.
            if len(siguientes) >= 2 and j + 1 < len(lineas):
                if numero_suelto(lineas[j + 1].strip()):
                    j += 1
                    break
            j += 1

        if len(siguientes) >= 2:
            items.append({
                "puesto": puesto,
                "artista": siguientes[0],
                "titulo": siguientes[1],
                "url": FUENTES["canal-fiesta"]["url"],
            })

        i = max(i + 1, j)

    canciones = _limpiar_canciones(items, 50)
    for item in canciones:
        item["puesto"] = int(item.get("puesto", 0) or 0)
    canciones.sort(key=lambda x: x["puesto"])
    return {
        "canciones": canciones,
        "fuente": FUENTES["canal-fiesta"]["url"],
        "nombre": FUENTES["canal-fiesta"]["nombre"],
    }

def _buscar_clave(obj, claves):
    if isinstance(obj, dict):
        for k in claves:
            if k in obj and isinstance(obj[k], list) and obj[k]:
                return obj[k]
        for v in obj.values():
            r = _buscar_clave(v, claves)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _buscar_clave(v, claves)
            if r:
                return r
    return None


def obtener_youtube():
    pagina = FUENTES["youtube"]["url"]
    html = _leer(pagina).decode("utf-8", errors="replace")
    m = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
    api_key = m.group(1) if m else "AIzaSyCzEW7JUJdSql0-2V4tHUb6laYm4iAE_dM"

    payload = {
        "browseId": "FEmusic_analytics_charts_home",
        "context": {
            "capabilities": {},
            "client": {
                "clientName": "WEB_MUSIC_ANALYTICS",
                "clientVersion": "0.2",
                "experimentIds": [],
                "experimentsToken": "",
                "gl": "ES",
                "hl": "es",
                "theme": "MUSIC",
            },
            "request": {"internalExperimentFlags": []},
        },
        "query": "chart_params_type=WEEK&perspective=CHART&flags=viral_video_chart&selected_chart=VIDEOS&chart_params_id=weekly:0:0:es",
    }
    url = "https://charts.youtube.com/youtubei/v1/browse?alt=json&key=" + api_key
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Origin": "https://charts.youtube.com",
            "Referer": pagina,
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as respuesta:
        data = json.loads(respuesta.read().decode("utf-8"))

    # Para TrendingVideos, YouTube suele devolver el listado en videos[1].
    # Buscamos esa estructura recursivamente porque el envoltorio puede cambiar.
    def encontrar_tendencias(obj):
        if isinstance(obj, dict):
            bloque = obj.get("videos")
            if isinstance(bloque, list) and len(bloque) > 1:
                candidato = bloque[1]
                if isinstance(candidato, dict) and isinstance(candidato.get("videoViews"), list):
                    return candidato["videoViews"]
            for valor in obj.values():
                encontrado = encontrar_tendencias(valor)
                if encontrado:
                    return encontrado
        elif isinstance(obj, list):
            for valor in obj:
                encontrado = encontrar_tendencias(valor)
                if encontrado:
                    return encontrado
        return None

    videos = encontrar_tendencias(data)
    if not videos:
        videos = _buscar_clave(data, ("videoViews",))
    if not videos:
        raise RuntimeError("YouTube no devolvió su lista de tendencias.")

    items = []
    for v in videos:
        if not isinstance(v, dict):
            continue
        titulo = v.get("title") or v.get("name")
        artistas = v.get("artists") or []
        if isinstance(artistas, list):
            artista = ", ".join(
                str(a.get("name", "")).strip()
                for a in artistas if isinstance(a, dict) and a.get("name")
            )
        else:
            artista = str(artistas or v.get("channelName") or "").strip()
        video_id = v.get("id") or v.get("videoId") or v.get("encryptedVideoId")
        if titulo and not artista:
            artista = v.get("channelName") or "YouTube"
        if titulo and artista:
            items.append({
                "titulo": str(titulo),
                "artista": artista,
                "url": "https://www.youtube.com/watch?v=" + str(video_id) if video_id else pagina,
            })
    return {
        "canciones": _limpiar_canciones(items, 30),
        "fuente": pagina,
        "nombre": FUENTES["youtube"]["nombre"],
    }


_OBTENER = {
    "los40": obtener_los40,
    "canal-fiesta": obtener_canal_fiesta,
    "youtube": obtener_youtube,
}


def cargar(tipo):
    if tipo not in FUENTES:
        raise KeyError(tipo)
    archivo = CACHE / f"{tipo}.json"
    if archivo.exists():
        try:
            return json.loads(archivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "tipo": tipo,
        "nombre": FUENTES[tipo]["nombre"],
        "fuente": FUENTES[tipo]["url"],
        "canciones": [],
        "actualizado": None,
        "en_curso": False,
        "mensaje": "Pulsa «Actualizar» para cargar la lista.",
    }


def actualizar(tipo):
    if tipo not in FUENTES:
        raise KeyError(tipo)
    lock = _LOCKS[tipo]
    if not lock.acquire(blocking=False):
        anterior = cargar(tipo)
        anterior["en_curso"] = True
        anterior["mensaje"] = "Esta lista ya se está actualizando."
        return anterior
    try:
        try:
            resultado = _OBTENER[tipo]()
            resultado.update({
                "tipo": tipo,
                "actualizado": datetime.now().astimezone().isoformat(timespec="minutes"),
                "en_curso": False,
                "mensaje": f"Lista actualizada: {len(resultado['canciones'])} canciones.",
            })
            (CACHE / f"{tipo}.json").write_text(
                json.dumps(resultado, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return resultado
        except Exception as e:
            anterior = cargar(tipo)
            anterior["en_curso"] = False
            anterior["mensaje"] = "No se pudo actualizar. " + str(e)
            anterior["error"] = True
            return anterior
    finally:
        lock.release()
