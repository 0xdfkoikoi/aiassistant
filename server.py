import os, json, time, hashlib, ipaddress
from collections import defaultdict
from flask import Flask, request, jsonify, make_response

# ---- config ----
PORT = 8000
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}  # requests come via Apache proxy
RATE_LIMIT = (30, 300)  # 30 requests / 300s per IP
SESSION_COOKIE = "sid"
PRODUCTS_PATH = os.path.join(os.path.dirname(__file__), "products.json")

# load products read-only
with open(PRODUCTS_PATH, "r", encoding="utf-8") as f:
    PRODUCTS = json.load(f)

app = Flask(__name__)
_hits = defaultdict(list)

def rate_limited(ip, limit=RATE_LIMIT[0], window=RATE_LIMIT[1]):
    now = time.time()
    bucket = _hits[ip]
    # drop old
    i = 0
    for t in bucket:
        if now - t < window:
            break
        i += 1
    if i:
        del bucket[:i]
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False

def ensure_session(resp):
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        raw = f"{time.time()}|{request.remote_addr}|{os.urandom(8).hex()}"
        sid = hashlib.sha256(raw.encode()).hexdigest()[:32]
        resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="Lax")
    return resp

def simple_search(query, k=5):
    """Very small relevance: count word matches in name/tags."""
    q = [w for w in query.lower().split() if len(w) >= 2]
    scored = []
    for p in PRODUCTS:
        hay = (p["name"] + " " + p.get("tags","")).lower()
        score = sum(1 for w in q if w in hay)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    return [p for _, p in scored[:k]]

def allowed_origin():
    # If you later serve frontend from same origin via Apache, this will be same-origin.
    # We still protect: only accept calls that came from the proxy (Host header local).
    host = request.host.split(":")[0]
    return host in ALLOWED_HOSTS

def call_openai(system_prompt, user_msg, context):
    """
    Calls OpenAI using your server-side key.
    If OPENAI_API_KEY is missing, return a demo reply so you can test the pipeline.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # demo fallback
        names = ", ".join(p["name"] for p in context) or "no matching items"
        return f"(demo) You asked: “{user_msg}”. Relevant items: {names}."

    try:
        import openai  # pip install openai
        openai.api_key = api_key
        messages = [
            {"role":"system","content": system_prompt},
            {"role":"user","content": (
                "User message:\n" + user_msg + "\n\n"
                "Relevant products (JSON):\n" + json.dumps(context, ensure_ascii=False)
            )}
        ]
        # choose a lightweight, cost-friendly model
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4
        )
        return resp.choices[0].message["content"].strip()
    except Exception as e:
        return f"Sorry, I had an issue contacting the AI: {e}"

@app.post("/api/chat")
def chat():
    ip = request.remote_addr or "0.0.0.0"
    # basic sanity: must be LAN-ish (optional hardening)
    try:
        if ipaddress.ip_address(ip).is_global:
            pass  # allow if behind NAT; Apache terminates anyway
    except:  # ignore parse issues
        pass

    if rate_limited(ip):
        return jsonify({"error": "Too many requests, please wait a bit."}), 429

    if not allowed_origin():
        return jsonify({"error":"Forbidden origin"}), 403

    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "")[:1000].strip()
    if not user_msg:
        return jsonify({"error":"Empty message"}), 400

    # retrieve relevant rows (read-only)
    context = simple_search(user_msg, k=6)

    system_prompt = (
        "You are 'Toko Gangan Assistant' (also serves Wisdom Cafe and Bendalton Roomshop). "
        "Only answer about products, prices, stock, promos, opening hours, and simple friendly small talk. "
        "Use ONLY the provided product context for items; if something is not present, say you don’t have it. "
        "For orders, confirm item names, quantity, and total price succinctly. Be polite and concise."
    )

    reply = call_openai(system_prompt, user_msg, context)
    resp = make_response(jsonify({"reply": reply}))
    return ensure_session(resp)

@app.get("/api/health")
def health():
    return {"ok": True, "products": len(PRODUCTS)}
    
if __name__ == "__main__":
    # For development; in production, run behind Apache via proxy
    app.run(host="127.0.0.1", port=PORT, debug=False)
