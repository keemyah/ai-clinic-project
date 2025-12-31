import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from assistant_service import AssistantService, get_assistant_service
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="Assistant Juridique API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


class ChatRequest(BaseModel):
    question: str
    code: str | None = None


@app.get("/api/health")
def health():
    try:
        service = get_assistant_service()
        return {"status": "ok", "mode": service.mode}
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        raise HTTPException(status_code=500, detail="Service non initialisé")


@app.get("/api/codes")
def list_codes():
    service = get_assistant_service()
    return {"codes": service.list_codes()}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    service = get_assistant_service()

    try:
        result = service.ask(request.question, request.code)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Erreur serveur durant /api/chat: %s", exc)
        raise HTTPException(status_code=500, detail="Erreur interne pendant l'analyse")
# ... (ton code existant s'arrête ici après la fonction chat)

if __name__ == "__main__":
    import uvicorn
    print("🚀 Démarrage du serveur API sur http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
