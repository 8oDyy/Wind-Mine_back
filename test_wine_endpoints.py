#!/usr/bin/env python3
"""
Script de test pour les endpoints wine-label-analysis et wine-label-add
"""

import json
import requests
import os
from uuid import uuid4

# Configuration
BASE_URL = "http://localhost:8000"
USER_ID = "2a0d4c0e-eebb-4456-a1e3-eea4f8203169"  # Ton user_id de test

def test_wine_label_analysis():
    """Test l'endpoint d'analyse d'étiquette"""
    print("\n🍷 Test 1: Analyse d'étiquette (wine-label-analysis)")
    print("=" * 60)
    
    # Test avec une image existante dans ton bucket
    payload = {
        "file_path": "test1.jpg",  # Change avec ton image
        "user_id": USER_ID,
        "stock": 1
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/wine-label-analysis",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Analyse réussie !")
            print(f"\n💬 Message conversationnel:")
            print(data.get("chat_response", "Pas de message"))
            
            print(f"\n📊 Proposition de vin existant:")
            existing = data.get("existing_proposal")
            if existing:
                print(f"   Nom: {existing.get('name')}")
                print(f"   Domaine: {existing.get('winery')}")
                print(f"   Année: {existing.get('year')}")
                print(f"   Type de correspondance: {existing.get('match_type')}")
                print(f"   Confiance: {existing.get('match_confidence', 0):.1%}")
            else:
                print("   Aucun vin existant trouvé")
            
            print(f"\n🆕 Proposition de nouveau vin:")
            new_proposal = data.get("new_proposal", {})
            print(f"   Nom: {new_proposal.get('name')}")
            print(f"   Domaine: {new_proposal.get('winery')}")
            print(f"   Année: {new_proposal.get('year')}")
            print(f"   Confiance IA: {new_proposal.get('confidence', 0):.1%}")
            
            # Retourner les données pour le test suivant
            return data
            
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion: {e}")
        return None

def test_wine_add_existing(wine_id):
    """Test l'ajout d'un vin existant"""
    print("\n🍷 Test 2: Ajout vin existant (wine-label-add)")
    print("=" * 60)
    
    payload = {
        "user_id": USER_ID,
        "wine_id": wine_id,
        "stock": 2,
        "custom_notes": "Test depuis script Python",
        "location": "Cave de test - Étagère A"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/wine-label-add",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Vin existant ajouté avec succès !")
            print(f"\n💬 Message: {data.get('message')}")
            print(f"🆕 Nouveau vin créé: {data.get('wine_added', False)}")
            
            cellar_wine = data.get("cellar_wine", {})
            print(f"\n📦 Entrée cave:")
            print(f"   ID: {cellar_wine.get('id')}")
            print(f"   Stock: {cellar_wine.get('stock')}")
            print(f"   Notes: {cellar_wine.get('notes')}")
            print(f"   Emplacement: {cellar_wine.get('location')}")
            
            wine_info = data.get("wine_info", {})
            print(f"\n🍷 Infos du vin:")
            print(f"   Nom: {wine_info.get('name')}")
            print(f"   Domaine: {wine_info.get('winery')}")
            print(f"   Année: {wine_info.get('year')}")
            
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion: {e}")

def test_wine_add_new():
    """Test la création et l'ajout d'un nouveau vin"""
    print("\n🍷 Test 3: Création nouveau vin (wine-label-add)")
    print("=" * 60)
    
    # Données d'un nouveau vin (à adapter selon tes besoins)
    wine_data = {
        "name": "Château Test Python",
        "winery": "Domaine Experimental",
        "year": 2023,
        "region": "Bordeaux",
        "country": "France",
        "variety": "Cabernet Sauvignon",
        "type": "Rouge",
        "alcohol_percentage": 13.5,
        "description": "Vin de test créé via l'API",
        "designation": "Grand Vin",
        "sub_region": "Médoc",
        "confidence": 0.95
    }
    
    payload = {
        "user_id": USER_ID,
        "wine_data": wine_data,
        "stock": 3,
        "custom_notes": "Nouveau vin créé via script de test",
        "location": "Cave expérimentale"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/wine-label-add",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Nouveau vin créé et ajouté !")
            print(f"\n💬 Message: {data.get('message')}")
            print(f"🆕 Nouveau vin créé: {data.get('wine_added', False)}")
            
            wine_info = data.get("wine_info", {})
            print(f"\n🍷 Nouveau vin créé:")
            print(f"   Nom: {wine_info.get('name')}")
            print(f"   Domaine: {wine_info.get('winery')}")
            print(f"   Année: {wine_info.get('year')}")
            print(f"   Région: {wine_info.get('region')}")
            
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion: {e}")

def check_server():
    """Vérifie que le serveur est démarré"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Serveur WineMind démarré et accessible")
            return True
        else:
            print(f"❌ Serveur répond avec code {response.status_code}")
            return False
    except requests.exceptions.RequestException:
        print("❌ Serveur inaccessible. Démarrer avec: docker compose up --build")
        return False

def main():
    """Fonction principale de test"""
    print("🍷 Script de test WineMind API")
    print("=" * 50)
    
    # Vérifier que le serveur est démarré
    if not check_server():
        return
    
    # Test 1: Analyse d'étiquette
    analysis_result = test_wine_label_analysis()
    
    if analysis_result:
        # Test 2: Ajouter le vin existant (si trouvé)
        existing_proposal = analysis_result.get("existing_proposal")
        if existing_proposal and existing_proposal.get("id"):
            print(f"\n🔄 Test avec le vin existant trouvé...")
            test_wine_add_existing(existing_proposal["id"])
        else:
            print("\n⚠️ Aucun vin existant à tester")
    
    # Test 3: Créer un nouveau vin
    print(f"\n🔄 Test création nouveau vin...")
    test_wine_add_new()
    
    print("\n🎉 Tests terminés !")
    print("\n💡 Prochaines étapes:")
    print("1. Vérifie ta cave dans l'interface WineMind")
    print("2. Adapte les noms de fichiers dans les tests")
    print("3. Teste avec tes vraies images d'étiquettes")

if __name__ == "__main__":
    main()
