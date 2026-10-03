"""LAN web interface for testing Kana Reader from a phone browser."""
import argparse
import hmac
import io
import os
import secrets
import sys
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from predict import predict_line
from translation import translate_japanese

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.secret_key = secrets.token_bytes(32)
ACCESS_CODE = ""


@app.before_request
def require_public_access_code():
    if not ACCESS_CODE or request.endpoint in {"login", "health", "static"}:
        return None
    supplied = request.headers.get("X-Sakura-Access-Code", "")
    if hmac.compare_digest(supplied, ACCESS_CODE):
        return None
    if session.get("sakura_authorized"):
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Enter the access code shown on the PC."), 401
    return redirect(url_for("login", next=request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    message = ""
    if request.method == "POST":
        submitted = request.form.get("code", "")
        if ACCESS_CODE and hmac.compare_digest(submitted, ACCESS_CODE):
            session["sakura_authorized"] = True
            next_path = request.args.get("next", "/")
            if not next_path.startswith("/") or next_path.startswith("//"):
                next_path = "/"
            return redirect(next_path)
        message = "That access code did not match. Try again."
    return render_template("login.html", message=message)


@app.get("/health")
def health():
    return jsonify(ok=True, access_code_required=bool(ACCESS_CODE))


@app.get("/")
def index():
    return render_template("mobile.html")


@app.post("/api/recognize")
def recognize():
    photo = request.files.get("image")
    if not photo or not photo.filename:
        return jsonify(error="Choose or take a photo first."), 400
    try:
        with Image.open(io.BytesIO(photo.read())) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        readings = predict_line(image)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return jsonify(error=f"Could not read that image: {exc}"), 400
    return jsonify(
        kana="".join(item["kana"] for item in readings),
        readings=[{
            "kana": item["kana"],
            "pronunciation": item["label"].lower(),
            "confidence": round(item["confidence"], 4),
            "alternatives": [
                {"kana": alt[1], "pronunciation": alt[0].lower(), "confidence": round(alt[2], 4)}
                for alt in item["alternatives"]
            ],
        } for item in readings],
    )


@app.post("/api/translate")
def translate():
    payload = request.get_json(silent=True) or {}
    text = " ".join(str(payload.get("text", "")).split())
    if not text:
        return jsonify(error="Enter Japanese text to translate."), 400
    try:
        return jsonify(translation=translate_japanese(text))
    except (FileNotFoundError, OSError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 503


def main():
    parser = argparse.ArgumentParser(description="Open Kana Reader on an Android phone over your local Wi-Fi.")
    parser.add_argument("--host", default="0.0.0.0", help="Network interface to bind (default: all local interfaces)")
    parser.add_argument("--port", type=int, default=5055)
    parser.add_argument("--access-code", default=os.environ.get("SAKURA_ACCESS_CODE", ""))
    args = parser.parse_args()
    global ACCESS_CODE
    ACCESS_CODE = args.access_code.strip()
    print("Kana Reader mobile page: http://<this-PC's-LAN-IP>:%d" % args.port, flush=True)
    print("Keep this window open while testing from your phone.", flush=True)
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
