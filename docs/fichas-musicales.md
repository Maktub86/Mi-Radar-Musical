# Fichas musicales

## Fuentes y comportamiento

- **MusicBrainz** se consulta para identificar coincidencias exactas y recuperar metadatos estructurados de artistas y grabaciones.
- **Last.fm** es opcional. Para activarlo, configura la variable de entorno `LASTFM_API_KEY` en el servicio de despliegue. No guardes la clave en el repositorio.
- **Wikipedia** se consulta como fuente complementaria cuando falta la biografía del artista o la historia de la canción.
- No se inventan curiosidades ni créditos de composición cuando no hay una fuente confirmada disponible.
- Las fichas correctas se guardan en SQLite y se reutilizan en consultas posteriores.

## Persistencia en Render

La base de datos se escribe en `MR_FICHAS_DB` si esa variable está configurada; de lo contrario, se usa `fichas_musicales.sqlite3` en el directorio raíz del proyecto.

Para conservar las fichas después de un nuevo despliegue, configura un disco persistente en Render y establece `MR_FICHAS_DB` en una ruta dentro del punto de montaje de ese disco, por ejemplo `/ruta/de/montaje/fichas_musicales.sqlite3`. Sustituye el ejemplo por la ruta real del disco configurado en el servicio.

Sin un disco persistente, el archivo SQLite puede perderse al recrearse la instancia. La caché seguirá funcionando mientras el archivo exista, pero no se debe asumir persistencia entre despliegues.

## Validación

El flujo de GitHub Actions comprueba la sintaxis Python y la importación del servidor. Estas comprobaciones no garantizan que las APIs externas estén disponibles ni sustituyen una prueba funcional en navegador.
