from .config import LIGNES, COLONNES, JOUEUR_DEPART
from .modele import (
    creer_plateau,
    afficher_plateau_console,
    changer_joueur,
    coup_valide,
    jouer_coup,
    plateau_plein,
    verifier_victoire,
)
from .ia import coup_aleatoire, coup_minimax, coup_bga
from .sauvegarde import (
    generer_index_partie,
    sauvegarder_partie,
    lister_sauvegardes,
    charger_partie_par_index,
    annuler_dernier_coup,
)
from core.database import db_connexion, db_ajouter_coup, db_creer_partie, db_terminer_partie


def partie_console(mode, profondeur=0, reprise=None):
    # Connexion PostgreSQL (nécessaire pour IA_BGA + enregistrement)
    conn_pg = db_connexion()

    if reprise:
        plateau = reprise["plateau"]
        joueur = reprise["joueur"]
        historique = reprise["historique"]
        index_partie = reprise["index"]
        nom = reprise["nom"]
        id_partie_pg = None  # On ne relie pas une reprise à PostgreSQL
    else:
        plateau = creer_plateau()
        joueur = JOUEUR_DEPART
        historique = []
        index_partie = generer_index_partie()
        nom = input("Nom de la partie : ")

        # Création dans PostgreSQL
        id_partie_pg = db_creer_partie(
            conn_pg,
            nom,
            nb_lignes=LIGNES,
            nb_colonnes=COLONNES,
            confiance=1
        )

    # Définition des types
    types = {
        "H_H": {"R": "HUMAIN", "J": "HUMAIN"},
        "H_IA_ALEA": {"R": "HUMAIN", "J": "IA_ALEA"},
        "H_IA_MINIMAX": {"R": "HUMAIN", "J": "IA_MINIMAX"},
        "H_IA_BGA": {"R": "HUMAIN", "J": "IA_BGA"},
        "IA_IA_ALEA": {"R": "IA_ALEA", "J": "IA_ALEA"},
        "IA_IA_MINIMAX": {"R": "IA_MINIMAX", "J": "IA_MINIMAX"},
        "IA_IA_BGA": {"R": "IA_BGA", "J": "IA_BGA"},
    }.get(mode, {"R": "HUMAIN", "J": "HUMAIN"})

    # Boucle de jeu
    while True:
        afficher_plateau_console(plateau)
        print("Joueur :", joueur)
        type_joueur = types[joueur]

        # HUMAIN
        if type_joueur == "HUMAIN":
            try:
                col = int(input("Colonne | -1 annuler | -2 sauvegarder : "))
            except Exception:
                continue

        # IA ALEATOIRE
        elif type_joueur == "IA_ALEA":
            import time
            time.sleep(0.3)
            col = coup_aleatoire(plateau)
            print(f"IA aléatoire ({joueur}) joue {col}")

        # IA MINIMAX
        elif type_joueur == "IA_MINIMAX":
            col, scores = coup_minimax(plateau, joueur, profondeur, afficher_console=True)
            print(f"IA MiniMax ({joueur}) joue {col}")

        # IA BGA
        elif type_joueur == "IA_BGA":
            col = coup_bga(plateau, [h["colonne"] for h in historique], conn_pg, joueur)
            print(f"IA BGA ({joueur}) joue {col}")

        # Gestion commandes humaines
        if type_joueur == "HUMAIN":
            if col == -1:
                # Undo cohérent avec le GUI : annule IA + humain
                annuler_dernier_coup(plateau, historique)
                annuler_dernier_coup(plateau, historique)
                continue

            if col == -2:
                sauvegarder_partie(index_partie, nom, plateau, joueur, historique, False)
                print("Partie sauvegardée !")
                conn_pg.close()
                return

        # Vérification coup valide
        if col is None or not coup_valide(plateau, col):
            print("Coup invalide.")
            continue

        # Jouer le coup
        jouer_coup(plateau, col, joueur)
        historique.append({"joueur": joueur, "colonne": col})

        # Enregistrer dans PostgreSQL
        if id_partie_pg is not None:
            numero = len(historique)
            db_ajouter_coup(conn_pg, id_partie_pg, numero, joueur, col)

        # Victoire ?
        win = verifier_victoire(plateau, joueur)
        if win:
            afficher_plateau_console(plateau)
            print("Victoire :", joueur)

            sauvegarder_partie(index_partie, nom, plateau, joueur, historique, True)

            if id_partie_pg is not None:
                db_terminer_partie(conn_pg, id_partie_pg, joueur)

            conn_pg.close()
            return

        # Match nul ?
        if plateau_plein(plateau):
            print("Match nul.")
            sauvegarder_partie(index_partie, nom, plateau, joueur, historique, True)

            if id_partie_pg is not None:
                db_terminer_partie(conn_pg, id_partie_pg, None)

            conn_pg.close()
            return

        joueur = changer_joueur(joueur)


def main_console():
    print("\n=== PUISSANCE 4 (CONSOLE) ===")
    print("1 Humain vs Humain")
    print("2 Humain vs IA aléatoire")
    print("3 Humain vs IA MiniMax")
    print("4 IA vs IA aléatoire")
    print("5 IA vs IA MiniMax")
    print("6 Humain vs IA BGA")
    print("7 IA vs IA BGA")
    print("8 Reprendre partie")
    print("P Paramétrage")

    choix = input("Choix : ").upper()

    if choix == "P":
        parametrage_console()
        return

    profondeur = 0
    if choix in ["3", "5"]:
        try:
            profondeur = int(input("Profondeur MiniMax : "))
        except Exception:
            profondeur = 2

    if choix == "8":
        parties = lister_sauvegardes()
        if not parties:
            print("Aucune sauvegarde.")
            return
        print("Parties disponibles :")
        for p in parties:
            term = "terminée" if p["terminee"] else "en cours"
            print(f"{p['index']} - {p['nom']} ({term})")
        try:
            idx = int(input("Index à reprendre : "))
        except Exception:
            return
        data = charger_partie_par_index(idx)
        if not data or data["terminee"]:
            print("Index invalide ou partie terminée.")
            return
        partie_console("H_H", reprise=data)
        return

    modes = {
        "1": "H_H",
        "2": "H_IA_ALEA",
        "3": "H_IA_MINIMAX",
        "4": "IA_IA_ALEA",
        "5": "IA_IA_MINIMAX",
        "6": "H_IA_BGA",
        "7": "IA_IA_BGA",
    }

    if choix in modes:
        partie_console(modes[choix], profondeur)



