# pdf_utils.py
from fpdf import FPDF  # pip install fpdf2

def _clean_text(text):
    """Remplace les caractères non supportés par latin-1."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    replacements = {
        "’": "'",   # apostrophe typographique
        "“": '"',
        "”": '"',
        "•": "-",
        "–": "-",
        "—": "-",
        "…": "...",
        "•": "-",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def build_pdf_from_analysis(question, analysis) -> bytes:
    """Construit un PDF simple à partir de l'analyse retournée par MistralSearchV2."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Titre
    pdf.set_font("Arial", "B", 16)
    pdf.multi_cell(0, 10, _clean_text("Analyse juridique – Assistant Légifrance + Mistral"))
    pdf.ln(4)

    # Question
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, _clean_text(f"Question : {question}"))
    pdf.ln(4)

    # Qualification
    qualif = analysis.get("qualification", "—")
    pdf.set_font("Arial", "B", 12)
    pdf.multi_cell(0, 8, _clean_text("Qualification :"))
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, _clean_text(qualif))
    pdf.ln(3)

    # Textes applicables
    textes = analysis.get("textes_applicables", [])
    pdf.set_font("Arial", "B", 12)
    pdf.multi_cell(0, 8, _clean_text("Textes applicables :"))
    pdf.set_font("Arial", "", 12)
    if textes:
        for t in textes:
            pdf.multi_cell(0, 6, _clean_text(f"- {t}"))
    else:
        pdf.multi_cell(0, 6, _clean_text("Aucun texte cité."))
    pdf.ln(3)

    # Argumentation
    args = analysis.get("argumentation", [])
    pdf.set_font("Arial", "B", 12)
    pdf.multi_cell(0, 8, _clean_text("Argumentation :"))
    pdf.set_font("Arial", "", 12)
    for i, a in enumerate(args, 1):
        pdf.multi_cell(0, 6, _clean_text(f"{i}. {a}"))
        pdf.ln(1)

    # Risques
    risques = analysis.get("risques", [])
    pdf.ln(2)
    pdf.set_font("Arial", "B", 12)
    pdf.multi_cell(0, 8, _clean_text("Risques :"))
    pdf.set_font("Arial", "", 12)
    for r in risques:
        pdf.multi_cell(0, 6, _clean_text(f"- {r}"))

    # Synthèse
    synthese = analysis.get("synthese", "")
    pdf.ln(2)
    pdf.set_font("Arial", "B", 12)
    pdf.multi_cell(0, 8, _clean_text("Synthèse :"))
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 6, _clean_text(synthese))

    # Recommandations
    recos = analysis.get("recommandations", [])
    if recos:
        pdf.ln(2)
        pdf.set_font("Arial", "B", 12)
        pdf.multi_cell(0, 8, _clean_text("Recommandations :"))
        pdf.set_font("Arial", "", 12)
        for r in recos:
            pdf.multi_cell(0, 6, _clean_text(f"- {r}"))

    # Retourne le PDF en bytes
    # dest="S" → retourne une string binaire, qu'on encode en latin-1
    return pdf.output(dest="S").encode("latin-1")
