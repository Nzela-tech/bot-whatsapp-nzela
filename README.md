# 🤖 Bot WhatsApp Nzela Shop

Bot WhatsApp intelligent pour commerce/boutique.
Stack : Python + Flask + Twilio + Claude AI + Render

---

## 📁 Structure du projet

bot-whatsapp-nzela/
├── bot_whatsapp.py     ← Le code principal
├── requirements.txt    ← Les dépendances
└── README.md           ← Ce fichier

---

## 🚀 Déploiement étape par étape

### Étape 1 — GitHub
1. Crée un dépôt "bot-whatsapp-nzela" sur github.com/nzela-tech
2. Upload les 3 fichiers dedans

### Étape 2 — Render
1. Va sur https://render.com
2. Crée un compte gratuit
3. "New Web Service" → connecte ton GitHub
4. Sélectionne "bot-whatsapp-nzela"
5. Configure :
   - Build Command : pip install -r requirements.txt
   - Start Command : gunicorn bot_whatsapp:app
6. Ajoute la variable :
   - Clé : ANTHROPIC_API_KEY
   - Valeur : ta clé API Anthropic
7. Déploie → tu obtiens une URL

### Étape 3 — Twilio
1. Va sur https://twilio.com
2. Crée un compte gratuit
3. Active le Sandbox WhatsApp
4. Dans Sandbox Settings → When a message comes in :
   https://ton-app.onrender.com/webhook
5. Méthode : POST
6. Sauvegarde

### Étape 4 — Test
1. Envoie le code sandbox Twilio depuis WhatsApp
2. Envoie "Bonjour" → le bot répond

---

## 💰 Coût total : 0 FCFA

---

## 📞 GitHub : nzela-tech
```

---

**Sur GitHub :**
```
Add file → Create new file
Nom : README.md
Colle le contenu
Commit changes
