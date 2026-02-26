import time
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import (
    db_connexion,
    db_get_last_random_index,
    db_creer_partie,
    db_ajouter_coup,
    db_terminer_partie
)

from core.modele import (
    creer_plateau,
    coup_valide,
    jouer_coup,
    changer_joueur,
    plateau_plein,
    verifier_victoire,
)

from core.ia import coup_aleatoire
from core.config import ROUGE, JAUNE


def jouer_partie_aleatoire(index):
    # Connexion unique pour toute la partie
    conn = db_connexion()

    plateau = creer_plateau()
    joueur = ROUGE
    numero_coup = 1

    # Créer la partie dans PostgreSQL
    id_partie = db_creer_partie(
        conn,
        nom=f"AUTO_RANDOM_{index:03d}",
        nb_lignes=9,
        nb_colonnes=9,
        confiance=1
    )

    sequence_list = []

    while True:
        # Choisir un coup aléatoire valide
        col = coup_aleatoire(plateau)

        # Jouer le coup
        jouer_coup(plateau, col, joueur)

        # Enregistrer en base
        db_ajouter_coup(conn, id_partie, numero_coup, joueur, col)
        sequence_list.append(col)
        numero_coup += 1

        # Victoire ?
        if verifier_victoire(plateau, joueur):
            db_terminer_partie(conn, id_partie, joueur)
            break

        # Match nul ?
        if plateau_plein(plateau):
            db_terminer_partie(conn, id_partie, None)
            break

        # Changer joueur
        joueur = changer_joueur(joueur)

    # Enregistrer la séquence dans la table parties
    sequence_str = ",".join(str(c) for c in sequence_list)

    cur = conn.cursor()
    cur.execute("""
        UPDATE parties
        SET sequence = %s
        WHERE id_partie = %s;
    """, (sequence_str, id_partie))
    conn.commit()
    cur.close()
    conn.close()

    return joueur


def generer_plusieurs_parties(n):
    conn = db_connexion()
    start = db_get_last_random_index(conn)
    conn.close()
    
    for i in range(1, n + 1):
        index = start + i
        gagnant = jouer_partie_aleatoire(index)
        print(f"Partie {i}/{n} terminée – gagnant : {gagnant}")
        time.sleep(0.1)


if __name__ == "__main__":
    generer_plusieurs_parties(50)

