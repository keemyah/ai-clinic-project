import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from api_connector import LegiFranceAPI


class DataProcessor:
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self._setup_directories()

    def _setup_directories(self):
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def save_api_response(self, api_response, query_keywords, code_nom=None):
        if not api_response or 'results' not in api_response:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_{timestamp}.json"
        data_to_save = {
            "metadata": {"extraction_date": timestamp, "query_keywords": query_keywords, "code_nom": code_nom, "result_count": len(api_response['results'])},
            "results": api_response['results']
        }
        filepath = self.raw_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)

        # Process articles individually
        self._process_and_save_articles(api_response['results'], query_keywords)
        return filepath

    def _process_and_save_articles(self, results, query_keywords):
        for result in results:
            article_data = self._extract_article_data(result, query_keywords)
            if article_data:
                self._save_individual_article(article_data)

    def _extract_article_data(self, raw_article, query_keywords):
        try:
            article_info = LegiFranceAPI._normaliser_article(raw_article)
            return {
                "article_id": article_info["id"],
                "code_name": article_info["code"],
                "title": article_info["titre"],
                "content": article_info["contenu"],
                "legal_status": article_info["etat"],
                "section": article_info["section"],
                "numero": article_info["numero"],
                "query_keywords": query_keywords,
                "extraction_date": datetime.now().isoformat(),
                "source": "legifrance_api"
            }
        except Exception as e:
            print(f"❌ Erreur extraction article: {e}")
            return None

    def _save_individual_article(self, article_data):
        filename = f"article_{article_data['article_id']}.json"
        filepath = self.processed_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(article_data, f, ensure_ascii=False, indent=2)

    def load_processed_articles(self):
        processed_files = list(self.processed_dir.glob("article_*.json"))
        articles = []
        for file in processed_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    articles.append(json.load(f))
            except Exception as e:
                print(f"❌ Erreur lecture {file}: {e}")
        print(f"📚 {len(articles)} articles chargés depuis le cache local")
        return articles

    def export_to_csv(self):
        articles = self.load_processed_articles()
        if articles:
            df = pd.DataFrame(articles)
            csv_path = self.processed_dir / "articles_dataset.csv"
            df.to_csv(csv_path, index=False, encoding='utf-8')
            print(f"💾 Données exportées vers: {csv_path}")
            return csv_path
        return None
