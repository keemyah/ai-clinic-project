import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from api_connector import LegiFranceAPI
from data_processor import DataProcessor
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
        
        self.embedding_index = None
        if enable_embeddings:
            self.embedding_index = self._prepare_embedding_index()

        self.mistral_search = self._prepare_mistral_client()

    # ------------------------------------------------------------------ #
    # Initialisations
    # ------------------------------------------------------------------ #
    
    def _prepare_mistral_client(self) -> MistralSearchV2:
        try:
            return MistralSearchV2(
                self.api,
                allow_offline_debug=False,  # <--- CHANGEZ ICI (Mettre False au lieu de True)
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
        question = (question or "").strip()
        if not question:
            raise ValueError("La question ne peut pas être vide.")

        effective_code = code_nom or self._infer_code_from_question(question)

        # Appel au pipeline V2
        analysis_result = self.mistral_search.process_question(question, code_nom=effective_code)
        
        articles_bruts = analysis_result.get("metadata", {}).get("articles_bruts", [])
        
        # CORRECTION ICI : On utilise le formateur Markdown
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
            "answer": answer_text, # Contient maintenant du Markdown propre
            "analysis": analysis_result,
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
    def _format_answer(self, data: Any) -> str:
        """Convertit le dictionnaire de résultats en texte Markdown lisible."""
        if isinstance(data, str):
            return data
        
        if not isinstance(data, dict):
            return str(data)

        # Construction de la réponse en Markdown
        md_lines = []

        # 1. Validation / Conclusion directe
        validation = data.get("validation_hypothesis", "Analyse en cours")
        if validation:
            md_lines.append(f"### ⚖️ Conclusion : {validation}")
        
        md_lines.append("") # Saut de ligne

        # 2. Synthèse
        synthese = data.get("synthese")
        if synthese:
            md_lines.append(f"**Synthèse** : {synthese}")
            md_lines.append("")

        # 3. Argumentation (points clés)
        argumentation = data.get("argumentation", [])
        if argumentation:
            md_lines.append("#### 💡 Analyse détaillée")
            if isinstance(argumentation, list):
                for arg in argumentation:
                    md_lines.append(f"- {arg}")
            else:
                md_lines.append(str(argumentation))
            md_lines.append("")

        # 4. Risques
        risques = data.get("risques", [])
        if risques:
            md_lines.append("#### ⚠️ Risques identifiés")
            for risque in risques:
                md_lines.append(f"- {risque}")
            md_lines.append("")

        # 5. Recommandations
        recos = data.get("recommandations", [])
        if recos:
            md_lines.append("#### ✅ Recommandations")
            for reco in recos:
                md_lines.append(f"1. {reco}")
            md_lines.append("")

        # 6. Textes de loi
        textes = data.get("textes_applicables", [])
        if textes:
            md_lines.append("---")
            md_lines.append(f"*Sources juridiques : {', '.join([str(t) for t in textes])}*")

        return "\n".join(md_lines)

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