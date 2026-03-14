# bot_whatsapp.py
# Bot WhatsApp pour Commerce / Boutique
# Stack : Python + Flask + Twilio + Claude API
# Hébergement : Render + GitHub (nzela-tech)

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
import os

app = Flask(__name__)

# ── Configuration ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Informations de la boutique (à personnaliser) ──────────
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

# ── Route principale WhatsApp ──────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    # Récupérer le message entrant
    incoming_msg = request.form.get("Body", "").strip()
    sender = request.form.get("From", "")

    # Initialiser la conversation si nouvelle
    if sender not in conversations:
        conversations[sender] = []

    # Ajouter le message de l'utilisateur
    conversations[sender].append({
        "role": "user",
        "content": incoming_msg
    })

    # Garder seulement les 10 derniers messages (mémoire courte)
    if len(conversations[sender]) > 10:
        conversations[sender] = conversations[sender][-10:]

    # Appel à Claude
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=BOUTIQUE_INFO,
            messages=conversations[sender]
        )
        bot_reply = response.content[0].text

    except Exception as e:
        bot_reply = "Désolé, une erreur s'est produite. Veuillez réessayer ou appeler directement la boutique."

    # Ajouter la réponse à la mémoire
    conversations[sender].append({
        "role": "assistant",
        "content": bot_reply
    })

    # Envoyer la réponse via Twilio
    resp = MessagingResponse()
    resp.message(bot_reply)
    return str(resp)

# ── Route de test (vérifier que le serveur tourne) ─────────
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot Nzela Shop actif et opérationnel.", 200

# ── Lancement ──────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
