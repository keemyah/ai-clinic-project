# mistral_search_v2.py - Version fonctionnelle et complète
import os
import time
import logging
import re
import json
import traceback
from typing import List, Dict, Optional
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MistralSearchV2:
    """
    Pipeline en 3 étapes:
    1. LLM génère une hypothèse juridique structurée
    2. Recherche API avec keywords extraits
    3. LLM construit réponse finale + vérification des citations
    """

    def __init__(self, api_connector, api_key=None, model_chat="mistral-large-latest",
                 model_hypothesis = "mistral-small-latest",
                 allow_offline_debug=False):
        self.api = api_connector
        self.model_chat = model_chat
        self.model_hypothesis = model_hypothesis
        self.max_results = 10
        self.chat_timeout = 60

        self.client = None
        self.available = False
        self._init_error = None
        self._offline_debug = allow_offline_debug

        # Résolution clé API
        if api_key is None:
            api_key = os.getenv("MISTRAL_API_KEY")

        if not api_key:
            msg = "Clé API Mistral non trouvée."
            logger.warning(msg)
            if allow_offline_debug:
                self._offline_debug = True
                return
            else:
                raise ValueError(msg)

        # Initialisation du client
        try:
            from mistralai import Mistral
            self.client = Mistral(api_key=api_key)
            self.available = True
            logger.info("✅ Client Mistral initialisé")
        except Exception as e:
            self._init_error = e
            logger.error(f"Erreur init Mistral: {e}")
            if allow_offline_debug:
                self._offline_debug = True
            else:
                raise RuntimeError(f"Impossible d'initialiser Mistral: {e}")

    # =========================================================================
    # ÉTAPE 1 : GÉNÉRATION D'HYPOTHÈSE
    # =========================================================================

    def generate_hypothesis(self, question: str) -> Dict:
        """Génère une hypothèse juridique structurée."""
        logger.info("🔍 ÉTAPE 1 : Génération d'hypothèse")

        if self._offline_debug:
            return {
                "hypothesis": "SIMULATION - Hypothèse de test",
                "keywords": ["test", "simulation"],
                "legal_domain": "général",
                "context": "Mode debug",
                "serach_scope" : "code_seul"
            }

        system_msg = """Tu es un expert juridique français. Analyse la question et génère:
1. **hypothesis**: Une hypothèse juridique plausible (max 200 mots)
2. **keywords**: 4-10 mots-clés techniques pour la recherche
3. **legal_domain**: Domaine parmi [fiscal, civil, pénal, travail, commercial, route, propriété intellectuelle, environnement, général]
4. **context**: Contexte factuel extract (max 70 mots)
5. **search_scope**: Recommande le périmètre de recherche : 'code_seul' (si la réponse est probablement dans le code), 'code_et_affiliés' (si décrets, arrêtés, ou lois non codifiées sont nécessaires), ou 'jurisprudence_et_code' (si l'interprétation par les tribunaux est clé).

Réponds en JSON strict avec ces clés."""

        prompt = f"QUESTION: {question}\nGénère l'analyse hypothétique."

        try:
            raw = self._call_chat(prompt, max_tokens=600, temperature=0.77, system_message=system_msg,force_json = True,model_override=self.model_hypothesis)
            cleaned = self._extract_json_from_markdown(raw)
            data = json.loads(cleaned)

            # Validation
            if isinstance(data.get("keywords"), str):
                data["keywords"] = [data["keywords"]]

            return {
                "hypothesis": data.get("hypothesis", "Hypothèse non générée"),
                "keywords": data.get("keywords", self._extract_simple_keywords(question)),
                "legal_domain": data.get("legal_domain", "général"),
                "context": data.get("context", "")
            }
        except Exception as e:
            logger.error(f"Erreur hypothèse: {e}")
            return {
                "hypothesis": f"Erreur: {str(e)}",
                "keywords": self._extract_simple_keywords(question),
                "legal_domain": "général",
                "context": ""
            }

    # =========================================================================
    # ÉTAPE 2 : RECHERCHE API
    # =========================================================================

    def search_with_hypothesis(self, hypothesis_data: Dict, code_nom: Optional[str] = None) -> List[Dict]:
        """Recherche API avec les keywords de l'hypothèse."""
        logger.info("🔎 ÉTAPE 2 : Recherche API")

        keywords = hypothesis_data.get("keywords", [])
        if not keywords:
            keywords = self._extract_simple_keywords(hypothesis_data.get("hypothesis", ""))

        search_query = " ".join(keywords[:5])
        logger.info(f"🔍 Recherche: '{search_query}'")

        try:
            results = self.api.rechercher_articles(search_query, code_nom, page_size=self.max_results)
            if not results or not results.get("results"):
                return []

            articles = []
            for res in results["results"][:self.max_results]:
                info = self.api._normaliser_article(res)
                articles.append({
                    "id": info.get("id"),
                    "title": info.get("titre"),
                    "content": info.get("contenu"),
                    "code_name": info.get("code"),
                    "legal_status": info.get("etat"),
                    "section": info.get("section"),
                    "numero": info.get("numero"),
                    "source": "api_legifrance"
                })

            logger.info(f"✅ {len(articles)} articles trouvés")
            return articles
        except Exception as e:
            logger.error(f"Erreur recherche API: {e}")
            return []

    # =========================================================================
    # ÉTAPE 3 : CONSTRUCTION RÉPONSE + VÉRIFICATION
    # =========================================================================

    def build_final_answer(self, question: str, hypothesis_data: Dict, articles: List[Dict]) -> Dict:
        """Construit la réponse finale et vérifie les citations."""
        logger.info("📝 ÉTAPE 3 : Construction réponse finale")

        if not articles:
            return self._create_no_source_response(question, hypothesis_data)

        snippets = self._prepare_juridical_snippets(articles)

        # Créer une liste formatée des sources
        sources_list = []
        for s in snippets:
            source_info = f"[[source:{s['id']}]] - {s['title']}\n"
            source_info += f"Contenu: {s['text']}\n"
            sources_list.append(source_info)

        snippet_block = "\n---\n".join(sources_list)

        # Prompt amélioré avec instructions plus strictes
        system_msg = """Tu es un assistant juridique senior. Ta mission est d'analyser la question posée uniquement à partir des textes de loi fournis dans la section SOURCES.

        Tu dois impérativement :
        1. ANALYSER en profondeur les SOURCES pour extraire tous les détails pertinents.
        2. VALIDER ou CORRIGER l'hypothèse initiale avec les textes légaux.
        3. RENSEIGNER l'argumentation en détail en citant précisément les articles pertinents avec [].
        4. IDENTIFIER les implications légales, les risques et les recommandations.
        5. RÉPONSE: STRICTEMENT en JSON 
        
    Format de réponse JSON OBLIGATOIRE avec ces champs :
    - validation_hypothesis: "VALIDÉE" ou "CORRIGÉE" + explication
    - textes_applicables: liste des IDs des sources utilisées (ex: ["ID1", "ID2"])
    - argumentation: liste de paragraphes, CHAQUE citation DOIT utiliser [[source:ID]]
    - hypotheses: interprétations possibles
    - risques: risques juridiques identifiés
    - synthese: synthèse concise
    - recommandations: recommandations pratiques

    ATTENTION : Si aucune source ne traite directement de la question, dire clairement "AUCUNE SOURCE PERTINENTE" et expliquer pourquoi."""

        prompt = f"""QUESTION JURIDIQUE : {question}

    HYPOTHÈSE INITIALE : {hypothesis_data['hypothesis']}

    SOURCES OFFICIELLES TROUVÉES :
    {snippet_block}

    ANALYSE REQUISE :
    1. Pour CHAQUE source, identifie si elle est pertinente pour la question
    2. Extrait les informations CLÉS de chaque source pertinente
    3. Construit une réponse DÉTAILLÉE avec citations PRÉCISES [[source:ID]]
    4. Compare avec l'hypothèse initiale
    5. Fournis une réponse complète et documentée qui répond bien à la question posée

    RÉPONSE :"""

        try:
            logger.info(f"📤 Envoi de {len(snippets)} snippets au LLM")
            logger.info(f"📊 Taille totale du contexte: {len(prompt)} caractères")

            raw = self._call_chat(prompt, max_tokens=2500, temperature=0.2,
                                  system_message=system_msg, force_json=True)

            logger.info(f"📄 Réponse LLM reçue, taille: {len(raw)} caractères")

            cleaned = self._extract_json_from_markdown(raw)
            parsed = json.loads(cleaned)

            logger.info(f"✅ JSON parsé avec succès")
            logger.info(f"📋 Clés: {list(parsed.keys())}")

            # VÉRIFICATION DES CITATIONS
            verified = self._verify_citations(parsed, snippets)

            return self._normalize_final_response(verified, question, hypothesis_data, snippets, articles)

        except json.JSONDecodeError as e:
            logger.error(f"❌ Erreur JSON: {e}")
            logger.error(f"📄 Texte brut (500 premiers chars): {raw[:500] if 'raw' in locals() else 'N/A'}")
            return self._create_error_response(f"Erreur format JSON: {str(e)}", question, hypothesis_data)
        except Exception as e:
            logger.error(f"❌ Erreur construction réponse: {e}")
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            return self._create_error_response(str(e), question, hypothesis_data)

    # =========================================================================
    # UTILITAIRES
    # =========================================================================

    def _detect_legal_domain(self, articles: List[Dict]) -> str:
        """Détecte le domaine juridique à partir des articles trouvés."""
        if not articles:
            return "général"

        codes = [art.get("code_name", "").lower() for art in articles[:3]]
        if any("impôt" in c or "fiscal" in c for c in codes):
            return "droit fiscal"
        elif any("pénal" in c for c in codes):
            return "droit pénal"
        elif any("travail" in c for c in codes):
            return "droit du travail"
        elif any("civil" in c for c in codes):
            return "droit civil"
        elif any("route" in c for c in codes):
            return "code de la route"
        elif any("commerce" in c for c in codes):
            return "droit commercial"
        elif any("propriété intellectuelle" in c for c in codes):
            return "propriété intellectuelle"
        elif any("environnement" in c for c in codes):
            return "droit environnemental"
        else:
            return "général"

    def _generate_domain_recommendations(self, domain: str, question: str) -> List[str]:
        """Génère des recommandations contextuelles par domaine."""
        base = [
            "Consultez la version officielle sur Légifrance (legifrance.gouv.fr)"
        ]

        domain_map = {
            "droit fiscal": [
                "Site: impots.gouv.fr (taux, simulateurs)",
                "Votre espace personnel impots.gouv.fr",
                "Centre des finances publiques"
            ],
            "droit du travail": [
                "Convention collective applicable (Legifrance)",
                "Inspection du travail",
                "Code du travail annoté (ministère)"
            ],
            "droit civil": [
                "Notaire pour succession/donation",
                "Jurisprudence JurisData",
                "Associations de consommateurs"
            ],
            "droit pénal": [
                "Avocat pénaliste (obligation légale)",
                "Ministère de la Justice",
                "Décisions de cassation (Legifrance)"
            ],
            "code de la route": [
                "Code de la route (Legifrance)",
                "Site officiel ANTS",
                "Préfecture pour permis"
            ],
            "propriété intellectuelle": [
                "INPI (brevets/marques)",
                "Bases jurisprudence Darts-IP",
                "Avocat spécialisé PI"
            ]
        }

        return base + domain_map.get(domain, ["Contactez un professionnel du droit"])

    def _prepare_juridical_snippets(self, articles: List[Dict]) -> List[Dict]:
        """Chunking juridique intelligent - inclut plus de contenu."""
        snippets = []

        for i, art in enumerate(articles[:8]):  # Augmenté à 8 articles
            art_id = str(art.get("id") or f"unk_{i}")
            title = art.get("title") or "(sans titre)"
            content = art.get("content") or ""

            if hasattr(self.api, "_nettoyer_texte"):
                content = self.api._nettoyer_texte(content)

            if not content:
                continue

            # Diviser le contenu en parties plus grandes
            alineas = re.split(r'\n\s*\n', content)

            # Prendre les 7 premiers alinéas maximum
            text_chunks = []
            current_chunk = ""

            for alinea in alineas[:7]:
                if not alinea.strip():
                    continue

                if len(current_chunk) + len(alinea) < 2000:
                    if current_chunk:
                        current_chunk += "\n\n" + alinea.strip()
                    else:
                        current_chunk = alinea.strip()
                else:
                    # Chunk plein, sauvegarder et commencer un nouveau
                    if current_chunk:
                        text_chunks.append(current_chunk)
                    current_chunk = alinea.strip()

            # Ajouter le dernier chunk
            if current_chunk:
                text_chunks.append(current_chunk)

            # Créer un snippet par chunk
            for idx, chunk in enumerate(text_chunks[:3]):
                if chunk.strip():
                    snippets.append({
                        "id": f"{art_id}__{idx}",
                        "art_id": art_id,
                        "title": title,
                        "text": chunk.strip()[:2500]
                    })

        logger.info(f"📄 Préparé {len(snippets)} snippets de {len(articles[:8])} articles")
        return snippets

    def _verify_citations(self, parsed: Dict, snippets: List[Dict]) -> Dict:
        """Vérifie que chaque citation correspond à un snippet existant."""
        allowed_ids = {s["id"] for s in snippets}
        result = parsed.copy()

        # Normaliser argumentation en liste de strings
        if "argumentation" in result:
            argumentation = result["argumentation"]
            if isinstance(argumentation, dict):
                # Convertir dict en list
                argumentation_list = []
                for key, value in argumentation.items():
                    if isinstance(value, list):
                        for item in value:
                            argumentation_list.append(str(item))
                    else:
                        argumentation_list.append(str(value))
                result["argumentation"] = argumentation_list
            elif not isinstance(argumentation, list):
                result["argumentation"] = [str(argumentation)]

        # Vérifier les citations dans argumentation
        citations_found = []
        for arg in result.get("argumentation", []):
            if isinstance(arg, str):
                # Rechercher les citations [[source:...]]
                citations = re.findall(r'\[\[source:([^\]]+)\]\]', arg)
                citations_found.extend(citations)

                # Vérifier aussi les formats alternatifs
                alt_citations = re.findall(r'\[source:([^\]]+)\]', arg)
                citations_found.extend(alt_citations)

                # Vérifier les références numériques
                num_citations = re.findall(r'article\s+([A-Za-z0-9\-\.]+)', arg, re.IGNORECASE)
                citations_found.extend(num_citations)

        # Vérifier textes_applicables
        if "textes_applicables" in result:
            textes = result["textes_applicables"]
            if not isinstance(textes, list):
                textes = [textes]

            filtered_textes = []
            for item in textes:
                if isinstance(item, dict) and "id" in item:
                    item = item["id"]
                item_str = str(item)
                if item_str in allowed_ids:
                    filtered_textes.append(item_str)
                else:
                    # Chercher un ID partiel
                    for allowed_id in allowed_ids:
                        if item_str in allowed_id or allowed_id in item_str:
                            filtered_textes.append(allowed_id)
                            break

            result["textes_applicables"] = filtered_textes

        if not citations_found:
            logger.warning("⚠️ Aucune citation trouvée dans l'argumentation")
            if isinstance(result.get("argumentation"), list):
                result["argumentation"].append(
                    "⚠️ REMARQUE: Les sources ont été analysées mais aucune citation directe n'a pu être extraite.")

        logger.info(f"📌 {len(citations_found)} citations trouvées dans la réponse")

        return result

    def _normalize_final_response(self, parsed: Dict, question: str,
                                  hypothesis_data: Dict, snippets: List[Dict],
                                  articles: List[Dict]) -> Dict:
        """Normalise la réponse finale en structure cohérente."""

        try:
            # Détecte le domaine pour les recommandations
            domain = self._detect_legal_domain_from_snippets(snippets)

            # Structure de base
            normalized = {
                "validation_hypothesis": parsed.get("validation_hypothesis", "Non spécifiée"),
                "hypothesis_originale": hypothesis_data.get("hypothesis"),
                "qualification": parsed.get("qualification", "Non spécifiée"),
                "textes_applicables": self._ensure_list(parsed.get("textes_applicables", [])),
                "argumentation": self._ensure_list(parsed.get("argumentation", [])),
                "hypotheses": self._ensure_list(parsed.get("hypotheses", [])),
                "risques": self._ensure_list(parsed.get("risques", [])),
                "synthese": parsed.get("synthese", ""),
                "recommandations": self._ensure_list(parsed.get("recommandations", [])),
                "metadata": {
                    "question": question,
                    "domaine_detecte": domain,
                    "keywords_utilises": hypothesis_data.get("keywords", []),
                    "contexte": hypothesis_data.get("context", ""),
                    "nombre_sources": len(snippets),
                    "sources_utilisees": parsed.get("textes_applicables", []),
                    "articles_bruts": articles,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "pipeline": "hypothesis_first_v2"
                }
            }

            return normalized
        except Exception as e:
            logger.error(f"Erreur normalisation réponse: {e}")
            # Fallback minimal
            return {
                "validation_hypothesis": "ERREUR_NORMALISATION",
                "hypothesis_originale": hypothesis_data.get("hypothesis"),
                "qualification": "ERREUR_FORMAT",
                "textes_applicables": [],
                "argumentation": [f"Erreur technique: {str(e)}"],
                "hypotheses": [],
                "risques": [],
                "synthese": "Erreur lors du formatage de la réponse.",
                "recommandations": ["Consultez un professionnel du droit"],
                "metadata": {"normalization_error": str(e)}
            }

    def _detect_legal_domain_from_snippets(self, snippets: List[Dict]) -> str:
        """Détecte le domaine à partir des snippets si articles vides."""
        if not snippets:
            return "général"

        # Regarde le premier snippet
        title = snippets[0].get("title", "").lower()
        if "fiscal" in title or "impôt" in title:
            return "droit fiscal"
        elif "pénal" in title:
            return "droit pénal"
        elif "travail" in title:
            return "droit du travail"
        return "général"

    def _ensure_list(self, value):
        """Assure qu'une valeur est une liste."""
        if isinstance(value, list):
            return value
        return [value] if value else []

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extrait le JSON depuis le markdown ou le texte brut."""
        # Supprime les caractères de contrôle
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', ' ', text)
        text = text.replace('\\\\', '\\')

        # Essaie d'abord le bloc JSON
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1)

        # Fallback: extrait entre accolades
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return text[start:end + 1]

        return "{}"

    def _extract_simple_keywords(self, text: str) -> List[str]:
        """Extraction basique de mots-clés."""
        stopwords = {"le", "la", "les", "un", "une", "de", "du", "des", "et", "ou", "dans", "pour", "par", "sur"}
        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if len(w) > 3 and w not in stopwords][:5]

    def _call_chat(self, prompt: str, max_tokens: int = 500,
                   temperature: float = 0.0, retries: int = 2,
                   system_message: Optional[str] = None,
                   model_override: Optional[str] = None,
                   force_json : bool = False) -> str:
        """Appel robuste au client Mistral."""
        if self._offline_debug:
            return '{"hypothesis": "DEBUG", "keywords": ["test"], "legal_domain": "général"}'

        model_to_use = model_override if model_override else self.model_chat

        for attempt in range(1, retries + 2):
            try:
                messages = [{"role": "user", "content": prompt}]
                if system_message:
                    messages = [{"role": "system", "content": system_message}] + messages

                if self.client is None:
                    raise RuntimeError("Client non initialisé")

                if hasattr(self.client, "chat") and hasattr(self.client.chat, "complete"):

                    call_params = {
                        "model": model_to_use,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    }
                    if force_json:
                        call_params["response_format"] = {"type": "json_object"}

                    resp = self.client.chat.complete(**call_params)
                    return self._extract_text_from_response(resp)

                raise RuntimeError("Signature SDK non reconnue")

            except Exception as e:
                error_message = str(e)
                if "429" in str(e).lower():
                    wait = 5 * attempt
                    logger.warning(f"429 → attente {wait}s")
                    time.sleep(wait)
                    continue
                time.sleep(1 * attempt)
            logger.error(f"Erreur API Mistral (Tentative {attempt}): {error_message}")
            time.sleep(1 * attempt)  # Attend avant de réessayer (pour les erreurs non-429)
            continue
        raise RuntimeError(f"Échec appel Mistral après {retries + 1} tentatives. Dernière erreur: {error_message}")

    def _extract_text_from_response(self, resp):
        """Extrait le texte depuis la réponse SDK."""
        try:
            if isinstance(resp, dict) and "choices" in resp:
                c = resp["choices"][0]
                if isinstance(c, dict) and "message" in c:
                    return c["message"]["content"]
            if hasattr(resp, "choices") and len(resp.choices) > 0:
                ch = resp.choices[0]
                if hasattr(ch, "message") and hasattr(ch.message, "content"):
                    return ch.message.content
            return str(resp)
        except Exception:
            return str(resp)

    # =========================================================================
    # GESTION DES ERREURS
    # =========================================================================

    def _create_no_source_response(self, question: str, hypothesis_data: Dict) -> Dict:
        """Réponse quand aucune source n'est trouvée."""
        domain = hypothesis_data.get("legal_domain", "général")
        return {
            "validation_hypothesis": "IMPOSSIBLE - Aucune source",
            "hypothesis_originale": hypothesis_data.get("hypothesis"),
            "qualification": "INFORMATION_INSUFFISANTE",
            "textes_applicables": [],
            "argumentation": ["Aucun article pertinent trouvé dans l'API LégiFrance"],
            "hypotheses": [hypothesis_data.get("hypothesis")],
            "risques": ["Impossible de valider sans sources officielles"],
            "synthese": "Aucune source juridique n'a pu être identifiée.",
            "recommandations": self._generate_domain_recommendations(domain, question),
            "metadata": {
                "error": "no_sources",
                "domaine_detecte": domain,
                "question": question
            }
        }

    def _create_error_response(self, error: str, question: str, hypothesis_data: Dict) -> Dict:
        """Réponse d'erreur."""
        domain = hypothesis_data.get("legal_domain", "général")
        return {
            "validation_hypothesis": f"ERREUR - {error}",
            "hypothesis_originale": hypothesis_data.get("hypothesis"),
            "qualification": "ERREUR_TRAITEMENT",
            "textes_applicables": [],
            "argumentation": [f"Erreur: {error}"],
            "hypotheses": [hypothesis_data.get("hypothesis")],
            "risques": [],
            "synthese": f"Erreur lors du traitement: {error}",
            "recommandations": self._generate_domain_recommendations(domain, question),
            "metadata": {"error": error}
        }

    def _create_critical_error(self, question: str, error: str) -> Dict:
        """Erreur critique du pipeline."""
        return {
            "validation_hypothesis": "ERREUR CRITIQUE",
            "hypothesis_originale": None,
            "qualification": "ERREUR_PIPELINE",
            "textes_applicables": [],
            "argumentation": [f"Erreur critique: {error}"],
            "hypotheses": [],
            "risques": [],
            "synthese": f"Pipeline en échec: {error}",
            "recommandations": ["Vérifiez les logs", "Contactez le support"],
            "metadata": {"critical_error": error}
        }

    # =========================================================================
    # MÉTHODE PRINCIPALE
    # =========================================================================

    def process_question(self, question: str, code_nom: Optional[str] = None) -> Dict:
        """Pipeline complet."""
        logger.info("=" * 70)
        logger.info("🚀 PIPELINE V2 (Hypothesis-First)")

        try:
            hypothesis = self.generate_hypothesis(question)
            articles = self.search_with_hypothesis(hypothesis, code_nom)
            return self.build_final_answer(question, hypothesis, articles)

        except Exception as e:
            logger.error(f"Erreur pipeline: {e}")
            return self._create_critical_error(question, str(e))

    # =========================================================================
    # FORMATAGE
    # =========================================================================

    def format_analysis_for_display(self, analysis: Dict) -> str:
        """Formate pour affichage utilisateur."""
        if not isinstance(analysis, dict):
            return str(analysis)

        output = []
        output.append("\n" + "=" * 70)
        output.append("📋 ANALYSE JURIDIQUE V2")
        output.append("=" * 70)

        if analysis.get("hypothesis_originale"):
            output.append(f"\n💡 Hypothèse: {analysis['hypothesis_originale']}")

        if analysis.get("validation_hypothesis"):
            output.append(f"\n✓ Validation: {analysis['validation_hypothesis']}")

        output.append(f"\n📖 Qualification: {analysis.get('qualification', 'N/A')}")

        if analysis.get("textes_applicables"):
            output.append(f"\n📚 Textes ({len(analysis['textes_applicables'])}):")
            for i, t in enumerate(analysis['textes_applicables'], 1):
                output.append(f"   {i}. {t}")

        if analysis.get("argumentation"):
            output.append(f"\n💡 Argumentation:")
            for i, a in enumerate(analysis['argumentation'], 1):
                output.append(f"   {i}. {a}")

        if analysis.get("recommandations"):
            output.append(f"\n✅ Recommandations:")
            for i, r in enumerate(analysis['recommandations'], 1):
                output.append(f"   {i}. {r}")

        output.append("\n" + "=" * 70)
        return "\n".join(output)