from flask import Flask, request, render_template, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
import os

app = Flask(__name__)

# ── Configuration ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Informations de la boutique ────────────────────────────
BOUTIQUE_INFO = """
Tu es l'assistant WhatsApp de la boutique NZELA SHOP.

Informations de la boutique :
- Nom : Nzela Shop
- Adresse : À compléter
- Horaires : Lundi-Samedi 8h-20h, Dimanche 9h-14h
- Téléphone : À compléter
- Livraison : Disponible dans un rayon de 5 km

Produits disponibles :
- Riz 25kg : 15 000 FCFA
- Riz 10kg : 6 500 FCFA
- Huile 5L : 4 500 FCFA
- Huile 1L : 1 200 FCFA
- Sucre 5kg : 3 500 FCFA
- Farine 5kg : 3 000 FCFA
- Savon x6 : 2 500 FCFA

Règles de réponse :
- Réponds toujours en français
- Sois courtois et professionnel
- Si le produit n'est pas listé, dis que tu vas vérifier
- Pour les commandes, demande : nom, quantité, adresse de livraison
- Réponds de façon courte et claire (WhatsApp)
- Si la question dépasse tes informations, propose d'appeler la boutique
"""

# ── Mémoire des conversations ──────────────────────────────
conversations = {}

# ── 🆕 PAGE WEB (UTILISE templates/index.html) ─────────────
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# ── 🆕 CHAT WEB ───────────────────────────────────────────
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_msg = data.get("message", "")

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            system=BOUTIQUE_INFO,
            messages=[{"role": "user", "content": user_msg}]
        )
        bot_reply = response.content[0].text

    except Exception as e:
        print("ERREUR WEB:", e)
        bot_reply = "Désolé, une erreur s'est produite."

    return jsonify({"reply": bot_reply})

# ── Route principale WhatsApp ──────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.form.get("Body", "").strip()
    sender = request.form.get("From", "")

    print("MESSAGE REÇU:", incoming_msg)

    if sender not in conversations:
        conversations[sender] = []

    conversations[sender].append({
        "role": "user",
        "content": incoming_msg
    })

    if len(conversations[sender]) > 10:
        conversations[sender] = conversations[sender][-10:]

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307"",
            max_tokens=300,
            system=BOUTIQUE_INFO,
            messages=conversations[sender]
        )
        bot_reply = response.content[0].text

    except Exception as e:
        print("ERREUR CLAUDE:", e)
        bot_reply = "Désolé, une erreur s'est produite. Veuillez réessayer."

    conversations[sender].append({
        "role": "assistant",
        "content": bot_reply
    })

    resp = MessagingResponse()
    resp.message(bot_reply)
    return str(resp)

# ── Lancement ──────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
