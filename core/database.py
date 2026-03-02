import os
import psycopg2


def db_connexion():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)

    return psycopg2.connect(
        dbname="connect4_db",
        user="connect4_user",
        password="connect4",
        host="127.0.0.1",
        port="5432",
    )


def safe_query(conn, query, params=None, fetch=False):
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
        return cur.fetchall() if fetch else None
    finally:
        if cur is not None:
            cur.close()


def db_creer_partie(conn, nom, nb_lignes=9, nb_colonnes=9, confiance=1):
    """
    Crée une partie EN_COURS.
    ⚠️ Dans la nouvelle logique, on appelle cette fonction uniquement au 1er vrai coup
    (pour éviter les parties à 0 coup).
    """
    rows = safe_query(
        conn,
        """
        INSERT INTO parties (nom, statut, nb_lignes, nb_colonnes, confiance)
        VALUES (%s, 'EN_COURS', %s, %s, %s)
        RETURNING id_partie;
        """,
        (nom, nb_lignes, nb_colonnes, confiance),
        fetch=True,
    )
    return rows[0][0] if rows else None


def db_ajouter_coup(conn, id_partie, numero, joueur, colonne):
    safe_query(
        conn,
        """
        INSERT INTO coups (id_partie, numero_coup, joueur, colonne)
        VALUES (%s, %s, %s, %s);
        """,
        (id_partie, numero, joueur, colonne),
    )




