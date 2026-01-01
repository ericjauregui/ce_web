from flask import Flask, render_template, request
from pathlib import Path
import json

app = Flask(__name__)

CATALOG_PATH = Path(__file__).parent / "catalog" / "products.json"
with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    PRODUCTS = json.load(f)

@app.route("/")
def index():
    q = (request.args.get("q") or "").strip().lower()
    items = PRODUCTS
    if q:
        items = [p for p in PRODUCTS if q in p["name"].lower() or q in p["code"].lower() or any(q in t.lower() for t in p.get("tags", []))]
    return render_template("index.html", products=items, q=q)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
