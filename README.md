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

## 🍷 Analyse d'Étiquettes de Vin

### POST /api/wine-label-analysis

Analyse une étiquette de vin et retourne 2 propositions (vin existant + nouveau vin) sans rien ajouter à la base.

**Workflow :**
1. Analyse l'étiquette avec IA vision
2. Recherche intelligente dans la base (130k+ vins)
3. Retourne 2 options pour choix utilisateur
4. **Pas d'ajout automatique** à la cave

Requête :

```json
{
  "file_path": "wine-labels/chateau-margaux-2010.jpg",
  "user_id": "uuid-utilisateur",
  "stock": 1
}
```

Réponse :

```json
{
  "chat_response": "🎉 Vin identifié ! J'ai trouvé Château Margaux 2010 dans notre catalogue. Voici mes propositions :\n\n**Option 1 - Vin existant** : Château Margaux 2010\n- Domaine: Château Margaux\n- Confiance: 100%\n\n**Option 2 - Nouveau vin** : Château Margaux 2010\n- Domaine: Château Margaux\n- Confiance IA: 98%\n\nChoisissez l'option qui vous convient.",
  "existing_proposal": {
    "id": "uuid-vin-existant",
    "name": "Château Margaux",
    "winery": "Château Margaux",
    "year": 2010,
    "region": "Margaux",
    "country": "France",
    "match_type": "exact",
    "match_confidence": 1.0
  },
  "new_proposal": {
    "name": "Château Margaux",
    "winery": "Château Margaux", 
    "year": 2010,
    "region": "Margaux",
    "country": "France",
    "variety": "Cabernet Sauvignon",
    "type": "Rouge",
    "alcohol_percentage": 13.5,
    "description": "Grand vin rouge de Bordeaux",
    "designation": "Grand Cru Classé",
    "province": "Médoc",
    "price": 850.0,
    "points": 98,
    "body_level": 0.8,
    "tannin_level": 0.9,
    "fruit_level": 0.7,
    "food_pairings": ["Viande rouge", "Fromage", "Agneau"],
    "confidence": 0.98
  },
  "wine_analysis": {
    "name": "Château Margaux",
    "winery": "Château Margaux",
    "year": 2010,
    "confidence": 0.98
  }
}
```

### POST /api/wine-label-add

Ajoute effectivement un vin à la cave de l'utilisateur (soit existant, soit nouveau).

**Ajout vin existant :**

```json
{
  "user_id": "uuid-utilisateur",
  "wine_id": "uuid-vin-existant",
  "stock": 2,
  "custom_notes": "Bouteille pour anniversaire",
  "location": "Cave principale - Étagère A"
}
```

**Création nouveau vin :**

```json
{
  "user_id": "uuid-utilisateur",
  "wine_data": {
    "name": "Château Test",
    "winery": "Domaine Experimental",
    "year": 2023,
    "region": "Bordeaux",
    "country": "France",
    "variety": "Cabernet Sauvignon",
    "type": "Rouge",
    "alcohol_percentage": 13.5,
    "description": "Vin de test",
    "designation": "Grand Vin",
    "province": "Médoc",
    "price": 25.0,
    "points": 88,
    "body_level": 0.6,
    "tannin_level": 0.5,
    "fruit_level": 0.7,
    "food_pairings": ["Viande rouge", "Fromage"]
  },
  "stock": 1,
  "custom_notes": "Nouveau vin test",
  "location": "Cave test"
}
```

Réponse :

```json
{
  "success": true,
  "message": "Vin existant ajouté à votre cave avec succès !",
  "wine_added": false,
  "cellar_wine": {
    "id": "uuid-entrée-cave",
    "wine_id": "uuid-vin",
    "user_id": "uuid-utilisateur",
    "stock": 2,
    "notes": "Bouteille pour anniversaire",
    "location": "Cave principale - Étagère A",
    "created_at": "2026-03-19T15:30:00Z"
  },
  "wine_info": {
    "id": "uuid-vin",
    "name": "Château Margaux",
    "winery": "Château Margaux",
    "year": 2010,
    "region": "Margaux"
  }
}
```

## 🧪 Script de Test Interactif

Un script Python interactif est disponible pour tester les endpoints :

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le test interactif
python test_wine_endpoints.py
```

Le script :
1. ✅ Vérifie que le serveur est accessible
2. 📸 Analyse une étiquette 
3. 🤔 Demande le choix utilisateur (1 ou 2)
4. ➕ Ajoute le vin sélectionné à la cave

**Personnalisation :**
- Change `USER_ID` dans le script
- Change `"file_path": "test1.jpg"` avec ton image
- Le script affiche les détails de chaque proposition

## 🏗️ Architecture des Endpoints

### Wine Label Analysis (`/api/wine-label-analysis`)
- **Input** : Image + user_id
- **Process** : IA vision → Recherche intelligente → 2 propositions
- **Output** : Propositions sans modification BDD
- **Usage** : Étape 1 du workflow utilisateur

### Wine Label Add (`/api/wine-label-add`)  
- **Input** : Choix utilisateur (wine_id OU wine_data)
- **Process** : Validation → Création si besoin → Ajout cave
- **Output** : Confirmation avec détails
- **Usage** : Étape 2 du workflow utilisateur

### Recherche Intelligente
5 niveaux de correspondance optimisés pour 130k+ vins :
1. **Exact** : Nom identique (100% confiance)
2. **Similar** : Même nom + domaine (90% confiance)  
3. **Partial** : Nom partiel + même domaine (80% confiance)
4. **Regional** : Même domaine + région (70% confiance)
5. **None** : Vraiment nouveau vin

### Données Enrichies
L'IA remplit automatiquement TOUS les champs de la table `wines` :
- **Basiques** : name, winery, year, region, country, variety, type
- **Descriptives** : description, designation, province
- **Numériques** : price, points, alcohol_percentage
- **Sensorielles** : body_level, tannin_level, fruit_level (0.0-1.0)
- **Pratiques** : food_pairings (array)

## Déploiement VM

```bash
git clone <repo>
cp .env.example .env   # remplir toutes les variables
docker compose up -d
```
