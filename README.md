# WineMind Backend

Backend API pour le chatbot sommelier de l'application WineMind.

## Stack

- **FastAPI** — framework web async
- **OpenAI SDK** — via GitHub Models (GPT-4o)
- **Supabase** — stockage images (signed URLs)
- **Docker** — containerisation
- **Python 3.13**

## Structure

```
app/
  main.py                        # FastAPI application
  routers/
    wine_pairing.py              # Route POST /api/wine-pairing
  schemas/
    wine_pairing.py              # Modèles Pydantic request/response
  services/
    supabase_storage.py          # Signed URL Supabase
    vision.py                    # Appel modèle vision GitHub Models
requirements.txt
.env                             # Variables d'environnement (gitignored)
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
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
SUPABASE_BUCKET_NAME=your_bucket_name
VISION_MODEL=openai/gpt-4o-mini
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

### `POST /api/wine-pairing`

Analyse une photo de plat et recommande des styles de vins.

Requête :

```json
{
  "file_path": "dishes/photo_plat.jpg",
  "user_note": "C'est un plat épicé"
}
```

Réponse :

```json
{
  "chat_response": "Ah, un excellent plat ! Je vois du poulet tikka masala avec sa sauce onctueuse et épices. Voici mes suggestions : 1) **Gewurztraminer sec d'Alsace** - ses arômes floraux et épicés complètent parfaitement le plat. Bon appétit !",
  "structured_data": {
    "dish_name": "Poulet tikka masala",
    "ingredients_detected": ["poulet", "sauce tomate", "épices", "riz"],
    "flavor_profile": {
      "richness": 3,
      "acidity": 2,
      "sweetness": 1,
      "spice": 4
    },
    "wine_pairings": [
      {
        "style": "Gewurztraminer sec d'Alsace",
        "color": "blanc",
        "reason": "Les arômes floraux et épicés du Gewurztraminer complètent les épices du plat."
      }
    ],
    "confidence": 0.85
  }
}
```

## Déploiement VM

```bash
git clone <repo>
cp .env.example .env   # remplir toutes les variables
docker compose up -d
```
