import json
import os

# Symboles du plateau
VIDE = "."
ROUGE = "R"
JAUNE = "J"

# Fichiers
DOSSIER_SAVES = "saves"
CONFIG_FILE = "config.json"

# Valeurs par défaut
CONFIG_DEFAUT = {
    "lignes": 9,
    "colonnes": 9,
    "joueur_depart": ROUGE
}


def charger_configuration():
    """Charge la configuration depuis config.json, avec fallback sécurisé."""
    if not os.path.exists(CONFIG_FILE):
        sauvegarder_configuration(
            CONFIG_DEFAUT["lignes"],
            CONFIG_DEFAUT["colonnes"],
            CONFIG_DEFAUT["joueur_depart"]
        )
        return CONFIG_DEFAUT["lignes"], CONFIG_DEFAUT["colonnes"], CONFIG_DEFAUT["joueur_depart"]

    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)

        # Validation minimale
        lignes = cfg.get("lignes", CONFIG_DEFAUT["lignes"])
        colonnes = cfg.get("colonnes", CONFIG_DEFAUT["colonnes"])
        joueur = cfg.get("joueur_depart", CONFIG_DEFAUT["joueur_depart"])

        # Sécurité : valeurs invalides → fallback
        if not (4 <= lignes <= 12):
            lignes = CONFIG_DEFAUT["lignes"]
        if not (4 <= colonnes <= 12):
            colonnes = CONFIG_DEFAUT["colonnes"]
        if joueur not in [ROUGE, JAUNE]:
            joueur = CONFIG_DEFAUT["joueur_depart"]

        return lignes, colonnes, joueur

    except Exception:
        # Fichier corrompu → reset
        sauvegarder_configuration(
            CONFIG_DEFAUT["lignes"],
            CONFIG_DEFAUT["colonnes"],
            CONFIG_DEFAUT["joueur_depart"]
        )
        return CONFIG_DEFAUT["lignes"], CONFIG_DEFAUT["colonnes"], CONFIG_DEFAUT["joueur_depart"]


def sauvegarder_configuration(lignes, colonnes, joueur):
    with open(CONFIG_FILE, "w") as f:
        json.dump(
            {"lignes": lignes, "colonnes": colonnes, "joueur_depart": joueur},
            f,
            indent=4,
        )


def recharger_config():
    """Permet au GUI de recharger la config sans relancer l'app."""
    global LIGNES, COLONNES, JOUEUR_DEPART
    LIGNES, COLONNES, JOUEUR_DEPART = charger_configuration()


# Chargement initial
LIGNES, COLONNES, JOUEUR_DEPART = charger_configuration()








