import os
import re
import json
import uuid
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import torch
from flask import Flask, request, jsonify, render_template
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
)


# ============================================================
# CONFIGURATION GENERALE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

MODEL_PATH = Path(
    os.environ.get(
        "JARVIS_MODEL_PATH",
        BASE_DIR / "models" / "jarvis_gpt2_fr_v1"
    )
)

HOST = os.environ.get("JARVIS_HOST", "127.0.0.1")
PORT = int(os.environ.get("JARVIS_PORT", "5000"))

MAX_HISTORY_MESSAGES = 12
MAX_INPUT_CHARACTERS = 4000
MAX_NEW_TOKENS = 180

APP_NAME = "JARVIS AI"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(APP_NAME)


# ============================================================
# APPLICATION FLASK
# ============================================================

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates")
)

app.config["JSON_AS_ASCII"] = False


# ============================================================
# MEMOIRE TEMPORAIRE DES CONVERSATIONS
# ============================================================

conversation_memory: Dict[str, List[Dict[str, str]]] = {}
memory_lock = threading.Lock()


def create_conversation() -> str:
    """
    Crée un identifiant unique de conversation.
    """
    conversation_id = str(uuid.uuid4())

    with memory_lock:
        conversation_memory[conversation_id] = []

    return conversation_id


def get_conversation(conversation_id: str) -> List[Dict[str, str]]:
    """
    Récupère une conversation existante.
    """
    with memory_lock:
        return list(conversation_memory.get(conversation_id, []))


def save_message(
    conversation_id: str,
    role: str,
    content: str
) -> None:
    """
    Enregistre un message dans la mémoire temporaire.
    """
    with memory_lock:
        if conversation_id not in conversation_memory:
            conversation_memory[conversation_id] = []

        conversation_memory[conversation_id].append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        conversation_memory[conversation_id] = (
            conversation_memory[conversation_id][-MAX_HISTORY_MESSAGES:]
        )


def clear_conversation(conversation_id: str) -> None:
    """
    Supprime l'historique d'une conversation.
    """
    with memory_lock:
        conversation_memory.pop(conversation_id, None)


# ============================================================
# CHARGEMENT DU MODELE GPT-2
# ============================================================

class GPT2Service:
    """
    Service responsable du chargement et de la génération GPT-2.
    """

    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.tokenizer = None
        self.model = None

        self.model_lock = threading.Lock()

        self.load_model()

    def load_model(self) -> None:
        """
        Charge le tokenizer et le modèle.
        """
        logger.info("Chargement du modèle GPT-2...")
        logger.info("Chemin modèle : %s", self.model_path)
        logger.info("Device : %s", self.device)

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Modèle introuvable : {self.model_path}"
            )

        self.tokenizer = AutoTokenizer.from_pretrained(
            str(self.model_path),
            local_files_only=True
        )

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            str(self.model_path),
            local_files_only=True
        )

        self.model.to(self.device)
        self.model.eval()

        logger.info(
            "GPT-2 chargé avec succès. Paramètres : %s",
            sum(parameter.numel() for parameter in self.model.parameters())
        )

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = MAX_NEW_TOKENS
    ) -> str:
        """
        Génère une réponse avec GPT-2.
        """

        if not prompt.strip():
            return ""

        encoded = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=900
        )

        input_ids = encoded["input_ids"].to(self.device)
        attention_mask = encoded["attention_mask"].to(self.device)

        with self.model_lock:
            with torch.no_grad():
                generated_ids = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    temperature=0.75,
                    top_p=0.92,
                    top_k=50,
                    repetition_penalty=1.15,
                    no_repeat_ngram_size=3,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    use_cache=True
                )

        generated_text = self.tokenizer.decode(
            generated_ids[0],
            skip_special_tokens=True
        )

        if generated_text.startswith(prompt):
            generated_text = generated_text[len(prompt):]

        return generated_text.strip()


# ============================================================
# MOTEUR JARVIS LOCAL
# ============================================================

