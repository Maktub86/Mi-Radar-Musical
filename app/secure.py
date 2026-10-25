"""Capa de acceso con contraseña para Mi Radar Musical en Render.

Este módulo envuelve la aplicación Flask existente sin modificar servidor.py.
Configurar en Render: RADAR_USER, RADAR_PASSWORD y FLASK_SECRET_KEY.
"""
import hmac
import os
from flask import abort, redirect, render_template_string, request, session, url_for

from servidor import app

LOGIN_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acceso · Mi Radar Musical</title>
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
</main></body></html>"""

@app.before_request
def exigir_acceso():
    if not all(os.environ.get(k) for k in ("RADAR_USER", "RADAR_PASSWORD", "FLASK_SECRET_KEY")):
        return (
            "Falta configurar RADAR_USER, RADAR_PASSWORD y FLASK_SECRET_KEY en las variables de entorno de Render.",
            503,
            {"Content-Type": "text/plain; charset=utf-8"},
        )
    app.secret_key = os.environ["FLASK_SECRET_KEY"]
    if request.endpoint in {"login"}:
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
