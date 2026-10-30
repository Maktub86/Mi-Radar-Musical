"""Capa de acceso con contraseña para Mi Radar Musical en Render.

Este módulo envuelve la aplicación Flask existente sin modificar servidor.py.
Configurar en Render: RADAR_USER, RADAR_PASSWORD y FLASK_SECRET_KEY.
"""
import hashlib
import hmac
import os
import secrets
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from pathlib import Path

from flask import redirect, render_template_string, request, session, url_for

# Permite cargar los módulos que están junto a servidor.py.
APP_DIR = str(Path(__file__).resolve().parent)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from servidor import app

# La clave debe estar disponible antes de que Flask abra la sesión.
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

LOGIN_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acceso · Mi Radar Musical</title>
<link rel="icon" type="image/png" sizes="192x192" href="/icono-mrm-192.png?v=13">
<link rel="icon" type="image/svg+xml" href="/icono-mrm.svg?v=13">
<link rel="apple-touch-icon" sizes="192x192" href="/icono-mrm-192.png?v=13">
<link rel="manifest" href="/manifest.webmanifest?v=13">
<meta name="theme-color" content="#6d28a8">
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(140deg,#17152d,#10101c 55%,#26152e);color:#f7f5ff;font-family:Segoe UI,Arial,sans-serif;padding:20px}
main{width:min(420px,100%);background:#1b1b2d;border:1px solid #ffffff20;border-radius:18px;padding:28px;box-shadow:0 18px 55px #0006}
h1{margin:0 0 8px;font-size:27px}p{color:#b8b6cf;line-height:1.5}label{display:block;margin:16px 0 6px;font-size:14px}
input{width:100%;padding:12px;border:1px solid #ffffff30;border-radius:9px;background:#10101c;color:white;font-size:16px}
button{width:100%;margin-top:20px;padding:12px;border:0;border-radius:9px;background:linear-gradient(100deg,#706bff,#b72d83);color:white;font-weight:700;font-size:16px;cursor:pointer}
.error{color:#ff9dbb;background:#51233b;padding:10px;border-radius:8px}
</style>
</head>
<body><main>
<div style="font-size:13px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:#76e0c2">Tu universo musical</div>
<h1>Mi Radar Musical 🎧</h1>
<p>Introduce tus credenciales para entrar.</p>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/login">
<label for="username">Usuario</label><input id="username" name="username" autocomplete="username" required autofocus>
<label for="password">Contraseña</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Entrar</button>
</form>
<p style="text-align:center;margin:18px 0 0"><a href="/recuperar" style="color:#c6a8ff">He olvidado cómo entrar</a></p>
</main></body></html>"""

RECUPERACION_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recuperar acceso · Mi Radar Musical</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(140deg,#17152d,#10101c 55%,#26152e);color:#f7f5ff;font-family:Segoe UI,Arial,sans-serif;padding:20px}
main{width:min(420px,100%);background:#1b1b2d;border:1px solid #ffffff20;border-radius:18px;padding:28px;box-shadow:0 18px 55px #0006}
h1{margin:0 0 8px;font-size:25px}p{color:#b8b6cf;line-height:1.5}button{width:100%;margin-top:18px;padding:12px;border:0;border-radius:9px;background:linear-gradient(100deg,#706bff,#b72d83);color:white;font-weight:700;font-size:16px;cursor:pointer}
a{color:#c6a8ff}.error{color:#ff9dbb;background:#51233b;padding:10px;border-radius:8px}
</style></head><body><main>
<div style="font-size:13px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:#76e0c2">Tu universo musical</div>
<h1>Recuperar acceso</h1>
<p>Enviaremos un enlace temporal a los dos correos autorizados. Al abrirlo entrarás directamente y tu contraseña seguirá siendo la misma.</p>
{% if mensaje %}<p class="{% if error %}error{% endif %}">{{ mensaje }}</p>{% endif %}
{% if mostrar_formulario %}<form method="post"><button type="submit">Enviar enlace a mis correos</button></form>{% endif %}
<p><a href="/login">Volver al inicio de sesión</a></p>
</main></body></html>"""

CONFIRMAR_RECUPERACION_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Confirmar acceso · Mi Radar Musical</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(140deg,#17152d,#10101c 55%,#26152e);color:#f7f5ff;font-family:Segoe UI,Arial,sans-serif;padding:20px}
main{width:min(420px,100%);background:#1b1b2d;border:1px solid #ffffff20;border-radius:18px;padding:28px;box-shadow:0 18px 55px #0006}
h1{margin:0 0 8px;font-size:25px}p{color:#b8b6cf;line-height:1.5}button{width:100%;margin-top:18px;padding:12px;border:0;border-radius:9px;background:linear-gradient(100deg,#706bff,#b72d83);color:white;font-weight:700;font-size:16px;cursor:pointer}
a{color:#c6a8ff}
</style></head><body><main>
<h1>Confirmar recuperación</h1>
<p>Al continuar entrarás en Mi Radar Musical sin cambiar tu contraseña. Este enlace solo se puede utilizar una vez.</p>
<form method="post"><button type="submit">Entrar en Mi Radar Musical</button></form>
<p><a href="/login">Cancelar</a></p>
</main></body></html>"""


CORREOS_RECUPERACION = (
    "alemartinvera@gmail.com",
    "rociromang@gmail.com",
)
RUTA_PUBLICA_RECUPERACION = {"/login", "/recuperar", "/manifest.webmanifest",
    "/icono-mrm-192.png", "/icono-mrm.svg", "/icono-mrm-maskable.svg", "/favicon.ico"}


def _conexion_recuperacion():
    import psycopg
    url = (os.environ.get("DATABASE_URL") or os.environ.get("RENDER_DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("La base de datos no está configurada.")
    return psycopg.connect(url, connect_timeout=10)


def _preparar_tabla_recuperacion(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS radar_accesos_recuperacion (
            token_hash TEXT PRIMARY KEY,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            caduca_en TIMESTAMPTZ NOT NULL,
            usado_en TIMESTAMPTZ
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS radar_recuperacion_intentos (
            ip_hash TEXT NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cursor.execute("DELETE FROM radar_accesos_recuperacion WHERE caduca_en < NOW() - INTERVAL '1 day'")
    cursor.execute("DELETE FROM radar_recuperacion_intentos WHERE creado_en < NOW() - INTERVAL '1 day'")


def _enviar_enlace_recuperacion(enlace):
    host = os.environ.get("SMTP_HOST", "").strip()
    usuario = os.environ.get("SMTP_USER", "").strip()
    clave = os.environ.get("SMTP_PASSWORD", "")
    puerto = int(os.environ.get("SMTP_PORT", "587"))
    remitente = os.environ.get("SMTP_FROM", "").strip() or usuario
    if not all((host, usuario, clave, remitente)):
        raise RuntimeError("Falta configurar el servicio de correo en Render.")

    for destinatario in CORREOS_RECUPERACION:
        mensaje = EmailMessage()
        mensaje["Subject"] = "Enlace para recuperar el acceso a Mi Radar Musical"
        mensaje["From"] = remitente
        mensaje["To"] = destinatario
        mensaje.set_content(
            "Has solicitado recuperar el acceso a Mi Radar Musical.\n\n"
            "Abre este enlace para entrar sin cambiar tu contraseña. "
            "El enlace caduca en 15 minutos y solo se puede utilizar una vez:\n\n"
            f"{enlace}\n\n"
            "Si no has solicitado este acceso, ignora este mensaje."
        )
        with smtplib.SMTP(host, puerto, timeout=15) as servidor:
            servidor.ehlo()
            servidor.starttls()
            servidor.ehlo()
            servidor.login(usuario, clave)
            servidor.send_message(mensaje)


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar_acceso():
    mensaje = None
    error = False
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest()
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        try:
            with _conexion_recuperacion() as conexion:
                with conexion.cursor() as cursor:
                    _preparar_tabla_recuperacion(cursor)
                    cursor.execute("""
                        SELECT COUNT(*) FROM radar_recuperacion_intentos
                        WHERE ip_hash = %s AND creado_en > NOW() - INTERVAL '1 hour'
                    """, (ip_hash,))
                    if cursor.fetchone()[0] >= 5:
                        mensaje = "Has solicitado varios enlaces. Espera un rato antes de volver a intentarlo."
                        error = True
                    else:
                        cursor.execute(
                            "INSERT INTO radar_recuperacion_intentos (ip_hash) VALUES (%s)",
                            (ip_hash,)
                        )
                        cursor.execute(
                            "INSERT INTO radar_accesos_recuperacion (token_hash, caduca_en) "
                            "VALUES (%s, NOW() + INTERVAL '15 minutes')",
                            (token_hash,)
                        )
            if not error:
                base = os.environ.get("RECOVERY_BASE_URL", "https://mi-radar-musical.onrender.com").rstrip("/")
                enlace = f"{base}/acceso-recuperacion/{token}"
                _enviar_enlace_recuperacion(enlace)
                mensaje = "Si el servicio de correo está configurado, recibirás el enlace en los dos correos autorizados. Caduca en 15 minutos."
        except Exception:
            app.logger.exception("No se pudo completar la solicitud de recuperación.")
            try:
                with _conexion_recuperacion() as conexion:
                    with conexion.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM radar_accesos_recuperacion WHERE token_hash = %s",
                            (token_hash,)
                        )
            except Exception:
                app.logger.exception("No se pudo invalidar el enlace no enviado.")
            mensaje = "Ahora mismo no se ha podido enviar el enlace. Inténtalo más tarde."
            error = True
    return render_template_string(
        RECUPERACION_HTML, mensaje=mensaje, error=error, mostrar_formulario=not mensaje
    )


@app.route("/acceso-recuperacion/<token>", methods=["GET", "POST"])
def acceso_recuperacion(token):
    if request.method == "GET":
        # No consumir el token en GET: algunos servicios de correo inspeccionan
        # automáticamente los enlaces antes de que el usuario los abra.
        return render_template_string(CONFIRMAR_RECUPERACION_HTML)

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    try:
        with _conexion_recuperacion() as conexion:
            with conexion.cursor() as cursor:
                _preparar_tabla_recuperacion(cursor)
                cursor.execute("""
                    UPDATE radar_accesos_recuperacion
                    SET usado_en = NOW()
                    WHERE token_hash = %s AND usado_en IS NULL AND caduca_en > NOW()
                    RETURNING token_hash
                """, (token_hash,))
                valido = cursor.fetchone() is not None
        if valido:
            session.clear()
            session["radar_autenticado"] = True
            return redirect("/")
    except Exception:
        app.logger.exception("No se pudo validar el enlace de recuperación.")
    return render_template_string(
        RECUPERACION_HTML,
        mensaje="Este enlace no es válido, ya se ha utilizado o ha caducado. Solicita uno nuevo.",
        error=True,
        mostrar_formulario=False,
    ), 400


@app.before_request
def exigir_acceso():
    if not all(os.environ.get(k) for k in ("RADAR_USER", "RADAR_PASSWORD", "FLASK_SECRET_KEY")):
        return (
            "Falta configurar RADAR_USER, RADAR_PASSWORD y FLASK_SECRET_KEY en las variables de entorno de Render.",
            503,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    # El navegador necesita poder descargar estos recursos antes de iniciar sesión
    # para mostrar el icono correcto al crear el acceso directo en Android.
    if request.path in RUTA_PUBLICA_RECUPERACION or request.path.startswith("/acceso-recuperacion/"):
        return None

    if session.get("radar_autenticado") is True:
        return None
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("username", "")
        clave = request.form.get("password", "")
        usuario_ok = hmac.compare_digest(usuario, os.environ["RADAR_USER"])
        clave_ok = hmac.compare_digest(clave, os.environ["RADAR_PASSWORD"])
        if usuario_ok and clave_ok:
            session.clear()
            session["radar_autenticado"] = True
            return redirect("/")
        error = "Usuario o contraseña incorrectos."
    return render_template_string(LOGIN_HTML, error=error)

@app.after_request
def proteger_sesion(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response
