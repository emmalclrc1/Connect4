# web/app.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from core.database import db_connexion, db_creer_partie, db_ajouter_coup
from core.ia import coup_aleatoire, coup_minimax, coup_bga
from core.config import ROUGE, JAUNE
from core.modele import (
    creer_plateau,
    coup_valide,
    jouer_coup,
    changer_joueur,
    verifier_victoire,
    plateau_plein,
)

app = FastAPI()

# Static + page HTML
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent 

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Connexion PostgreSQL (local)
CONN_PG = db_connexion()

# Stockage temporaire en mémoire 
games = {}


@app.get("/")
def root():
    return {"message": "Connect4 API running"}


@app.get("/play", response_class=HTMLResponse)
def play_page():
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.post("/new-game")
def new_game(mode: str = "hvh"):
    """
    mode:
      - hvh     : humain vs humain
      - random  : humain vs IA aléatoire (IA = JAUNE)
      - minimax : humain vs IA minimax (IA = JAUNE)
      - bga     : humain vs IA BGA (IA = JAUNE, utilise PostgreSQL)
    """
    plateau = creer_plateau()
    game_id = len(games) + 1
    
    # creer la partie en base (WEB)
    id_partie_pg = db_creer_partie(CONN_PG, f"WEB_{game_id}")

    games[game_id] = {
        "plateau": plateau,
        "joueur": ROUGE,      # ROUGE commence
        "winner": None,
        "mode": mode,
        "coups": [],          # historique des colonnes jouées
        "ia_couleur": JAUNE,  # IA joue JAUNE dans les modes IA
        "minimax_depth": 4,
        "id_partie_pg": id_partie_pg
    }

    return {"game_id": game_id, "plateau": plateau, "mode": mode}


def choisir_coup_ia(game):
    plateau = game["plateau"]
    ia_couleur = game["ia_couleur"]
    mode = game["mode"]

    if mode == "random":
        return coup_aleatoire(plateau)

    if mode == "minimax":
        col, _ = coup_minimax(
            plateau, ia_couleur, profondeur=game.get("minimax_depth", 2)
        )
        return col

    if mode == "bga":
        return coup_bga(plateau, game["coups"], CONN_PG, ia_couleur)

    return None


@app.get("/game/{game_id}")
def get_game(game_id: int):
    """Pratique pour debug/refresh côté frontend."""
    game = games.get(game_id)
    if not game:
        return {"error": "Game not found"}
    return {
        "plateau": game["plateau"],
        "joueur": game["joueur"],
        "mode": game["mode"],
        "winner": game["winner"],
        "coups": game["coups"],
    }


@app.post("/move/{game_id}")
def move(game_id: int, col: int):
    game = games.get(game_id)
    if not game:
        return {"error": "Game not found"}

    plateau = game["plateau"]
    joueur = game["joueur"]

    if game.get("winner"):
        return {"error": "Game finished", "plateau": plateau}

    if not coup_valide(plateau, col):
        return {"error": "Invalid move", "plateau": plateau}

    # -------------------------
    # Coup du joueur courant
    # -------------------------
    jouer_coup(plateau, col, joueur)
    game["coups"].append(col)
    
    db_ajouter_coup(
        CONN_PG,
        game["id_partie_pg"],
        len(game["coups"]),
        joueur,
        col
    )

    win_pos = verifier_victoire(plateau, joueur)
    if win_pos:
        game["winner"] = joueur
        return{"plateau": plateau, "winner": joueur, "win_pos": win_pos}

    if plateau_plein(plateau):
        return {"plateau": plateau, "draw": True}

    # Tour suivant
    game["joueur"] = changer_joueur(joueur)

    # -------------------------
    # Coup IA auto (si mode IA)
    # -------------------------
    mode = game["mode"]
    ia_couleur = game["ia_couleur"]

    if mode in ("random", "minimax", "bga") and game["joueur"] == ia_couleur:
        try:
            col_ia = choisir_coup_ia(game)
        except Exception:
            # fallback au cas où la DB est down / erreur SQL
            col_ia, _ = coup_minimax(plateau, ia_couleur, profondeur=2)

        if col_ia is None or not coup_valide(plateau, col_ia):
            return {"error": "IA has no valid move", "plateau": plateau}

        jouer_coup(plateau, col_ia, ia_couleur)
        game["coups"].append(col_ia)
        
        db_ajouter_coup(
            CONN_PG,
            game["id_partie_pg"],
            len(game["coups"]),
            joueur,
            col
        ) 

        win_pos = verifier_victoire(plateau, ia_couleur)
        if win_pos:
            game["winner"] = ia_couleur
            return {"plateau": plateau, "winner": ia_couleur, "ia_move": col_ia, "win_pos": win_pos}

        if plateau_plein(plateau):
            return {"plateau": plateau, "draw": True, "ia_move": col_ia}

        game["joueur"] = changer_joueur(ia_couleur)
        return {"plateau": plateau, "next_player": game["joueur"], "ia_move": col_ia}

    # Mode hvh (ou tour humain suivant)
    return {"plateau": plateau, "next_player": game["joueur"]}
       
@app.get("/debug/db")
def debug_db():
    conn = db_connexion()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM parties;")
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {"count_parties": n}        

