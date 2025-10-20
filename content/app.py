from flask import Flask, request, redirect, make_response, render_template_string
import sqlite3
import urllib
from markupsafe import escape
import quoter_templates as templates

app = Flask(__name__)
app.static_folder = '.'

# Open de database – queries geven dicts terug
db = sqlite3.connect("db.sqlite3", check_same_thread=False)
db.row_factory = sqlite3.Row

# Log alle requests
log_file = open('access.log', 'a', buffering=1)

@app.before_request
def log_request():
    log_file.write(f"{request.method} {request.path} {dict(request.form) if request.form else ''}\n")

# Controleer of gebruiker is ingelogd
@app.before_request
def check_authentication():
    if 'user_id' in request.cookies:
        try:
            request.user_id = int(request.cookies['user_id'])
        except ValueError:
            request.user_id = None
    else:
        request.user_id = None


# 📄 Hoofdpagina
@app.route("/")
def index():
    quotes = db.execute(
        "SELECT id, text, attribution FROM quotes ORDER BY id"
    ).fetchall()
    error = escape(request.args.get("error", ""))  # ✅ XSS fix
    return templates.main_page(quotes, request.user_id, error)


# 💬 Quote comments pagina
@app.route("/quotes/<int:quote_id>")
def get_comments_page(quote_id):
    quote = db.execute(
        "SELECT id, text, attribution FROM quotes WHERE id = ?", (quote_id,)
    ).fetchone()

    if not quote:
        return "Quote not found", 404

    comments = db.execute(
        """
        SELECT text, datetime(time,'localtime') AS time, name AS user_name
        FROM comments c
        LEFT JOIN users u ON u.id = c.user_id
        WHERE quote_id = ?
        ORDER BY c.id
        """,
        (quote_id,),
    ).fetchall()

    return templates.comments_page(quote, comments, request.user_id)


# ✍️ Nieuwe quote plaatsen
@app.route("/quotes", methods=["POST"])
def post_quote():
    text = escape(request.form.get("text", ""))  # ✅ ontsmet input
    attribution = escape(request.form.get("attribution", ""))

    with db:
        db.execute(
            "INSERT INTO quotes (text, attribution) VALUES (?, ?)",
            (text, attribution),
        )
    return redirect("/#bottom")


# 💭 Nieuwe comment plaatsen
@app.route("/quotes/<int:quote_id>/comments", methods=["POST"])
def post_comment(quote_id):
    if request.user_id is None:
        return redirect(f"/quotes/{quote_id}?error=" + urllib.parse.quote("Login required"))

    text = escape(request.form.get("text", ""))  # ✅ ontsmet input

    with db:
        db.execute(
            "INSERT INTO comments (text, quote_id, user_id) VALUES (?, ?, ?)",
            (text, quote_id, request.user_id),
        )
    return redirect(f"/quotes/{quote_id}#bottom")


# 🔐 Inloggen of registreren
@app.route("/signin", methods=["POST"])
def signin():
    username = request.form.get("username", "").lower()
    password = request.form.get("password", "")

    user = db.execute(
        "SELECT id, password FROM users WHERE name = ?", (username,)
    ).fetchone()

    if user:
        if password != user["password"]:
            return redirect("/?error=" + urllib.parse.quote("Invalid password!"))
        user_id = user["id"]
    else:
        with db:
            cursor = db.execute(
                "INSERT INTO users (name, password) VALUES (?, ?)",
                (username, password),
            )
            user_id = cursor.lastrowid

    response = make_response(redirect("/"))
    response.set_cookie(
        "user_id",
        str(user_id),
        secure=True,
        httponly=True,
        samesite="Lax",
        max_age=60 * 60 * 24 * 7,  # 7 dagen geldig
    )
    return response


# 🚪 Uitloggen
@app.route("/signout", methods=["GET"])
def signout():
    response = make_response(redirect("/"))
    response.delete_cookie("user_id")
    return response
