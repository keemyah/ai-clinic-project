# mistral_search.py (version robuste, debug-friendly)
import os
import time
import logging
import re
import traceback
from dotenv import load_dotenv
env_path = "/Users/hirama/PycharmProjects/TESTZONE/src/.env"
load_dotenv(env_path)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MistralSearch:
    def __init__(self, api_connector, api_key=None, model_chat="mistral-large-latest",
                 use_embeddings=False, allow_offline_debug=True):
        """
        :param api_connector: instance de LegiFranceAPI
        :param api_key: clé Mistral (optionnelle si présente en MISTRAL_API_KEY)
        :param allow_offline_debug: si True, la classe reste utilisable en mode "offline" (stub responses)
        """
        self.api = api_connector
        self.model_chat = model_chat
        self.use_embeddings = use_embeddings
        self.max_preview_chars = 700
        self.max_results = 10
        self.chat_timeout = 60

        self.client = None
        self.available = False
        self._init_error = None
        self._offline_debug = False

        # résolution clé
        if api_key is None:
            api_key = os.getenv("MISTRAL_API_KEY")

        if not api_key:
            # Ne raise pas : on passe en mode offline si autorisé, sinon raise pour forcer config.
            msg = "Clé API Mistral non trouvée. Configurez MISTRAL_API_KEY."
            logger.warning(msg)
            if allow_offline_debug:
                logger.info("Activation du mode offline/debug (pas de connexion au modèle).")
                self._offline_debug = True
                return
            else:
                raise ValueError(msg)

        # tentative d'init du client (entourer d'un try pour logger précisément)
        try:
            from mistralai import Mistral
            # Certaines versions du SDK peuvent exiger un autre constructeur ; capture d'erreurs explicite
            try:
                self.client = Mistral(api_key=api_key)
            except TypeError:
                # fallback to positional
                self.client = Mistral(api_key)
            self.available = True
            logger.info("✅ Client Mistral initialisé avec succès")
        except Exception as e:
            # stocke l'erreur pour debug et active offline si permis
            self._init_error = e
            logger.error("Impossible d'initialiser le client Mistral : %s", e)
            logger.debug(traceback.format_exc())
            if allow_offline_debug:
                logger.info("Mode offline/debug activé (mistral indisponible). Vous pouvez toujours tester le pipeline sans IA.")
                self._offline_debug = True
            else:
                raise RuntimeError(f"Impossible d'initialiser le client Mistral: {e}")

    # -----------------------------
    # RAG-safe analyse
    # -----------------------------
    def generate_analysis(self, question, articles, max_tokens=1200):
        if not articles:
            return "❌ Aucun article fourni pour l'analyse."

        # --- chunking et snippets (identique à ta version)
        snippets = []
        for i, art in enumerate(articles[:6]):
            art_id = str(art.get("id") or art.get("article_id") or f"unk_{i}")
            title = art.get("title") or art.get("titre") or "(sans titre)"
            content = art.get("content") or art.get("contenu") or ""
            content = getattr(self.api, "_nettoyer_texte")(content) if hasattr(self.api, "_nettoyer_texte") else content
            sents = re.split(r'(?<=[\.\?\!])\s+', content)
            chunks = []
            cur = ""
            for s in sents:
                if len(cur) + len(s) + 1 <= 1500:
                    cur = (cur + " " + s).strip()
                else:
                    if cur:
                        chunks.append(cur)
                    cur = s
            if cur:
                chunks.append(cur)
            chosen = chunks[:2] if chunks else [content[:1500]]
            for idx, c in enumerate(chosen):
                sid = f"{art_id}__{idx}"
                snippets.append({"id": sid, "art_id": art_id, "title": title, "text": c})

        snippet_block = "\n\n".join([f"[[source:{s['id']}]] {s['title']}\n{s['text']}" for s in snippets])
        system_msg = (
            "Tu es un assistant juridique. Réponds UNIQUEMENT à partir des EXTRAITS fournis. "
            "Ne jamais inventer d'article ou référence. Si l'information ne figure pas, réponds EXACTEMENT: INFORMATION_INSUFFISANTE."
        )

        prompt = f"""
QUESTION: {question}

EXTRAITS:
{snippet_block}

INSTRUCTIONS:
- Réponds strictement en JSON avec les clés: qualification, textes_applicables (liste d'IDs [[source:...]]), argumentation, risques, synthese.
- Pour chaque point d'argumentation, cite la source en utilisant [[source:ID]].
- Si la réponse ne peut pas être déduite à partir des EXTRAITS fournis, renvoie exactement "INFORMATION_INSUFFISANTE"
"""

        # Si on est en mode offline/debug : retourne un stub JSON pour test.
        if self._offline_debug:
            logger.info("MODE DEBUG: génération simulée (offline).")
            # Stub simple : indique qu'il s'agit d'un résultat simulé
            return {
                "qualification": "SIMULATION - Aucun raisonnement réel (mode debug).",
                "textes_applicables": [s["id"] for s in snippets[:2]],
                "argumentation": ["SIMULATION - Aucune preuve extraite."],
                "risques": ["SIMULATION - Aucun risque réel analysé."],
                "synthese": "SIMULATION"
            }

        # appel réel
        resp_text = self._call_chat(prompt, max_tokens=max_tokens, temperature=0.0, system_message=system_msg)
        allowed_ids = {s["id"] for s in snippets}
        if not self._verify_sources_in_response(resp_text, allowed_ids):
            logger.warning("Réponse citant des sources non fournies. Rejet.")
            return "INFORMATION_INSUFFISANTE"

        # parse JSON
        try:
            import json
            return json.loads(resp_text)
        except Exception:
            logger.warning("Réponse non-JSON reçue du modèle (on renvoie le texte brut).")
            return resp_text

    def _verify_sources_in_response(self, response_text, allowed_ids):
        found = re.findall(r"\[\[source:([^\]\]]+)\]\]", response_text)
        unknown = [fid for fid in found if fid not in allowed_ids]
        if unknown:
            logger.debug("Sources inconnues détectées: %s", unknown)
        return len(unknown) == 0

    # -----------------------------
    # Chat wrapper robuste (tolérances sur signatures)
    # -----------------------------
    def _call_chat(self, prompt, max_tokens=300, temperature=0.0, retries=2, system_message=None):
        """
        Appelle le client Mistral en essayant plusieurs signatures possibles
        et gère 429/backoff. Retourne le texte produit par le modèle.
        """
        last_exc = None
        for attempt in range(1, retries + 2):
            try:
                messages = [{"role": "user", "content": prompt}]
                if system_message:
                    messages = [{"role": "system", "content": system_message}] + messages

                # différentes signatures possibles du SDK
                if self.client is None:
                    raise RuntimeError("Client Mistral non initialisé malgré available=True")

                # signature type: client.chat.complete(...)
                if hasattr(self.client, "chat") and hasattr(self.client.chat, "complete"):
                    resp = self.client.chat.complete(
                        model=self.model_chat,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                    return self._extract_text_from_response(resp)

                # signature type: client.chat.completions.create(...)
                if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                    resp = self.client.chat.completions.create(
                        model=self.model_chat,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                    return self._extract_text_from_response(resp)

                # signature type: client.completions.create(...)
                if hasattr(self.client, "completions") and hasattr(self.client.completions, "create"):
                    resp = self.client.completions.create(
                        model=self.model_chat,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                    return self._extract_text_from_response(resp)

                # signature type: client.chat.generate(...)
                if hasattr(self.client, "chat") and hasattr(self.client.chat, "generate"):
                    # certains SDK retournent objets complexes; on délègue l'extraction
                    resp = self.client.chat.generate(model=self.model_chat, messages=messages)
                    return self._extract_text_from_response(resp)

                raise RuntimeError("Aucune signature connue trouvée sur le client Mistral installé.")
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                logger.debug("Erreur appel chat (attempt %d): %s", attempt, msg)
                if "429" in msg or "too many requests" in msg or "capacity" in msg:
                    wait = 5 * attempt
                    logger.warning("429 reçu (ou quota). Attente %ds puis retry (attempt %d).", wait, attempt)
                    time.sleep(wait)
                    continue
                # backoff court pour autres erreurs
                time.sleep(1 * attempt)
                continue
        # sortie en erreur après retries
        logger.error("Échec appel chat après %d tentatives: %s", retries + 1, last_exc)
        raise last_exc or RuntimeError("Échec appel chat Mistral")

    def _extract_text_from_response(self, resp):
        """
        Tentatives de parsing des différents formats de réponse SDK.
        """
        try:
            # dict-like (OpenAI style)
            if isinstance(resp, dict):
                if "choices" in resp and isinstance(resp["choices"], list) and resp["choices"]:
                    c = resp["choices"][0]
                    if isinstance(c, dict):
                        if "message" in c and isinstance(c["message"], dict) and "content" in c["message"]:
                            return c["message"]["content"]
                        if "text" in c:
                            return c["text"]
                if "output" in resp:
                    return resp["output"]
                if "result" in resp:
                    return resp["result"]

            # object-like SDKs
            if hasattr(resp, "choices") and len(resp.choices) > 0:
                ch = resp.choices[0]
                if hasattr(ch, "message") and hasattr(ch.message, "content"):
                    return ch.message.content
                if hasattr(ch, "text"):
                    return ch.text

            # fallback
            return str(resp)
        except Exception:
            logger.debug("Erreur extract_text_from_response: returning str(resp)")
            return str(resp)

    # -----------------------------
    # Recherche intelligente (fallback non-LLM pour keywords)
    # -----------------------------
    def intelligent_search(self, question, code_nom=None, max_results=10):
        # fallback: extraction simple de keywords (évite appel LLM)
        keywords = " ".join([w for w in question.lower().split() if len(w) > 2])
        search_results = self.api.rechercher_articles(keywords, code_nom, page_size=max_results)
        if not search_results or not search_results.get("results"):
            return {"combined_results": [], "query_analysis": keywords, "original_question": question}
        ranked_results = []
        for res in search_results["results"][:max_results]:
            info = self.api._normaliser_article(res)
            ranked_results.append({
                "id": info.get("id"),
                "title": info.get("titre"),
                "content": info.get("contenu"),
                "code_name": info.get("code"),
                "legal_status": info.get("etat"),
                "source": "api_legifrance",
                "relevance_rank": len(ranked_results) + 1
            })
        return {"combined_results": ranked_results, "query_analysis": keywords, "original_question": question}
