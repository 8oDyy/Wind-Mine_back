# WineMind Backend

Backend API pour le chatbot sommelier de l'application WineMind.

## Stack

- **FastAPI** — framework web async
- **OpenAI SDK** — via GitHub Models (GPT-4o)
- **Docker** — containerisation
- **Python 3.13**

## Structure

```
app/
  main.py          # FastAPI application
requirements.txt
.env               # GITHUB_TOKEN (gitignored)
Dockerfile
docker-compose.yml
```

## Setup local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Créer un fichier `.env` à la racine :

```
GITHUB_TOKEN=your_github_pat_here
```

Lancer :

```bash
python -m app.main
```

## Docker

```bash
docker compose up --build
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

```bash
git clone <repo>
cp .env.example .env   # remplir GITHUB_TOKEN
docker compose up -d
```
