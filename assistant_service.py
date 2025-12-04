import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from api_connector import LegiFranceAPI
from data_processor import DataProcessor
from embedding_index import EmbeddingIndex
from mistral_search import MistralSearchV2

logger = logging.getLogger(__name__)


class AssistantService:
    _CODE_HINTS = [
        ("Code du travail", ["cdd", "contrat à durée déterminée", "contrat duree", "licenciement", "employeur", "salarie", "prud'h", "prudhom"]),
        ("Code civil", ["responsabilité civile", "responsabilite", "contrat civil", "obligation", "dommage", "préjudice", "prejudice"]),
        ("Code de commerce", ["commerce", "société", "entreprise", "actionnaire", "cession parts"]),
        ("Code pénal", ["infraction", "délit", "crime", "pénal", "sanction pénale"]),
        ("Code de la route", ["permis", "conduite", "vehicule", "route", "infraction routière"]),
    ]
    """Orchestre les appels LegiFrance + Mistral et sérialise les réponses."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        enable_embeddings: bool = True,
    ) -> None:
        self.client_id = client_id or os.getenv("CLIENT_ID")
        self.client_secret = client_secret or os.getenv("CLIENT_SECRET")

        if not self.client_id or not self.client_secret:
            raise RuntimeError("CLIENT_ID / CLIENT_SECRET manquants pour LegiFrance.")

        self.api = LegiFranceAPI(self.client_id, self.client_secret)
        self.data_processor = DataProcessor()
        
        # Note: EmbeddingIndex est conservé si vous voulez l'utiliser ailleurs, 
        # mais MistralSearchV2 gère sa propre logique de recherche désormais.
        self.embedding_index = None
        if enable_embeddings:
            self.embedding_index = self._prepare_embedding_index()

        # CORRECTION 1 : Appel correct au constructeur V2
        self.mistral_search = self._prepare_mistral_client()
        
        # CORRECTION 2 : Suppression de attach_embedding_index qui n'existe pas en V2
        # La V2 utilise une approche "Hypothesis-First" et non vectorielle directe pour l'instant.

    # ------------------------------------------------------------------ #
    # Initialisations
    # ------------------------------------------------------------------ #
    def _prepare_embedding_index(self) -> Optional[EmbeddingIndex]:
        try:
            idx = EmbeddingIndex()
        except Exception as exc:
            logger.warning("Chargement EmbeddingIndex impossible: %s", exc)
            return None

        try:
            idx.load()
            logger.info("Index d'embeddings chargé depuis le cache.")
            return idx
        except FileNotFoundError:
            logger.info("Index d'embeddings introuvable. Construction en cours...")
        except Exception as exc:
            logger.warning("Lecture index échouée (%s). Reconstruction forcée.", exc)

        try:
            idx.build_index()
            idx.save()
            return idx
        except Exception as exc:
            logger.warning("Impossible de construire l'index FAISS: %s", exc)
            return None

    def _prepare_mistral_client(self) -> MistralSearchV2:
        try:
            # CORRECTION : Suppression de 'use_embeddings'
            return MistralSearchV2(
                self.api,
                allow_offline_debug=True,
            )
        except Exception as exc:
            logger.error("Initialisation MistralSearch échouée: %s", exc)
            raise

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def list_codes(self) -> List[Dict[str, str]]:
        return [{"id": key, "label": value} for key, value in self.api.CODES_DISPO.items()]

    def ask(self, question: str, code_nom: Optional[str] = None) -> Dict[str, Any]:
        """Méthode mise à jour pour utiliser le pipeline V2."""
        question = (question or "").strip()
        if not question:
            raise ValueError("La question ne peut pas être vide.")

        if code_nom and code_nom not in self.api.CODES_DISPO.values():
            logger.info("Code fourni non reconnu (%s). Recherche tous codes.", code_nom)
            code_nom = None

        effective_code = code_nom or self._infer_code_from_question(question)

        # CORRECTION 3 : Utilisation de process_question (pipeline complet V2)
        # au lieu de intelligent_search + generate_analysis
        analysis_result = self.mistral_search.process_question(question, code_nom=effective_code)
        
        # Récupération des articles depuis les métadonnées de la réponse V2
        articles_bruts = analysis_result.get("metadata", {}).get("articles_bruts", [])
        
        answer_text = self._format_answer(analysis_result)

        if articles_bruts:
            try:
                self.data_processor._process_and_save_articles(articles_bruts, question)
                self.data_processor.export_to_csv()
            except Exception as exc:
                logger.warning("Impossible de sauvegarder les articles: %s", exc)

        return {
            "question": question,
            "code": effective_code,
            "answer": answer_text,
            "analysis": analysis_result, # On renvoie l'objet JSON complet
            "articles": self._serialize_articles(articles_bruts),
            "query_analysis": {
                "keywords": analysis_result.get("metadata", {}).get("keywords_utilises", []),
                "hypothesis": analysis_result.get("hypothesis_originale")
            },
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "offline" if getattr(self.mistral_search, "_offline_debug", False) else "online",
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _build_empty_response(self, question: str, code: Optional[str], search_res: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "question": question,
            "code": code,
            "answer": "INFORMATION_INSUFFISANTE",
            "analysis": {},
            "articles": [],
            "query_analysis": {},
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "offline" if getattr(self.mistral_search, "_offline_debug", False) else "online",
        }

    def _format_answer(self, analysis_payload: Any) -> str:
        # Si c'est déjà une string, on la retourne
        if isinstance(analysis_payload, str):
            return analysis_payload
        
        # Si c'est le dict complexe de la V2, on essaie de faire un joli résumé texte
        # ou on retourne le JSON formaté
        if isinstance(analysis_payload, dict):
             # Optionnel : Vous pouvez construire un string Markdown ici si le frontend attend du texte pur
             # Pour l'instant, on retourne le JSON stringifié pour que le front puisse parser
             return json.dumps(analysis_payload, ensure_ascii=False, indent=2)

        return str(analysis_payload)

    def _serialize_articles(self, articles: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
        cleaned = []
        for art in articles[:limit]:
            cleaned.append(
                {
                    "id": art.get("id") or art.get("article_id"),
                    "title": art.get("title") or art.get("titre"),
                    "code": art.get("code_name") or art.get("code"),
                    "excerpt": (art.get("content") or art.get("contenu") or "")[:700],
                    "source": art.get("source"),
                }
            )
        return cleaned

    def _infer_code_from_question(self, question: str) -> Optional[str]:
        q = (question or "").lower()
        for code_name, keywords in self._CODE_HINTS:
            if code_name not in self.api.CODES_DISPO.values():
                continue
            if any(token in q for token in keywords):
                return code_name
        return None

    @property
    def mode(self) -> str:
        return "offline" if getattr(self.mistral_search, "_offline_debug", False) else "online"


_SERVICE_LOCK = threading.Lock()
_ASSISTANT_INSTANCE: Optional[AssistantService] = None


def get_assistant_service() -> AssistantService:
    global _ASSISTANT_INSTANCE
    if _ASSISTANT_INSTANCE is None:
        with _SERVICE_LOCK:
            if _ASSISTANT_INSTANCE is None:
                _ASSISTANT_INSTANCE = AssistantService()
    return _ASSISTANT_INSTANCE