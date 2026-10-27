"""Prepara resúmenes musicales verificados para que la web no consulte en cada clic."""
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
CSV_PATH = ROOT / "mi_radar_musical.csv"
DATA_PATH = ROOT / "lanzamientos.json"
CACHE_PATH = APP / "resumenes_musicales.json"
MAX_ARTISTAS = 18
MAX_CANCIONES = 30
REINTENTO_DIAS = 7


def normalizar(valor):
    valor = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode("ascii").upper()
    return re.sub(r"[^A-Z0-9]+", " ", valor).strip()


def clave(tipo, nombre, artista=""):
    return "|".join((tipo, normalizar(nombre), normalizar(artista)))


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cargar_json(ruta, predeterminado):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return predeterminado


def leer_objetivos():
    artistas = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            nombre = (fila.get("NombreOriginal") or fila.get("NombreNormalizado") or "").strip()
            estado = (fila.get("Estado") or "").casefold()
            if nombre and "pendiente" not in estado and "descart" not in estado:
                artistas.append(nombre)

    canciones = []
    datos = cargar_json(DATA_PATH, {})
    if isinstance(datos, dict):
        for item in datos.values():
            artista = (item.get("nombre_musicbrainz") or "").strip()
            publicaciones = item.get("publicaciones") or {}
            if not artista or not isinstance(publicaciones, dict):
                continue
            ordenadas = sorted(
                publicaciones.values(),
                key=lambda p: str(p.get("fecha") or ""),
                reverse=True,
            )
            for p in ordenadas[:20]:
                titulo = (p.get("titulo") or "").strip()
                if titulo and str(p.get("tipo") or "").casefold() not in ("video", "audiovisual"):
                    canciones.append((titulo, artista))
    # Evitar duplicados conservando el nombre que aparece en los datos originales.
    return list(dict.fromkeys(artistas)), list(dict.fromkeys(canciones))


def preparar_resumen(cliente, tipo, nombre, artista, cache):
    k = clave(tipo, nombre, artista)
    previo = cache["items"].get(k)
    # Las fichas de Wikipedia también son válidas como último recurso; no se invalidan.
    if previo:
        try:
            reintentar = datetime.fromisoformat(previo.get("reintentar_despues", ""))
            if reintentar > datetime.now(timezone.utc):
                return False
        except (ValueError, TypeError):
            if previo.get("encontrado") and str(previo.get("fuente_tipo") or "").casefold() in ("gemini", "lastfm", "wikipedia"):
                return False

    query = {"tipo": tipo, "nombre": nombre}
    if artista:
        query["artista"] = artista
    respuesta = cliente.get("/api/resumen-musical", query_string=query)
    datos = respuesta.get_json(silent=True) or {}
    fuente_tipo = str(datos.get("fuente_tipo") or "fuente_musical")
    if respuesta.status_code != 200 or not datos.get("encontrado"):
        # No recurrir a Wikipedia: guardar el fallo para reintentarlo más adelante.
        cache["items"][k] = {
            "tipo": tipo, "nombre": nombre, "artista": artista,
            "encontrado": False, "fuentes": [], "comprobado": ahora(),
            "reintentar_despues": (datetime.now(timezone.utc) + timedelta(days=REINTENTO_DIAS)).isoformat(timespec="seconds"),
        }
        return False

    resumen = re.sub(r"\s+", " ", str(datos.get("resumen") or "")).strip()
    if not resumen or len(resumen) < 80:
        cache["items"][k] = {
            "tipo": tipo, "nombre": nombre, "artista": artista,
            "encontrado": False, "fuentes": [], "comprobado": ahora(),
            "reintentar_despues": (datetime.now(timezone.utc) + timedelta(days=REINTENTO_DIAS)).isoformat(timespec="seconds"),
        }
        return False

    # Resúmenes cortos, legibles en móvil; conserva frases completas.
    max_palabras = 220 if tipo == "artista" else 180
    palabras = resumen.split()
    if len(palabras) > max_palabras:
        resumen = " ".join(palabras[:max_palabras]).rsplit(" ", 1)[0].rstrip(" ,;:") + "…"

    fuentes = datos.get("fuentes") or []
    fuentes = [
        {"titulo": str(f.get("titulo") or "Fuente consultada")[:120], "url": str(f.get("url") or "")}
        for f in fuentes
        if isinstance(f, dict) and str(f.get("url") or "").startswith("https://")
    ][:4]
    if not fuentes:
        cache["items"][k] = {
            "tipo": tipo, "nombre": nombre, "artista": artista,
            "encontrado": False, "fuentes": [], "comprobado": ahora(),
            "reintentar_despues": (datetime.now(timezone.utc) + timedelta(days=REINTENTO_DIAS)).isoformat(timespec="seconds"),
        }
        return False

    cache["items"][k] = {
        "tipo": tipo, "nombre": nombre, "artista": artista,
        "encontrado": True, "resumen": resumen, "fuentes": fuentes,
        "fuente_tipo": fuente_tipo, "titulo": datos.get("titulo") or nombre,
        "comprobado": ahora(),
    }
    return True


def guardar(cache):
    temporal = CACHE_PATH.with_suffix(".tmp")
    temporal.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(CACHE_PATH)


def main():
    sys.path.insert(0, str(APP))
    from servidor import app

    cache = cargar_json(CACHE_PATH, {"version": 1, "actualizado": None, "items": {}})
    if not isinstance(cache, dict) or not isinstance(cache.get("items"), dict):
        cache = {"version": 1, "actualizado": None, "items": {}}

    artistas, canciones = leer_objetivos()
    def necesita_actualizacion(item):
        if not isinstance(item, dict):
            return True
        if item.get("encontrado"):
            return str(item.get("fuente_tipo") or "").casefold() not in ("gemini", "lastfm", "wikipedia")
        return item.get("reintentar_despues", "") < ahora()

    pendientes_artistas = [a for a in artistas if necesita_actualizacion(cache["items"].get(clave("artista", a)))]
    pendientes_canciones = [p for p in canciones if necesita_actualizacion(cache["items"].get(clave("cancion", p[0], p[1])))]

    print(f"Resúmenes pendientes: {len(pendientes_artistas)} artistas y {len(pendientes_canciones)} canciones.", flush=True)
    procesados = 0
    with app.test_client() as cliente:
        for nombre in pendientes_artistas[:MAX_ARTISTAS]:
            try:
                ok = preparar_resumen(cliente, "artista", nombre, "", cache)
                procesados += 1
                print(f"{'OK' if ok else 'Sin fuente fiable'} artista: {nombre}", flush=True)
            except Exception as error:
                print(f"AVISO artista {nombre}: {error}", flush=True)
            if procesados % 5 == 0:
                cache["actualizado"] = ahora()
                guardar(cache)
            time.sleep(0.25)

        for titulo, artista in pendientes_canciones[:MAX_CANCIONES]:
            try:
                ok = preparar_resumen(cliente, "cancion", titulo, artista, cache)
                procesados += 1
                print(f"{'OK' if ok else 'Sin fuente fiable'} canción: {titulo} — {artista}", flush=True)
            except Exception as error:
                print(f"AVISO canción {titulo} — {artista}: {error}", flush=True)
            if procesados % 5 == 0:
                cache["actualizado"] = ahora()
                guardar(cache)
            time.sleep(0.25)

    cache["actualizado"] = ahora()
    guardar(cache)
    encontrados = sum(1 for item in cache["items"].values() if item.get("encontrado"))
    print(f"Caché guardada: {encontrados} fichas verificadas de {len(cache['items'])} consultadas.", flush=True)


if __name__ == "__main__":
    main()
