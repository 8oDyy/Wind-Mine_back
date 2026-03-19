# WineMind Backend

Backend API pour le chatbot sommelier de l'application WineMind.

## Stack

- **FastAPI** — framework web async
- **OpenAI SDK** — via GitHub Models (GPT-4o)
- **Python 3.11+**

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Créer un fichier `.env` à la racine :

```
GITHUB_TOKEN=your_github_pat_here
```

## Lancer

```bash
python main.py
```

Le serveur démarre sur `http://0.0.0.0:8000`.

## Endpoints

### `GET /health`

Health check.

### `POST /chat`

```json
{
  "message": "Quel vin pour un boeuf bourguignon ?",
  "history": [
    {"role": "user", "content": "Bonjour"},
    {"role": "assistant", "content": "Bonjour ! Comment puis-je vous aider ?"}
  ]
}
```

Réponse :

```json
{
  "reply": "Pour un bœuf bourguignon, un Pinot Noir de Bourgogne..."
}
```

## Déploiement VM

À venir — configurer `uvicorn` derrière un reverse proxy (nginx/caddy).
