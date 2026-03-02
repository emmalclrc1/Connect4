from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from core.config import ROUGE, JAUNE
from core.database import db_connexion, safe_query, db_creer_partie, db_ajouter_coup
from core.modele import (
    creer_plateau,
    coup_valide,
    jouer_coup,
    changer_joueur,
    verifier_victoire,
    plateau_plein,
)
from core.ia import (
    coup_aleatoire,
    coup_minimax,
    coup_bga,
    bga_poids,
    analyse_position,
    principal_variation_from_board,
)

ModeInternal = Literal["hvh", "random", "minimax", "bga", "eve"]
ModeUI = Literal["pvp", "vsai", "iaia"]
AIType = Literal["random", "minimax", "bga"]

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

games: Dict[str, dict] = {}
locks: Dict[str, asyncio.Lock] = {}


def get_lock(game_id: str) -> asyncio.Lock:
    if game_id not in locks:
        locks[game_id] = asyncio.Lock()
    return locks[game_id]


@contextmanager
def get_conn():
    conn = db_connexion()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -------------------------
# Pages
# -------------------------
@app.get("/play", response_class=HTMLResponse)
def play_page():
    return (BASE_DIR / "templates" / "play.html").read_text(encoding="utf-8")


@app.get("/history", response_class=HTMLResponse)
def history_page():
    return (BASE_DIR / "templates" / "history.html").read_text(encoding="utf-8")


@app.get("/bga", response_class=HTMLResponse)
def bga_page():
    return (BASE_DIR / "templates" / "bga.html").read_text(encoding="utf-8")


@app.get("/replay/{id_partie}", response_class=HTMLResponse)
def replay_page(id_partie: int):
    return (BASE_DIR / "templates" / "replay.html").read_text(encoding="utf-8")


@app.get("/about", response_class=HTMLResponse)
def about_page():
    return (BASE_DIR / "templates" / "about.html").read_text(encoding="utf-8")


@app.get("/")
def root():
    return {"message": "Connect4 API running"}


# -------------------------
# Helpers
# -------------------------
def choisir_coup_par_type(ai_type: AIType, plateau, coups, conn, joueur_ia: str, depth: int) -> Optional[int]:
    if ai_type == "random":
        return coup_aleatoire(plateau)
    if ai_type == "minimax":
        col, _ = coup_minimax(plateau, joueur_ia, profondeur=depth)
        return col
    if ai_type == "bga":
        return coup_bga(plateau, coups, conn, joueur_ia)
    return None


def sequence_str(coups) -> str:
    return ",".join(str(c) for c in coups)


def debug_bga_for(game: dict, joueur: str) -> dict:
    if game["ai_type"] != "bga":
        return {}
    with get_conn() as conn:
        weights, matches = bga_poids(game["plateau"], game["coups"], conn, joueur)
    return {"bga": {"weights": weights, "matches": matches}}


def conseil_humain(game: dict, joueur_humain: str) -> dict:
    """
    Donne le meilleur coup pour l'humain + une explication (minimax scores ou poids BGA)
    """
    plateau = game["plateau"]

    # Si l'humain joue contre BGA, on peut afficher les poids BGA "comme s'il était l'IA"
    if game["ai_type"] == "bga":
        with get_conn() as conn:
            w, matches = bga_poids(plateau, game["coups"], conn, joueur_humain)
        if w:
            best = max(w, key=w.get)
        else:
            best, _ = coup_minimax(plateau, joueur_humain, profondeur=2)
        return {"human_hint": {"type": "bga", "best_col": best, "weights": w, "matches": matches}}

    # Sinon minimax conseil
    best, scores, score_best, label = analyse_position(plateau, joueur_humain, profondeur=int(game.get("depth", 4)))
    return {"human_hint": {"type": "minimax", "best_col": best, "scores": scores, "label": label, "score": score_best}}


async def finir_partie(game: dict, gagnant: Optional[str], draw: bool):
    if game.get("finished"):
        return
    game["finished"] = True
    game["winner"] = gagnant
    seq = sequence_str(game["coups"])

    with get_conn() as conn:
        safe_query(
            conn,
            """
            UPDATE parties
            SET statut='TERMINE', gagnant=%s, sequence=%s
            WHERE id_partie=%s;
            """,
            (None if draw else gagnant, seq, game["id_partie_pg"]),
        )


