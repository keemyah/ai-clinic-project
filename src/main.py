import os
import logging
from pathlib import Path
from api_connector import LegiFranceAPI
from data_processor import DataProcessor
from credentials import CLIENT_ID, CLIENT_SECRET

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("🚀 LEGIFRANCE + MISTRAL AI - RECHERCHE JURIDIQUE")
    print("="*60)

    api = LegiFranceAPI(CLIENT_ID, CLIENT_SECRET)
    data_processor = DataProcessor()

    try:
        from mistral_search import MistralSearch
        mistral_search = MistralSearch(api, use_embeddings=False)
        print("✅ MistralSearch initialisé")
    except:
        mistral_search = None
        print("🔶 Mistral non disponible")

    while True:
        question = input("\n🔎 Question (ou 'q' pour quitter): ").strip()
        if question.lower() in ['quit','exit','q']:
            break
        code_choisi = api.choisir_code()
        search_res = mistral_search.intelligent_search(question, code_nom=code_choisi)
        articles = search_res["combined_results"]
        if not articles:
            print("❌ Aucun article trouvé pour cette question.")
            continue

        analysis = mistral_search.generate_analysis(question, articles)
        print("\n📝 Analyse juridique générée :\n")
        print(analysis)

        # sauvegarde localement
        data_processor._process_and_save_articles(articles, question)
        data_processor.export_to_csv()

if __name__ == "__main__":
    main()
