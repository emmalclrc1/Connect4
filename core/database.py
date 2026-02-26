import psycopg2

# ------------------------------------------------------------
# Connexion à la base PostgreSQL
# ------------------------------------------------------------

def db_connexion():
    """Crée une connexion PostgreSQL."""
    return psycopg2.connect(
        dbname="connect4_db",
        user="connect4_user",
        password="connect4",
        host="127.0.0.1",
        port="5432"
    )


# ------------------------------------------------------------
# Fonctions utilitaires
# ------------------------------------------------------------

def safe_query(conn, query, params=None, fetch=False):
    """
    Exécute une requête SQL en gérant commit/rollback proprement.
    fetch=True → retourne les résultats.
    """
    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
        if fetch:
            rows = cur.fetchall()
        else:
            rows = None
        conn.commit()
        cur.close()
        return rows
    except Exception as e:
        conn.rollback()
        print("Erreur SQL :", e)
        return None


# ------------------------------------------------------------
# Création d'une partie
# ------------------------------------------------------------

def db_creer_partie(conn, nom, nb_lignes=9, nb_colonnes=9, confiance=1):
    rows = safe_query(
        conn,
        """
        INSERT INTO parties (nom, statut, nb_lignes, nb_colonnes, confiance)
        VALUES (%s, 'EN_COURS', %s, %s, %s)
        RETURNING id_partie;
        """,
        (nom, nb_lignes, nb_colonnes, confiance),
        fetch=True
    )
    return rows[0][0] if rows else None


# ------------------------------------------------------------
# Ajout d'un coup
# ------------------------------------------------------------

def db_ajouter_coup(conn, id_partie, numero, joueur, colonne):
    safe_query(
        conn,
        """
        INSERT INTO coups (id_partie, numero_coup, joueur, colonne)
        VALUES (%s, %s, %s, %s);
        """,
        (id_partie, numero, joueur, colonne)
    )


# ------------------------------------------------------------
# Terminer une partie
# ------------------------------------------------------------

def db_terminer_partie(conn, id_partie, gagnant):
    safe_query(
        conn,
        """
        UPDATE parties
        SET statut = 'TERMINE', gagnant = %s
        WHERE id_partie = %s;
        """,
        (gagnant, id_partie)
    )


# ------------------------------------------------------------
# Récupérer le dernier index AUTO_RANDOM
# ------------------------------------------------------------

def db_get_last_random_index(conn):
    rows = safe_query(
        conn,
        """
        SELECT nom FROM parties
        WHERE nom LIKE 'AUTO_RANDOM_%'
        ORDER BY id_partie DESC
        LIMIT 1;
        """,
        fetch=True
    )

    if not rows:
        return 0

    nom = rows[0][0]
    try:
        return int(nom.split("_")[-1])
    except:
        return 0

# ------------------------------------------------------------
# Supprimer dernier coup
# ------------------------------------------------------------

def db_supprimer_dernier_coup(conn, id_partie):
    """
    Supprime le dernier coup enregistré pour cette partie.
    Utilisé pour synchroniser l'undo GUI <-> PostgreSQL.
    """
    try:
        cur = conn.cursor()

        # Récupérer le dernier coup
        cur.execute("""
            SELECT numero_coup
            FROM coups
            WHERE id_partie = %s
            ORDER BY numero_coup DESC
            LIMIT 1;
        """, (id_partie,))
        row = cur.fetchone()

        if row is None:
            cur.close()
            return

        dernier_numero = row[0]

        # Supprimer ce coup
        cur.execute("""
            DELETE FROM coups
            WHERE id_partie = %s AND numero_coup = %s;
        """, (id_partie, dernier_numero))

        conn.commit()
        cur.close()

    except Exception as e:
        conn.rollback()
        print("Erreur db_supprimer_dernier_coup :", e)








