import json
import os
import random

from .config import DOSSIER_SAVES, LIGNES, COLONNES, VIDE


def verifier_dossier_saves():
    if not os.path.exists(DOSSIER_SAVES):
        os.mkdir(DOSSIER_SAVES)


def generer_index_partie():
    """Génère un index unique garanti."""
    verifier_dossier_saves()
    while True:
        idx = random.randint(1000, 9999)
        if not os.path.exists(f"{DOSSIER_SAVES}/partie_{idx}.json"):
            return idx


def sauvegarder_partie(index, nom, plateau, joueur, historique, terminee):
    verifier_dossier_saves()
    data = {
        "index": index,
        "nom": nom,
        "plateau": plateau,
        "joueur": joueur,
        "historique": historique,
        "terminee": terminee,
    }
    with open(f"{DOSSIER_SAVES}/partie_{index}.json", "w") as f:
        json.dump(data, f, indent=4)


def lister_sauvegardes():
    """Retourne les sauvegardes triées par index croissant."""
    verifier_dossier_saves()
    parties = []

    for f in os.listdir(DOSSIER_SAVES):
        if f.startswith("partie_") and f.endswith(".json"):
            try:
                with open(f"{DOSSIER_SAVES}/{f}") as file:
                    data = json.load(file)
                    parties.append(data)
            except Exception:
                continue  # fichier corrompu → ignoré

    # Tri par index
    parties.sort(key=lambda p: p.get("index", 0))
    return parties


def charger_partie_par_index(index):
    try:
        with open(f"{DOSSIER_SAVES}/partie_{index}.json") as f:
            data = json.load(f)

        # Validation minimale
        if "plateau" not in data or "historique" not in data:
            return None

        return data

    except Exception:
        return None


def annuler_dernier_coup(plateau, hist):
    """Annule le dernier coup en retirant le pion le plus bas de la colonne."""
    if not hist:
        return

    col = hist.pop()["colonne"]

    # On part du bas pour trouver le dernier pion joué
    for l in range(LIGNES - 1, -1, -1):
        if plateau[l][col] != VIDE:
            plateau[l][col] = VIDE
            break


