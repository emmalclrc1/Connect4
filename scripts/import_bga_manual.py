import sys
import os
import re

# Ajoute la racine du projet au PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import (
    db_connexion,
    db_creer_partie,
    db_ajouter_coup,
    db_terminer_partie
)

# Dossier contenant les fichiers texte
DOSSIER_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# REGEX POUR DETECTER LES COUPS
regex_coup = re.compile(r"place un pion dans la colonne (\d+)")


def importer_fichier(chemin_fichier):
    # Nom propre (sans extension)
    nom_partie = os.path.splitext(os.path.basename(chemin_fichier))[0]

    # Connexion unique
    conn = db_connexion()

    # Créer la partie dans la base (9x9 + confiance=4 car BGA)
    id_partie = db_creer_partie(
        conn,
        nom_partie,
        nb_lignes=9,
        nb_colonnes=9,
        confiance=4
    )

    with open(chemin_fichier, "r", encoding="utf-8") as f:
        lignes = f.readlines()

    num_coup = 0
    joueur_actuel = None
    gagnant = None
    sequence_list = []

    for ligne in lignes:
        ligne = ligne.strip()

        # Détecter le joueur
        if "kentino place" in ligne:
            joueur_actuel = "R"
        elif "place un pion" in ligne:
            joueur_actuel = "J"

        # Détecter la colonne
        match = regex_coup.search(ligne)
        if match:
            colonne = int(match.group(1)) - 1
            num_coup += 1

            # Ajouter le coup dans la base
            db_ajouter_coup(conn, id_partie, num_coup, joueur_actuel, colonne)

            # Ajouter à la séquence
            sequence_list.append(colonne)

        # Détecter le gagnant
        if "a aligné quatre pions" in ligne:
            gagnant = "R" if "kentino" in ligne else "J"

        # Fin de partie
        if "Fin de la partie" in ligne:
            break

    # Construire la séquence complète
    sequence_str = ",".join(str(col) for col in sequence_list)

    # Mettre à jour la séquence dans la table parties
    cur = conn.cursor()
    cur.execute("""
        UPDATE parties
        SET sequence = %s
        WHERE id_partie = %s;
    """, (sequence_str, id_partie))
    conn.commit()
    cur.close()

    # Terminer la partie dans la base
    db_terminer_partie(conn, id_partie, gagnant)

    conn.close()

    print(f"✔ Partie importée : {nom_partie} → id={id_partie}, coups={num_coup}, sequence={sequence_str}")


def importer_toutes_les_parties():
    print("📥 Import des fichiers .txt dans /data ...")

    fichiers = [f for f in os.listdir(DOSSIER_DATA) if f.endswith(".txt")]

    if not fichiers:
        print("⚠ Aucun fichier .txt trouvé dans /data")
        return

    for fichier in fichiers:
        chemin = os.path.join(DOSSIER_DATA, fichier)
        importer_fichier(chemin)

    print("\n🎉 Import terminé pour tous les fichiers !")


if __name__ == "__main__":
    importer_toutes_les_parties()





