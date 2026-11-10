import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import timedelta
from functools import wraps

import boto3
from flask_limiter import Limiter
from flask import Flask, Response, jsonify, make_response, redirect, render_template, request, url_for

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)
BUCKET = os.getenv("AWS_S3_BUCKET_NAME")
ADMIN_KEY = os.getenv("KEY")

RESERVED = {"auth", "logout", "panel", "manage", "delete", "rename", "create", "tos",
            "static", "api", "robots.txt", "favicon.ico"}


NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,16}$")
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
MAX_BYTES = 256 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES


# ---------- storage ----------

def exists(name):
    try:
        s3.head_object(Bucket=BUCKET, Key=name)
        return True
    except s3.exceptions.ClientError:
        return False


def list_pastes():
    out = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET):
        for o in page.get("Contents", []):
            out.append({"name": o["Key"], "size": o["Size"], "modified": o["LastModified"]})
    out.sort(key=lambda p: p["modified"], reverse=True)
    return out


def purge(names):
    """Delete every stored version of each name, so nothing lingers in a versioned bucket."""
    names = set(names)
    if not names:
        return
    items = []
    for name in names:
        for page in s3.get_paginator("list_object_versions").paginate(Bucket=BUCKET, Prefix=name):
            for v in page.get("Versions", []) + page.get("DeleteMarkers", []):
                if v["Key"] == name:
                    items.append({"Key": name, "VersionId": v["VersionId"]})
    for i in range(0, len(items), 1000):
        s3.delete_objects(Bucket=BUCKET, Delete={"Objects": items[i:i + 1000], "Quiet": True})


def new_name():
    for length in (4, 4, 4, 5, 6, 8):
        name = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if name not in RESERVED and not exists(name):
            return name
    raise RuntimeError("could not allocate a name")


# ---------- auth ----------

def admin_token():
    return hmac.new(ADMIN_KEY.encode(), b"deltabin-admin", hashlib.sha256).hexdigest()


def is_admin():
    cookie = request.cookies.get("session")
    return bool(ADMIN_KEY and cookie and hmac.compare_digest(cookie, admin_token()))


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("auth"))
        return view(*args, **kwargs)
    return wrapper


def message(code, text):
    return render_template("message.html", code=code, message=text), code


# ---------- filters / headers ----------

@app.template_filter("size")
def fmt_size(n):
    if n < 1024:
        return f"{n} b"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} kb"
    return f"{n / 1024 / 1024:.1f} mb"


@app.after_request
def headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    return resp


# ---------- public ----------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/create", methods=["POST"])
def create():
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("ct"), str) or not isinstance(data.get("iv"), str):
        return Response("bad request", status=400, mimetype="text/plain")
    name = new_name()
    body = json.dumps({"ct": data["ct"], "iv": data["iv"]})
    s3.put_object(Bucket=BUCKET, Key=name, Body=body, Metadata={"enc": "1"}, ContentType="application/json")
    return jsonify(id=name)


@app.route("/tos")
def tos():
    return render_template("tos.html")


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.route("/<name>")
def paste(name):
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=name)
        payload = json.loads(obj["Body"].read())
        if not isinstance(payload, dict) or "ct" not in payload:
            raise ValueError
    except s3.exceptions.NoSuchKey:
        return message(404, "paste not found")
    except ValueError:
        return message(500, "this paste is unreadable")
    return render_template("view.html", id=name, payload=payload)


# ---------- admin ----------

@app.route("/auth", methods=["GET", "POST"])
def auth():
    if is_admin():
        return redirect(url_for("panel"))
    if request.method == "GET":
        return render_template("auth.html")
    entered = request.form.get("key", "")
    if not ADMIN_KEY or not hmac.compare_digest(entered.encode(), ADMIN_KEY.encode()):
        return render_template("auth.html", error="incorrect key"), 401
    resp = make_response(redirect(url_for("panel")))
    resp.set_cookie("session", admin_token(), max_age=timedelta(hours=72),
                    httponly=True, secure=request.is_secure, samesite="Strict")
    return resp


@app.route("/logout", methods=["POST"])
def logout():
    resp = make_response(redirect("/"))
    resp.delete_cookie("session")
    return resp


@app.route("/panel")
@admin_required
def panel():
    pastes = list_pastes()
    return render_template("panel.html", pastes=pastes, total=sum(p["size"] for p in pastes),
                           flash=request.args.get("msg"))


@app.route("/manage")
@admin_required
def manage():
    name = request.args.get("id", "")
    try:
        head = s3.head_object(Bucket=BUCKET, Key=name)
    except s3.exceptions.ClientError:
        return message(404, "paste not found")
    return render_template("manage.html", id=name, size=head["ContentLength"],
                           modified=head["LastModified"], error=request.args.get("err"))


@app.route("/delete", methods=["POST"])
@admin_required
def delete():
    names = [n for n in request.form.getlist("name") if n]
    purge(names)
    n = len(names)
    return redirect(url_for("panel", msg=f"deleted {n} paste{'' if n == 1 else 's'}"))


@app.route("/rename", methods=["POST"])
@admin_required
def rename():
    old = request.form.get("old", "")
    new = request.form.get("new", "").strip() or new_name()
    if not exists(old):
        return message(404, "paste not found")
    if not NAME_RE.match(new) or new in RESERVED:
        return redirect(url_for("manage", id=old, err="invalid name"))
    if new != old and exists(new):
        return redirect(url_for("manage", id=old, err="name taken"))
    if new != old:
        s3.copy_object(Bucket=BUCKET, CopySource={"Bucket": BUCKET, "Key": old}, Key=new)
        purge([old])
    return redirect(url_for("panel", msg=f"renamed {old} → {new}"))


# ---------- errors ----------

@app.errorhandler(413)
def too_large(_):
    if request.path == "/create":
        return Response("too large", status=413, mimetype="text/plain")
    return message(413, "too large. 256 kb max.")


@app.errorhandler(404)
def not_found(_):
    return message(404, "page not found")


@app.errorhandler(500)
def server_error(_):
    return message(500, "something went wrong")


if __name__ == "__main__":
    app.run(debug=True, port=8080)
