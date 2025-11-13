import re
import json
import requests
from datetime import datetime


class LegiFranceAPI:
    def __init__(self, client_id, client_secret):
        self.CLIENT_ID = client_id
        self.CLIENT_SECRET = client_secret
        self.SCOPE = "openid"
        self.TOKEN_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
        self.BASE_URL = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app"
        self.token = None

        self.CODES_DISPO = {
            "1": "Code civil", "2": "Code du travail", "3": "Code de commerce",
            "4": "Code pénal", "5": "Code de la route", "6": "Code de la santé publique",
            "7": "Code de l'action sociale et des familles", "8": "Code de l'éducation",
            "9": "Code de la propriété intellectuelle", "10": "Code de l'environnement",
            "11": "Code général des impôts", "12": "Code des postes et des communications électroniques"
        }

    def get_token(self):
        if self.token:
            return self.token
        try:
            r = requests.post(
                self.TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.CLIENT_ID, self.CLIENT_SECRET),
                timeout=10,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            )
            if r.status_code == 200:
                self.token = r.json()["access_token"]
                return self.token
            raise RuntimeError(f"Token error: {r.status_code} {r.text}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Erreur réseau OAuth: {e}")

    def rechercher_articles(self, mots_cles, code_nom=None, page_size=20):
        token = self.get_token()
        url = f"{self.BASE_URL}/search"

        payload = {
            "fond": "CODE_ETAT",
            "recherche": {
                "champs": [
                    {"typeChamp": "ARTICLE", "criteres": [{"typeRecherche": "UN_DES_MOTS", "valeur": mots_cles, "operateur": "ET"}], "operateur": "ET"}
                ],
                "pageNumber": 1,
                "pageSize": page_size,
                "operateur": "ET",
                "sort": "PERTINENCE",
                "typePagination": "ARTICLE",
                "withDetails": True,
                "withContent": True
            }
        }

        if code_nom:
            payload["filtres"] = [{"facette": "TEXT_NOM_CODE", "valeurs": [code_nom]}]

        try:
            r = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
                timeout=15
            )
            if r.status_code == 200:
                return r.json()
            else:
                print(f"❌ Erreur API: {r.status_code} - {r.text}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur réseau: {e}")
            return None

    def get_article_complet(self, article_id):
        token = self.get_token()
        url = f"{self.BASE_URL}/consult/getArticle"
        try:
            r = requests.post(
                url,
                json={"id": article_id},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
                timeout=15
            )
            if r.status_code == 200:
                return r.json()
            else:
                print(f"❌ Erreur récupération article: {r.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur réseau: {e}")
            return None

    def afficher_codes(self):
        print("\n" + "=" * 50)
        print("📚 CODES DISPONIBLES")
        print("=" * 50)
        for num, nom in self.CODES_DISPO.items():
            print(f"{num}. {nom}")

    def choisir_code(self):
        while True:
            self.afficher_codes()
            choix = input("\n🔢 Choisissez un code (numéro) ou 'tous' pour tous les codes: ").strip()
            if choix.lower() == 'tous':
                return None
            elif choix in self.CODES_DISPO:
                return self.CODES_DISPO[choix]
            else:
                print("❌ Choix invalide. Veuillez réessayer.")

    @staticmethod
    def _nettoyer_texte(brut):
        if not brut:
            return ""
        texte = re.sub(r"<[^>]+>", " ", brut)
        texte = re.sub(r"\s+", " ", texte, flags=re.MULTILINE)
        return texte.strip()

    @staticmethod
    def _normaliser_article(article):
        bloc = article.get("item") or article.get("fields") or article
        titres_possibles = bloc.get("titles") or []
        code_nom = next((t.get("title") for t in titres_possibles if t.get("title")), bloc.get("codeName") or bloc.get("code") or "Code inconnu")
        sections = bloc.get("sections") or []
        for section in sections:
            extracts = section.get("extracts") or []
            for extract in extracts:
                contenu = " ".join(extract.get("values") or [])
                if contenu:
                    contenu = LegiFranceAPI._nettoyer_texte(contenu)
                    return {
                        "id": extract.get("id") or bloc.get("id"),
                        "code": code_nom,
                        "etat": extract.get("legalStatus") or section.get("legalStatus") or bloc.get("etat"),
                        "titre": extract.get("title") or section.get("title") or bloc.get("title"),
                        "section": section.get("title"),
                        "numero": extract.get("num"),
                        "contenu": contenu
                    }
        return {
            "id": bloc.get("id"),
            "code": code_nom,
            "etat": bloc.get("legalStatus") or bloc.get("etat"),
            "titre": bloc.get("title"),
            "section": None,
            "numero": None,
            "contenu": LegiFranceAPI._nettoyer_texte(bloc.get("content") or bloc.get("text") or "")
        }
