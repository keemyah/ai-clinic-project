import os
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()


from api_connector import LegiFranceAPI
from data_processor import DataProcessor
from mistral_search import MistralSearchV2

# NOUVEAU: Charger les variables d'environnement
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    print("🚀 LEGIFRANCE + MISTRAL AI - RECHERCHE JURIDIQUE (V2)")
    print("=" * 60)

    # Initialisation des composants
    api = LegiFranceAPI(CLIENT_ID, CLIENT_SECRET)
    data_processor = DataProcessor()

    # Initialisation de MistralSearchV2 avec gestion d'erreur
    mistral_search = None
    try:
        mistral_search = MistralSearchV2(api, allow_offline_debug=False)
        print("✅ MistralSearchV2 (Hypothesis-First) initialisé")
    except Exception as e:
        logger.error(f"Erreur init MistralSearchV2: {e}")
        print("🔶 Mistral non disponible - Mode simplifié activé")

    while True:
        question = input("\n🔎 Question (ou 'q' pour quitter): ").strip()
        if question.lower() in ['quit', 'exit', 'q']:
            break

        code_choisi = api.choisir_code()

        # ─── MODE AVEC MISTRAL V2 ─────────────────────────────────────
        if mistral_search and mistral_search.available:
            try:
                # Pipeline V2 complet
                analysis = mistral_search.process_question(question, code_nom=code_choisi)
                print(mistral_search.format_analysis_for_display(analysis))

                # Sauvegarde des articles (correctement indentée)
                articles_to_save = analysis.get('metadata', {}).get('articles_bruts', [])
                if articles_to_save:
                    data_processor._process_and_save_articles(articles_to_save, question)
                    data_processor.export_to_csv()
                    print(f"💾 {len(articles_to_save)} articles sauvegardés")

            except Exception as e:
                logger.error(f"Erreur pipeline V2: {e}")
                print("⚠️ Erreur Mistral, passage en mode simplifié...")
                _fallback_search(question, code_choisi, api, data_processor)

        # ─── MODE SANS MISTRAL (Fallback) ───────────────────────────
        else:
            _fallback_search(question, code_choisi, api, data_processor)


def _fallback_search(question: str, code_choisi: str, api: LegiFranceAPI, data_processor: DataProcessor):
    """Mode de secours sans IA : recherche par mots-clés simples."""
    print("\n⚠️  Mode sans IA - Recherche par keywords...")

    # Extraction simple de mots-clés
    keywords = " ".join([w for w in question.lower().split() if len(w) > 3])
    search_results = api.rechercher_articles(keywords, code_choisi, page_size=10)

    if not search_results or not search_results.get("results"):
        print("❌ Aucun article trouvé.")
        return

    articles = []
    for res in search_results["results"]:
        info = api._normaliser_article(res)
        articles.append({
            "id": info.get("id"),
            "title": info.get("titre"),
            "content": info.get("contenu"),
            "code_name": info.get("code")
        })

    # Affichage simple
    print(f"\n✅ {len(articles)} articles trouvés:")
    for i, art in enumerate(articles, 1):
        print(f"\n{i}. {art['title']}")
        print(f"   {art['content'][:250]}...")

    # Sauvegarde
    data_processor._process_and_save_articles(articles, question)
    data_processor.export_to_csv()
    print(f"💾 Données sauvegardées dans data/processed/")


if __name__ == "__main__":
    main()