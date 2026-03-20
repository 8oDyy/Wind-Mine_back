#!/usr/bin/env python3
"""
Script de test pour les endpoints wine-label-analysis et wine-label-add
"""

import json
import requests
import os
from uuid import uuid4

# Configuration
BASE_URL = "http://10.74.16.212:8000"
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

def interactive_choice_and_add(analysis_result):
    """Demande le choix utilisateur et ajoute le vin sélectionné"""
    print("\n🤔 Quel vin souhaitez-vous ajouter à votre cave ?")
    print("=" * 60)
    
    existing = analysis_result.get("existing_proposal")
    new_proposal = analysis_result.get("new_proposal")
    
    # Afficher les options
    print("\n**Option 1 - Vin existant:**")
    if existing:
        print(f"   🍷 {existing.get('name')} ({existing.get('year', 'N/A')})")
        print(f"      Domaine: {existing.get('winery', 'N/A')}")
        print(f"      Région: {existing.get('region', 'N/A')}")
        print(f"      Confiance: {existing.get('match_confidence', 0):.1%}")
        print(f"      Type: {existing.get('match_type', 'N/A')}")
    else:
        print("   ❌ Aucun vin existant trouvé")
    
    print(f"\n**Option 2 - Nouveau vin:**")
    print(f"   🍷 {new_proposal.get('name')} ({new_proposal.get('year', 'N/A')})")
    print(f"      Domaine: {new_proposal.get('winery', 'N/A')}")
    print(f"      Région: {new_proposal.get('region', 'N/A')}")
    print(f"      Confiance IA: {new_proposal.get('confidence', 0):.1%}")
    
    # Demander le choix
    while True:
        choice = input("\nVotre choix (1 ou 2): ").strip()
        
        if choice == "1" and existing:
            print(f"\n✅ Vous avez choisi: {existing.get('name')}")
            add_existing_wine(existing["id"])
            break
        elif choice == "1" and not existing:
            print("❌ Option 1 non disponible (aucun vin existant)")
        elif choice == "2":
            print(f"\n✅ Vous avez choisi: {new_proposal.get('name')}")
            add_new_wine(new_proposal)
            break
        else:
            print("❌ Choix invalide. Entrez 1 ou 2.")

def add_existing_wine(wine_id):
    """Ajoute un vin existant à la cave"""
    print("\n🍷 Ajout du vin existant à votre cave...")
    print("=" * 60)
    
    payload = {
        "user_id": USER_ID,
        "wine_id": wine_id,
        "stock": 2,
        "custom_notes": "Test depuis script Python interactif",
        "location": "Cave de test - Étagère A"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/wine-label-add",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Vin existant ajouté avec succès !")
            print(f"💬 {data.get('message')}")
            
            wine_info = data.get("wine_info", {})
            print(f"\n🍷 Ajouté à votre cave:")
            print(f"   {wine_info.get('name')} ({wine_info.get('year')})")
            print(f"   {wine_info.get('winery')}")
            
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion: {e}")

def add_new_wine(wine_data):
    """Crée et ajoute un nouveau vin"""
    print("\n🍷 Création et ajout du nouveau vin...")
    print("=" * 60)
    
    payload = {
        "user_id": USER_ID,
        "wine_data": wine_data,
        "stock": 2,
        "custom_notes": "Nouveau vin créé via script interactif",
        "location": "Cave de test - Nouveaux vins"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/wine-label-add",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Nouveau vin créé et ajouté !")
            print(f"💬 {data.get('message')}")
            
            wine_info = data.get("wine_info", {})
            print(f"\n🍷 Nouveau vin dans votre cave:")
            print(f"   {wine_info.get('name')} ({wine_info.get('year')})")
            print(f"   {wine_info.get('winery')}")
            print(f"   {wine_info.get('region')}")
            
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
    """Fonction principale de test interactif"""
    print("🍷 Script de test WineMind API - Mode Interactif")
    print("=" * 60)
    
    # Vérifier que le serveur est démarré
    if not check_server():
        return
    
    # Étape 1: Analyse d'étiquette
    print("\n📸 Étape 1: Analyse de l'étiquette")
    analysis_result = test_wine_label_analysis()
    
    if analysis_result:
        # Étape 2: Choix interactif
        print("\n🤔 Étape 2: Votre choix")
        interactive_choice_and_add(analysis_result)
    else:
        print("\n❌ Impossible d'analyser l'étiquette. Vérifie:")
        print("   - L'image existe dans le bucket Supabase")
        print("   - Le nom du fichier est correct")
        print("   - Le serveur fonctionne correctement")
    
    print("\n🎉 Test terminé !")
    print("\n💡 Pour tester à nouveau:")
    print("   1. Change le nom de l'image dans le script")
    print("   2. Relance: python test_wine_endpoints.py")
    print("   3. Vérifie ta cave dans WineMind")

if __name__ == "__main__":
    main()
