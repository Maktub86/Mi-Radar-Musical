import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import servidor


class FichasMusicalesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta_original = servidor._RUTA_FICHAS_DB
        servidor._RUTA_FICHAS_DB = Path(self.tmp.name) / "fichas.sqlite3"
        self.cliente = servidor.app.test_client()

    def tearDown(self):
        servidor._RUTA_FICHAS_DB = self.ruta_original
        self.tmp.cleanup()

    def test_ficha_artista_se_guarda_y_se_reutiliza(self):
        artista_mb = {
            "artists": [{
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "Artista de prueba",
                "type": "Person",
                "country": "ES",
                "life-span": {"begin": "2000"}
            }]
        }
        with patch.object(servidor, "_musicbrainz_consultar", return_value=artista_mb) as consulta_mb, \
             patch.object(servidor, "_lastfm_consultar", return_value=None), \
             patch.object(servidor, "api_wikipedia", return_value=(
                 servidor.app.response_class('{"encontrado": false, "fuente_tipo": "ninguna"}', mimetype="application/json"), 200
             )):
            primera = self.cliente.get(
                "/api/ficha-musical?tipo=artista&nombre=Artista%20de%20prueba"
            )
            segunda = self.cliente.get(
                "/api/ficha-musical?tipo=artista&nombre=Artista%20de%20prueba"
            )

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(primera.json["datos_musicales"]["pais"], "ES")
        self.assertTrue(segunda.json["desde_cache"])
        self.assertEqual(consulta_mb.call_count, 1)

    def test_ficha_rechaza_parametros_incompletos(self):
        respuesta = self.cliente.get("/api/ficha-musical")
        self.assertEqual(respuesta.status_code, 400)


if __name__ == "__main__":
    unittest.main()