# -------------------------
# API: Stats / Historique / Replay
# -------------------------
@app.get("/api/stats")
def api_stats():
    with get_conn() as conn:
        rows = safe_query(
            conn,
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN gagnant='R' THEN 1 ELSE 0 END) AS rouge,
                SUM(CASE WHEN gagnant='J' THEN 1 ELSE 0 END) AS jaune,
                SUM(CASE WHEN gagnant IS NULL AND statut='TERMINE' THEN 1 ELSE 0 END) AS nuls
            FROM parties;
            """,
            fetch=True,
        )
        (total, rouge, jaune, nuls) = rows[0] if rows else (0, 0, 0, 0)
        return {"ok": True, "total": total or 0, "rouge": rouge or 0, "jaune": jaune or 0, "nuls": nuls or 0}


@app.get("/api/history")
def api_history(limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0)):
    with get_conn() as conn:
        rows = safe_query(
            conn,
            """
            SELECT
                p.id_partie,
                p.nom,
                p.statut,
                p.gagnant,
                p.sequence,
                p.created_at,
                COALESCE(c.nb_coups, 0) AS nb_coups
            FROM parties p
            LEFT JOIN (
                SELECT id_partie, COUNT(*) AS nb_coups
                FROM coups
                GROUP BY id_partie
            ) c ON c.id_partie = p.id_partie
            ORDER BY p.id_partie DESC
            LIMIT %s OFFSET %s;
            """,
            (limit, offset),
            fetch=True,
        )

        items = []
        for (idp, nom, statut, gagnant, sequence, created_at, nb_coups) in rows or []:
            items.append(
                {
                    "id_partie": idp,
                    "nom": nom,
                    "statut": statut,
                    "gagnant": gagnant,
                    "sequence": sequence or "",
                    "created_at": created_at.isoformat() if created_at else None,
                    "nb_coups": nb_coups,
                }
            )

        return {"ok": True, "items": items}


@app.get("/api/replay/{id_partie}")
def api_replay(id_partie: int):
    with get_conn() as conn:
        rows = safe_query(
            conn,
            """
            SELECT id_partie, nom, statut, gagnant, sequence, created_at, nb_lignes, nb_colonnes
            FROM parties
            WHERE id_partie = %s;
            """,
            (id_partie,),
            fetch=True,
        )
        if not rows:
            return {"ok": False, "error": "Partie introuvable"}

        p = rows[0]
        coups = safe_query(
            conn,
            """
            SELECT numero_coup, joueur, colonne
            FROM coups
            WHERE id_partie = %s
            ORDER BY numero_coup ASC;
            """,
            (id_partie,),
            fetch=True,
        ) or []

        return {
            "ok": True,
            "partie": {
                "id_partie": p[0],
                "nom": p[1],
                "statut": p[2],
                "gagnant": p[3],
                "sequence": p[4] or "",
                "created_at": p[5].isoformat() if p[5] else None,
                "nb_lignes": p[6],
                "nb_colonnes": p[7],
            },
            "coups": [{"n": n, "joueur": j, "col": c} for (n, j, c) in coups],
        }


# -------------------------
# API: Analyse situation (pour la soutenance / image)
# -------------------------
@app.get("/api/analyze")
def api_analyze(
    sequence: str = Query("", description="ex: 3,3,4,2"),
    next_player: Literal["R", "J", "auto"] = "auto",
    depth: int = Query(6, ge=1, le=9),
):
    # reconstruire plateau depuis sequence
    plateau = creer_plateau()
    coups = []
    seq = sequence.strip()
    if seq:
        try:
            coups = [int(x) for x in seq.split(",") if x.strip() != ""]
        except Exception:
            return {"ok": False, "error": "Sequence invalide. Exemple: 3,3,4,2"}

        joueur = ROUGE
        for c in coups:
            if not coup_valide(plateau, c):
                return {"ok": False, "error": f"Coup invalide dans la sequence: {c}"}
            jouer_coup(plateau, c, joueur)
            if verifier_victoire(plateau, joueur):
                break
            joueur = changer_joueur(joueur)

    if next_player == "auto":
        joueur_a_jouer = ROUGE if (len(coups) % 2 == 0) else JAUNE
    else:
        joueur_a_jouer = next_player

    best, scores, score_best, label = analyse_position(plateau, joueur_a_jouer, profondeur=depth)
    pv = principal_variation_from_board(plateau, joueur_a_jouer, profondeur=depth, max_len=12)

    return {
        "ok": True,
        "plateau": plateau,
        "joueur_a_jouer": joueur_a_jouer,
        "best_col": best,
        "score_best": score_best,
        "label": label,
        "scores": scores,
        "pv": pv,
    }


# -------------------------
# Jeu
# -------------------------
@app.post("/new-game")
async def new_game(
    mode: ModeUI = "pvp",
    human_color: Literal["R", "J"] = "R",
    ai_type: AIType = "minimax",
    depth: int = Query(4, ge=1, le=9),
    delay_ms: int = Query(350, ge=0, le=2000),
    ai_r: AIType = "minimax",
    ai_j: AIType = "bga",
):
    plateau = creer_plateau()
    game_id = uuid4().hex

    # map UI -> internal
    if mode == "pvp":
        internal: ModeInternal = "hvh"
    elif mode == "vsai":
        internal = ai_type  # random|minimax|bga
    else:
        internal = "eve"

    nom = f"WEB_{int(time.time()*1000)}"
    with get_conn() as conn:
        id_partie_pg = db_creer_partie(conn, nom)

    # Qui est humain / IA ?
    if internal == "hvh":
        joueur_depart = ROUGE
        humain = None
        ia_couleur = None
    elif internal in ("random", "minimax", "bga"):
        humain = human_color
        ia_couleur = changer_joueur(humain)
        # le joueur qui commence est toujours ROUGE dans ton projet -> donc parfois l'IA commence
        joueur_depart = ROUGE
    else:
        humain = None
        ia_couleur = None
        joueur_depart = ROUGE

    games[game_id] = {
        "plateau": plateau,
        "joueur": joueur_depart,
        "winner": None,
        "finished": False,
        "mode": internal,
        "coups": [],
        "id_partie_pg": id_partie_pg,
        "depth": depth,
        "delay_ms": delay_ms,
        # vsai
        "human_color": humain,
        "ia_color": ia_couleur,
        "ai_type": ai_type,
        # ia/ia
        "ai_for": {"R": ai_r, "J": ai_j},
    }

    # Auto-start si l'IA doit jouer en premier (humain = JAUNE et ROUGE commence)
    auto = None
    if internal in ("random", "minimax", "bga") and games[game_id]["joueur"] == games[game_id]["ia_color"]:
        await asyncio.sleep(delay_ms / 1000.0)
        with get_conn() as conn:
            col_ia = choisir_coup_par_type(ai_type, plateau, [], conn, games[game_id]["ia_color"], depth)
        if col_ia is not None and coup_valide(plateau, col_ia):
            jouer_coup(plateau, col_ia, games[game_id]["ia_color"])
            games[game_id]["coups"].append(col_ia)
            with get_conn() as conn:
                db_ajouter_coup(conn, id_partie_pg, 1, games[game_id]["ia_color"], col_ia)
            games[game_id]["joueur"] = changer_joueur(games[game_id]["ia_color"])
            auto = {"ia_move": col_ia}

    # Conseil humain (si vsai et humain doit jouer)
    hint = {}
    if internal in ("random", "minimax", "bga") and games[game_id]["joueur"] == games[game_id]["human_color"]:
        hint = conseil_humain(games[game_id], games[game_id]["human_color"])

    return {
        "ok": True,
        "game_id": game_id,
        "plateau": plateau,
        "mode": internal,
        "next_player": games[game_id]["joueur"],
        "sequence": sequence_str(games[game_id]["coups"]),
        "auto": auto,
        **hint,
    }


@app.post("/move/{game_id}")
async def move(game_id: str, col: int = Query(..., ge=0, le=50)):
    game = games.get(game_id)
    if not game:
        return {"ok": False, "error": "Game not found"}

    async with get_lock(game_id):
        plateau = game["plateau"]
        joueur = game["joueur"]

        if game.get("finished") or game.get("winner"):
            return {"ok": False, "error": "Game finished", "plateau": plateau}

        if game["mode"] == "eve":
            return {"ok": False, "error": "Mode IA/IA: utilisez Lancer", "plateau": plateau}

        if not coup_valide(plateau, col):
            return {"ok": False, "error": "Invalid move", "plateau": plateau}

        # interdire humain si ce n'est pas lui (en vsai)
        if game["mode"] in ("random", "minimax", "bga") and joueur != game["human_color"]:
            return {"ok": False, "error": "Ce n'est pas ton tour", "plateau": plateau}

        # coup humain
        jouer_coup(plateau, col, joueur)
        game["coups"].append(col)
        with get_conn() as conn:
            db_ajouter_coup(conn, game["id_partie_pg"], len(game["coups"]), joueur, col)
        with get_conn() as conn:
            safe_query(
                conn,
                "UPDATE parties SET sequence=%s WHERE id_partie=%s;",
                (sequence_str(game["coups"]), game["id_partie_pg"]),
        )

        # victoire humain ?
        win_pos = verifier_victoire(plateau, joueur)
        if win_pos:
            await finir_partie(game, gagnant=joueur, draw=False)
            return {
                "ok": True,
                "plateau": plateau,
                "winner": joueur,
                "win_pos": win_pos,
                "sequence": sequence_str(game["coups"]),
            }

        if plateau_plein(plateau):
            await finir_partie(game, gagnant=None, draw=True)
            return {"ok": True, "plateau": plateau, "draw": True, "sequence": sequence_str(game["coups"])}

        # tour IA si vsai
        game["joueur"] = changer_joueur(joueur)

        payload = {
            "ok": True,
            "plateau": plateau,
            "sequence": sequence_str(game["coups"]),
        }

        if game["mode"] in ("random", "minimax", "bga") and game["joueur"] == game["ia_color"]:
            # prediction IA AVANT de jouer (soutenance)
            best_ai, scores_ai, score_ai, label_ai = analyse_position(plateau, game["ia_color"], profondeur=int(game["depth"]))
            payload["prediction_ai"] = {"label": label_ai, "score": score_ai, "best_col": best_ai}

            await asyncio.sleep(game["delay_ms"] / 1000.0)

            with get_conn() as conn:
                col_ia = choisir_coup_par_type(game["mode"], plateau, game["coups"], conn, game["ia_color"], int(game["depth"]))
            if col_ia is None or not coup_valide(plateau, col_ia):
                return {"ok": False, "error": "IA has no valid move", "plateau": plateau}

            jouer_coup(plateau, col_ia, game["ia_color"])
            game["coups"].append(col_ia)

            with get_conn() as conn:
                db_ajouter_coup(conn, game["id_partie_pg"], len(game["coups"]), game["ia_color"], col_ia)
            
            with get_conn() as conn:
                safe_query(
                    conn,
                    "UPDATE parties SET sequence=%s WHERE id_partie=%s;",
                    (sequence_str(game["coups"]), game["id_partie_pg"]),
            )
            
            # victoire IA ?
            win_pos = verifier_victoire(plateau, game["ia_color"])
            if win_pos:
                await finir_partie(game, gagnant=game["ia_color"], draw=False)
                return {
                    "ok": True,
                    "plateau": plateau,
                    "winner": game["ia_color"],
                    "win_pos": win_pos,
                    "ia_move": col_ia,
                    "sequence": sequence_str(game["coups"]),
                }

            if plateau_plein(plateau):
                await finir_partie(game, gagnant=None, draw=True)
                return {"ok": True, "plateau": plateau, "draw": True, "ia_move": col_ia, "sequence": sequence_str(game["coups"])}

            game["joueur"] = changer_joueur(game["ia_color"])
            payload["ia_move"] = col_ia
            payload["next_player"] = game["joueur"]
            payload["sequence"] = sequence_str(game["coups"])

            # conseil pour humain après coup IA
            payload.update(conseil_humain(game, game["human_color"]))

            # debug BGA (poids) si IA = BGA (ou si tu veux le voir)
            payload["debug"] = debug_bga_for(game, game["ia_color"])
            return payload

        # hvh: tour suivant
        payload["next_player"] = game["joueur"]
        return payload


@app.post("/step/{game_id}")
async def step(game_id: str):
    game = games.get(game_id)
    if not game:
        return {"ok": False, "error": "Game not found"}

    async with get_lock(game_id):
        plateau = game["plateau"]
        joueur = game["joueur"]

        if game.get("finished") or game.get("winner"):
            return {"ok": False, "error": "Game finished", "plateau": plateau}

        if game["mode"] != "eve":
            return {"ok": False, "error": "step seulement pour IA/IA", "plateau": plateau}

        ai_type = game["ai_for"].get(joueur, "random")
        await asyncio.sleep(game["delay_ms"] / 1000.0)

        with get_conn() as conn:
            col = choisir_coup_par_type(ai_type, plateau, game["coups"], conn, joueur, int(game["depth"]))

        if col is None or not coup_valide(plateau, col):
            return {"ok": False, "error": "IA has no valid move", "plateau": plateau}

        jouer_coup(plateau, col, joueur)
        game["coups"].append(col)
        with get_conn() as conn:
            db_ajouter_coup(conn, game["id_partie_pg"], len(game["coups"]), joueur, col)

        win_pos = verifier_victoire(plateau, joueur)
        if win_pos:
            await finir_partie(game, gagnant=joueur, draw=False)
            return {"ok": True, "plateau": plateau, "winner": joueur, "win_pos": win_pos, "ai_move": col, "sequence": sequence_str(game["coups"])}

        if plateau_plein(plateau):
            await finir_partie(game, gagnant=None, draw=True)
            return {"ok": True, "plateau": plateau, "draw": True, "ai_move": col, "sequence": sequence_str(game["coups"])}

        game["joueur"] = changer_joueur(joueur)
        return {"ok": True, "plateau": plateau, "next_player": game["joueur"], "ai_move": col, "sequence": sequence_str(game["coups"])}


# -------------------------
# About data
# -------------------------
@app.get("/api/about")
def api_about():
    # simple stats + derniers id
    with get_conn() as conn:
        rows = safe_query(conn, "SELECT COUNT(*) FROM parties;", fetch=True)
        total = rows[0][0] if rows else 0
        rows2 = safe_query(conn, "SELECT COUNT(*) FROM coups;", fetch=True)
        total_coups = rows2[0][0] if rows2 else 0
    return {"ok": True, "total_parties": total, "total_coups": total_coups}
