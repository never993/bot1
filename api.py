from flask import Flask, request, jsonify
from db import validate_license, get_license
import os

app = Flask(__name__)

# Chave secreta para o painel se autenticar com a API
API_SECRET = os.environ.get("API_SECRET", "TROQUE_ESSA_CHAVE_SECRETA")

@app.route("/validate", methods=["POST"])
def validate():
    data = request.get_json(silent=True) or {}
    secret = data.get("secret", "")
    key    = data.get("key", "").strip().upper()

    if secret != API_SECRET:
        return jsonify({"valid": False, "reason": "Acesso negado."}), 403

    if not key:
        return jsonify({"valid": False, "reason": "Chave vazia."}), 400

    result = validate_license(key)
    return jsonify(result)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
