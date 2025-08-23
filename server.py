from flask import Flask, request, jsonify
import openai
import os
import json
from dotenv import load_dotenv

# Load API key
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Load products database
with open("products.json", "r") as f:
    products = json.load(f)

app = Flask(__name__)

def find_product_info(user_message):
    """Search for a product by name or tags in products.json"""
    user_message_lower = user_message.lower()
    for p in products:
        if p["name"].lower() in user_message_lower or any(tag in user_message_lower for tag in p["tags"].split(",")):
            return f"{p['name']} is Rp{p['price']} and we have {p['stock']} in stock."
    return None

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # First try to answer from local product database
    product_answer = find_product_info(user_message)
    if product_answer:
        return jsonify({"reply": product_answer})

    # Otherwise, fallback to ChatGPT
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # works with openai==0.28.1
            messages=[
                {"role": "system", "content": "You are a helpful AI cashier for a local shop."},
                {"role": "user", "content": user_message}
            ]
        )
        reply = response["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