class JarvisEngine:
    """
    Moteur de coordination JARVIS.

    GPT-2 génère du langage.
    Ce moteur réalise les vérifications locales simples.
    Les réponses GPT-2 ne sont pas automatiquement enregistrées
    comme connaissances fiables.
    """

    def __init__(self, gpt2_service: GPT2Service):
        self.gpt2 = gpt2_service

    # --------------------------------------------------------
    # DETECTION DES CALCULS
    # --------------------------------------------------------

    def looks_like_math(self, text: str) -> bool:
        """
        Détecte les demandes mathématiques simples.
        """
        lowered = text.lower()

        math_words = [
            "calcule",
            "calculer",
            "résous",
            "resous",
            "équation",
            "equation",
            "combien font",
            "combien fait",
            "math",
            "solve"
        ]

        if any(word in lowered for word in math_words):
            return True

        if re.search(r"\d+\s*[\+\-\*\/x×]\s*\d+", lowered):
            return True

        return False

    def solve_simple_math(self, text: str) -> Optional[str]:
        """
        Résout uniquement des opérations arithmétiques simples.

        Sécurité :
        - aucun eval() ;
        - aucune exécution de code utilisateur ;
        - seulement nombres et opérateurs autorisés.
        """

        cleaned = text.lower()

        cleaned = cleaned.replace("×", "*")
        cleaned = cleaned.replace("x", "*")
        cleaned = cleaned.replace("÷", "/")
        cleaned = cleaned.replace(",", ".")

        match = re.search(
            r"(-?\d+(?:\.\d+)?)\s*"
            r"([\+\-\*\/])\s*"
            r"(-?\d+(?:\.\d+)?)",
            cleaned
        )

        if not match:
            return None

        first = float(match.group(1))
        operator = match.group(2)
        second = float(match.group(3))

        try:
            if operator == "+":
                result = first + second

            elif operator == "-":
                result = first - second

            elif operator == "*":
                result = first * second

            elif operator == "/":
                if second == 0:
                    return "Je ne peux pas diviser par zéro."
                result = first / second

            else:
                return None

        except Exception as error:
            logger.exception("Erreur calcul : %s", error)
            return None

        if result.is_integer():
            result_text = str(int(result))
        else:
            result_text = str(round(result, 10))

        return (
            "Résultat vérifié par le moteur de calcul local :\n"
            f"{first:g} {operator} {second:g} = {result_text}"
        )

    # --------------------------------------------------------
    # ANALYSE DE LA DEMANDE
    # --------------------------------------------------------

    def analyze(self, user_message: str) -> Dict[str, Any]:
        """
        Analyse simple de la demande.
        """
        return {
            "is_math": self.looks_like_math(user_message),
            "length": len(user_message),
            "language": "fr",
            "needs_gpt2": True
        }

    # --------------------------------------------------------
    # CONSTRUCTION DU PROMPT
    # --------------------------------------------------------

    def build_prompt(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        analysis: Dict[str, Any]
    ) -> str:
        """
        Construit le contexte transmis à GPT-2.
        """

        prompt_parts = [
            "Tu es JARVIS AI, un assistant intelligent francophone.",
            "Tu aides l'utilisateur avec des réponses claires, utiles et prudentes.",
            "Tu ne dois pas inventer une information présentée comme certaine.",
            "Si tu n'es pas sûr, indique-le clairement.",
            "Ne prétends pas avoir exécuté une action si tu ne l'as pas exécutée.",
            ""
        ]

        if analysis.get("is_math"):
            prompt_parts.extend(
                [
                    "La demande semble mathématique.",
                    "Explique les étapes simplement.",
                    ""
                ]
            )

        for message in history[-MAX_HISTORY_MESSAGES:]:
            role = message.get("role", "user")
            content = message.get("content", "").strip()

            if not content:
                continue

            if role == "user":
                prompt_parts.append(f"Utilisateur : {content}")

            elif role == "assistant":
                prompt_parts.append(f"JARVIS : {content}")

        prompt_parts.append(f"Utilisateur : {user_message}")
        prompt_parts.append("JARVIS :")

        return "\n".join(prompt_parts)

    # --------------------------------------------------------
    # NETTOYAGE DE LA REPONSE
    # --------------------------------------------------------

    def clean_response(
        self,
        response: str,
        user_message: str
    ) -> str:
        """
        Nettoie les répétitions fréquentes de GPT-2.
        """

        if not response:
            return ""

        cleaned = response.strip()

        stop_markers = [
            "\nUtilisateur :",
            "\nJARVIS :",
            "\nHuman :",
            "\nAssistant :"
        ]

        for marker in stop_markers:
            if marker in cleaned:
                cleaned = cleaned.split(marker, 1)[0].strip()

        if cleaned.startswith("JARVIS :"):
            cleaned = cleaned[len("JARVIS :"):].strip()

        if not cleaned:
            return (
                "Je n'ai pas réussi à produire une réponse claire. "
                "Peux-tu reformuler ta demande ?"
            )

        return cleaned

    # --------------------------------------------------------
    # REPONSE PRINCIPALE
    # --------------------------------------------------------

    def answer(
        self,
        user_message: str,
        history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Produit une réponse JARVIS.
        """

        analysis = self.analyze(user_message)

        # Priorité au moteur local pour les calculs simples.
        if analysis["is_math"]:
            math_answer = self.solve_simple_math(user_message)

            if math_answer is not None:
                return {
                    "answer": math_answer,
                    "source": "jarvis_local_math",
                    "verified": True,
                    "analysis": analysis
                }

        prompt = self.build_prompt(
            user_message=user_message,
            history=history,
            analysis=analysis
        )

        try:
            generated = self.gpt2.generate(prompt)
            cleaned = self.clean_response(
                generated,
                user_message
            )

            return {
                "answer": cleaned,
                "source": "gpt2",
                "verified": False,
                "analysis": analysis
            }

        except RuntimeError as error:
            logger.exception("Erreur GPU/GPT-2 : %s", error)

            if "out of memory" in str(error).lower():
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                return {
                    "answer": (
                        "La mémoire GPU est insuffisante pour cette réponse. "
                        "Essaie une question plus courte."
                    ),
                    "source": "system",
                    "verified": False,
                    "analysis": analysis
                }

            return {
                "answer": (
                    "Une erreur technique est survenue pendant la génération."
                ),
                "source": "system",
                "verified": False,
                "analysis": analysis
            }

        except Exception as error:
            logger.exception("Erreur génération : %s", error)

            return {
                "answer": (
                    "J'ai rencontré une erreur technique. "
                    "Consulte la console du serveur."
                ),
                "source": "system",
                "verified": False,
                "analysis": analysis
            }


# ============================================================
# INITIALISATION DES SERVICES
# ============================================================

try:
    gpt2_service = GPT2Service(MODEL_PATH)
    jarvis = JarvisEngine(gpt2_service)

except Exception as startup_error:
    logger.exception(
        "Impossible de charger JARVIS au démarrage : %s",
        startup_error
    )

    gpt2_service = None
    jarvis = None


# ============================================================
# ROUTES WEB
# ============================================================

@app.route("/", methods=["GET"])
def home():
    """
    Affiche l'interface Web.
    """
    return render_template(
        "index.html",
        app_name=APP_NAME
    )


@app.route("/api/health", methods=["GET"])
def health():
    """
    Vérifie l'état du serveur.
    """
    return jsonify(
        {
            "application": APP_NAME,
            "status": "ok" if jarvis is not None else "error",
            "model_path": str(MODEL_PATH),
            "model_loaded": jarvis is not None,
            "device": (
                gpt2_service.device
                if gpt2_service is not None
                else None
            ),
            "cuda_available": torch.cuda.is_available()
        }
    )


@app.route("/api/conversation", methods=["POST"])
def new_conversation():
    """
    Crée une nouvelle conversation.
    """
    conversation_id = create_conversation()

    return jsonify(
        {
            "success": True,
            "conversation_id": conversation_id
        }
    )


@app.route("/api/conversation/<conversation_id>", methods=["DELETE"])
def delete_conversation(conversation_id: str):
    """
    Supprime une conversation.
    """
    clear_conversation(conversation_id)

    return jsonify(
        {
            "success": True,
            "conversation_id": conversation_id
        }
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Reçoit une question et retourne la réponse JARVIS.
    """

    if jarvis is None:
        return jsonify(
            {
                "success": False,
                "error": (
                    "JARVIS n'est pas disponible. "
                    "Le modèle GPT-2 n'a pas pu être chargé."
                )
            }
        ), 503

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            {
                "success": False,
                "error": "Requête JSON invalide."
            }
        ), 400

    user_message = str(
        data.get("message", "")
    ).strip()

    conversation_id = str(
        data.get("conversation_id", "")
    ).strip()

    if not conversation_id:
        conversation_id = create_conversation()

    if not user_message:
        return jsonify(
            {
                "success": False,
                "error": "Le message est vide."
            }
        ), 400

    if len(user_message) > MAX_INPUT_CHARACTERS:
        return jsonify(
            {
                "success": False,
                "error": (
                    f"Le message est trop long. "
                    f"Maximum : {MAX_INPUT_CHARACTERS} caractères."
                )
            }
        ), 400

    history = get_conversation(conversation_id)

    save_message(
        conversation_id=conversation_id,
        role="user",
        content=user_message
    )

    result = jarvis.answer(
        user_message=user_message,
        history=history
    )

    answer = result.get(
        "answer",
        "Je n'ai pas de réponse."
    )

    save_message(
        conversation_id=conversation_id,
        role="assistant",
        content=answer
    )

    return jsonify(
        {
            "success": True,
            "conversation_id": conversation_id,
            "answer": answer,
            "source": result.get("source"),
            "verified": result.get("verified", False),
            "analysis": result.get("analysis", {})
        }
    )


@app.route("/api/history/<conversation_id>", methods=["GET"])
def history(conversation_id: str):
    """
    Retourne l'historique d'une conversation.
    """
    return jsonify(
        {
            "success": True,
            "conversation_id": conversation_id,
            "messages": get_conversation(conversation_id)
        }
    )


# ============================================================
# DEMARRAGE
# ============================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("%s démarre", APP_NAME)
    logger.info("Adresse locale : http://%s:%s", HOST, PORT)
    logger.info("Modèle : %s", MODEL_PATH)
    logger.info("GPU disponible : %s", torch.cuda.is_available())
    logger.info("=" * 60)

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        threaded=True
    )
