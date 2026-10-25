from pathlib import Path

p = Path.home() / "Desktop" / "Pagina radar musica" / "app" / "detector.py"
s = p.read_text(encoding="utf-8-sig")

inicio = s.index("def publicaciones(artista):")
fin = s.index("\ndef main():", inicio)

nuevo = '''def publicaciones(artista):
    todas = []
    offset = 0

    while True:
        url = "https://musicbrainz.org/ws/2/release-group/?" + urllib.parse.urlencode({
            "artist": artista["id"],
            "fmt": "json",
            "limit": 100,
            "offset": offset
        })
        respuesta = consultar(url)
        grupos = respuesta.get("release-groups", [])

        if not grupos:
            break

        todas.extend(grupos)
        print(f"  Publicaciones recopiladas: {len(todas)}", flush=True)

        if len(grupos) < 100:
            break

        offset += len(grupos)

    return {
        g["id"]: {
            "titulo": g["title"],
            "fecha": g.get("first-release-date", ""),
            "tipo": g.get("primary-type", ""),
            "artista": artista["name"]
        }
        for g in todas
    }

'''

p.write_text(s[:inicio] + nuevo + s[fin:], encoding="utf-8")
print("Detector actualizado correctamente.")
