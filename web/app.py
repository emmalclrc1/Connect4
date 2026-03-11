from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Literal, Optional, List, Tuple
from uuid import uuid4

from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from core.config import ROUGE, JAUNE, LIGNES, COLONNES
from core.database import db_connexion, safe_query, db_creer_partie, db_ajouter_coup
from core.modele import (
    creer_plateau,
    coup_valide,
    jouer_coup,
    changer_joueur,
    verifier_victoire,
    plateau_plein,
)
from core.ia import coup_aleatoire, coup_minimax

ModeUI = Literal["pvp", "vsai", "iaia"]
AIType = Literal["random", "minimax", "bga"]

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
def _read_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


@app.get("/play", response_class=HTMLResponse)
def play_page():
    return _read_template("play.html")


@app.get("/history", response_class=HTMLResponse)
def history_page():
    return _read_template("history.html")


@app.get("/bga", response_class=HTMLResponse)
def bga_page():
    return _read_template("bga.html")


@app.get("/about", response_class=HTMLResponse)
def about_page():
    return _read_template("about.html")


@app.get("/replay/{id_partie}", response_class=HTMLResponse)
def replay_page(id_partie: int):
    return _read_template("replay.html")


@app.get("/")
def root():
    return {"ok": True, "message": "Connect4 API running"}


# -------------------------
# Helpers
# -------------------------
def _deepcopy_plateau(plateau):
    return [row[:] for row in plateau]


def _serialize_game(game: dict):
    return {
        "plateau": game["plateau"],
        "sequence": ",".join(str(c) for c in game["coups"]),
        "winner": game["winner"],
        "finished": game["finished"],
        "win_pos": game["win_pos"],
        "last_move": game["last_move"],
        "next_player": None if game["finished"] else game["joueur"],
    }


def _current_existing_winner(plateau):
    wp_r = verifier_victoire(plateau, ROUGE)
    if wp_r:
        return ROUGE, wp_r
    wp_j = verifier_victoire(plateau, JAUNE)
    if wp_j:
        return JAUNE, wp_j
    return None, None


def _count_pieces(plateau):
    r = 0
    j = 0
    for row in plateau:
        for cell in row:
            if cell == ROUGE:
                r += 1
            elif cell == JAUNE:
                j += 1
    return r, j


def _build_mode_summary(game: dict):
    internal = game["internal"]
    joueur = game["joueur"]

    if internal["kind"] == "pvp":
        return {
            "mode": "Humain vs Humain",
            "detail": "Deux joueurs humains",
            "turn": joueur,
        }

    if internal["kind"] == "vsai":
        human = internal["human"]
        ai = internal["ai"]
        return {
            "mode": "Humain vs IA",
            "detail": f"Humain : {human} • IA : {ai} ({internal['ai_type']})",
            "turn": joueur,
        }

    return {
        "mode": "IA vs IA",
        "detail": f"Rouge : {internal['ai_for']['R']} • Jaune : {internal['ai_for']['J']}",
        "turn": joueur,
    }


# -------------------------
# DB helpers (lazy create)
# -------------------------
def _ensure_db_game(game: dict) -> int:
    """
    Crée la partie en DB uniquement au 1er coup réel (anti parties 0 coup).
    """
    if game.get("id_partie") is not None:
        return int(game["id_partie"])

    nom = f"WEB_{int(time.time()*1000)}"
    with get_conn() as conn:
        pid = db_creer_partie(conn, nom, nb_lignes=LIGNES, nb_colonnes=COLONNES, confiance=1)
    game["id_partie"] = pid
    return int(pid)


def _db_add_move(game: dict, joueur: str, col: int):
    pid = _ensure_db_game(game)
    numero = len(game["coups"])
    with get_conn() as conn:
        db_ajouter_coup(conn, pid, numero, joueur, col)


def _finish_db_game(game: dict, gagnant: Optional[str], draw: bool):
    if game.get("id_partie") is None:
        return
    pid = int(game["id_partie"])
    seq = ",".join(str(c) for c in game["coups"])
    with get_conn() as conn:
        safe_query(
            conn,
            """
            UPDATE parties
            SET statut='TERMINE',
                gagnant=%s,
                sequence=%s
            WHERE id_partie=%s;
            """,
            (None if draw else gagnant, seq, pid),
        )


# -------------------------
# IA move
# -------------------------
def _ai_choose(ai_type: AIType, plateau, joueur_ia: str, depth: int) -> Optional[int]:
    if ai_type == "random":
        return coup_aleatoire(plateau)
    if ai_type == "minimax":
        col, _ = coup_minimax(plateau, joueur_ia, profondeur=depth)
        return col
    if ai_type == "bga":
        col, _ = coup_minimax(plateau, joueur_ia, profondeur=max(2, min(depth, 5)))
        return col
    return None


# -------------------------
# ANALYSE (poids, verdict, PV)
# -------------------------
def _apply_move(plateau, col: int, joueur: str) -> Optional[Tuple[int, int]]:
    if not coup_valide(plateau, col):
        return None
    row = jouer_coup(plateau, col, joueur)
    return (row, col)


def _verdict_from_scores(scores: dict, profondeur: int) -> str:
    vals = [v for v in scores.values() if v is not None]
    if not vals:
        return "INCERTAIN"
    best = max(vals)

    if best >= 100000:
        return "VICTOIRE"
    if best <= -100000:
        return "DEFAITE"

    if profondeur >= 5 and abs(best) < 80:
        return "NUL"

    return "INCERTAIN"


def _pv_find_win_line(plateau, joueur: str, profondeur: int, max_len: int = 12) -> Optional[List[int]]:
    cp = _deepcopy_plateau(plateau)
    seq: List[int] = []
    current = joueur
    adv = changer_joueur(joueur)

    for _ in range(max_len):
        if verifier_victoire(cp, joueur):
            return seq
        if verifier_victoire(cp, adv) or plateau_plein(cp) or profondeur <= 0:
            return None

        if current == joueur:
            best_col, _scores = coup_minimax(cp, joueur, profondeur)
            if best_col is None:
                return None
            _apply_move(cp, best_col, current)
            seq.append(best_col)
        else:
            worst_col = None
            worst_for_player = 10**9

            for c in range(COLONNES):
                if not coup_valide(cp, c):
                    continue
                test = _deepcopy_plateau(cp)
                _apply_move(test, c, adv)
                if verifier_victoire(test, adv):
                    worst_col = c
                    worst_for_player = -100000
                    break

                _, sc = coup_minimax(test, joueur, max(1, profondeur - 1))
                vals = [v for v in sc.values() if v is not None]
                approx = max(vals) if vals else 0
                if approx < worst_for_player:
                    worst_for_player = approx
                    worst_col = c

            if worst_col is None:
                return None
            _apply_move(cp, worst_col, current)
            seq.append(worst_col)

        current = changer_joueur(current)
        profondeur -= 1

    return None


@app.get("/api/analyze/{game_id}")
def api_analyze(
    game_id: str,
    for_player: str = Query(..., pattern="^(R|J)$"),
    depth: int = Query(4, ge=1, le=9),
):
    game = games.get(game_id)
    if not game:
        return {"ok": False, "error": "Game not found"}

    plateau = game["plateau"]

    existing_winner, existing_win_pos = _current_existing_winner(plateau)
    if existing_winner:
        return {
            "ok": True,
            "for_player": for_player,
            "depth": depth,
            "scores": [None for _ in range(COLONNES)],
            "best_col": None,
            "verdict": "VICTOIRE" if existing_winner == for_player else "DEFAITE",
            "pv": [],
            "existing_winner": existing_winner,
            "winning_cells": existing_win_pos,
        }

    best_col, scores = coup_minimax(plateau, for_player, profondeur=depth)
    verdict = _verdict_from_scores(scores, depth)
    pv = _pv_find_win_line(plateau, for_player, depth, max_len=12) if verdict == "VICTOIRE" else None

    scores_list = []
    for c in range(COLONNES):
        v = scores.get(c, None)
        scores_list.append(None if v is None else int(v))

    return {
        "ok": True,
        "for_player": for_player,
        "depth": depth,
        "scores": scores_list,
        "best_col": best_col,
        "verdict": verdict,
        "pv": pv,
        "existing_winner": None,
        "winning_cells": None,
    }


@app.get("/api/analyze_sequence")
def api_analyze_sequence(
    sequence: str = Query("", description="Ex: 3,3,4,2"),
    for_player: str = Query("R", pattern="^(R|J)$"),
    depth: int = Query(5, ge=1, le=9),
):
    plateau = creer_plateau()
    joueur = ROUGE
    coups = []

    if sequence.strip():
        parts = [p.strip() for p in sequence.split(",") if p.strip()]
        for p in parts:
            try:
                col = int(p)
            except Exception:
                return {"ok": False, "error": "Séquence invalide (entiers séparés par des virgules)"}

            if col < 0 or col >= COLONNES or not coup_valide(plateau, col):
                return {"ok": False, "error": f"Coup invalide dans la séquence : {col}"}

            jouer_coup(plateau, col, joueur)
            coups.append(col)

            if verifier_victoire(plateau, joueur) or plateau_plein(plateau):
                break
            joueur = changer_joueur(joueur)

    existing_winner, existing_win_pos = _current_existing_winner(plateau)
    if existing_winner:
        return {
            "ok": True,
            "plateau": plateau,
            "sequence_applied": ",".join(map(str, coups)),
            "for_player": for_player,
            "depth": depth,
            "scores": [None for _ in range(COLONNES)],
            "best_col": None,
            "verdict": "VICTOIRE" if existing_winner == for_player else "DEFAITE",
            "pv": [],
            "existing_winner": existing_winner,
            "winning_cells": existing_win_pos,
        }

    best_col, scores = coup_minimax(plateau, for_player, profondeur=depth)
    verdict = _verdict_from_scores(scores, depth)
    pv = _pv_find_win_line(plateau, for_player, depth, max_len=14) if verdict == "VICTOIRE" else None

    scores_list = []
    for c in range(COLONNES):
        v = scores.get(c, None)
        scores_list.append(None if v is None else int(v))

    return {
        "ok": True,
        "plateau": plateau,
        "sequence_applied": ",".join(map(str, coups)),
        "for_player": for_player,
        "depth": depth,
        "scores": scores_list,
        "best_col": best_col,
        "verdict": verdict,
        "pv": pv,
        "existing_winner": None,
        "winning_cells": None,
    }


@app.post("/api/analyze_board")
def api_analyze_board(
    board: List[List[str]] = Body(...),
    for_player: str = Query("R", pattern="^(R|J)$"),
    depth: int = Query(5, ge=1, le=9),
):
    if not isinstance(board, list) or len(board) != LIGNES:
        return {"ok": False, "error": "Board invalide (lignes)"}
    for r in range(LIGNES):
        if not isinstance(board[r], list) or len(board[r]) != COLONNES:
            return {"ok": False, "error": "Board invalide (colonnes)"}
        for c in range(COLONNES):
            if board[r][c] not in (".", "R", "J"):
                return {"ok": False, "error": "Board invalide (valeurs)"}

    existing_winner, existing_win_pos = _current_existing_winner(board)
    if existing_winner:
        return {
            "ok": True,
            "for_player": for_player,
            "depth": depth,
            "scores": [None for _ in range(COLONNES)],
            "best_col": None,
            "verdict": "VICTOIRE" if existing_winner == for_player else "DEFAITE",
            "pv": [],
            "existing_winner": existing_winner,
            "winning_cells": existing_win_pos,
        }

    best_col, scores = coup_minimax(board, for_player, profondeur=depth)
    verdict = _verdict_from_scores(scores, depth)
    pv = _pv_find_win_line(board, for_player, depth, max_len=14) if verdict == "VICTOIRE" else None

    scores_list = []
    for c in range(COLONNES):
        v = scores.get(c, None)
        scores_list.append(None if v is None else int(v))

    return {
        "ok": True,
        "for_player": for_player,
        "depth": depth,
        "scores": scores_list,
        "best_col": best_col,
        "verdict": verdict,
        "pv": pv,
        "existing_winner": None,
        "winning_cells": None,
    }


# -------------------------
# API - Stats / History / About / Replay
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
                SUM(CASE WHEN gagnant IS NULL AND statut='TERMINE' THEN 1 ELSE 0 END) AS nuls,
                SUM(CASE WHEN statut='EN_COURS' THEN 1 ELSE 0 END) AS en_cours
            FROM parties;
            """,
            fetch=True,
        )
    (total, rouge, jaune, nuls, en_cours) = rows[0] if rows else (0, 0, 0, 0, 0)
    return {
        "ok": True,
        "total": int(total or 0),
        "rouge": int(rouge or 0),
        "jaune": int(jaune or 0),
        "nuls": int(nuls or 0),
        "en_cours": int(en_cours or 0),
    }


@app.get("/api/history")
def api_history(limit: int = Query(5000, ge=1, le=5000), offset: int = Query(0, ge=0)):
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
                "nb_coups": int(nb_coups or 0),
            }
        )
    return {"ok": True, "items": items}


@app.get("/api/replay/{id_partie}")
def api_replay(id_partie: int):
    with get_conn() as conn:
        p = safe_query(
            conn,
            """
            SELECT id_partie, nom, statut, gagnant, sequence, created_at, nb_lignes, nb_colonnes
            FROM parties
            WHERE id_partie=%s;
            """,
            (id_partie,),
            fetch=True,
        )
        if not p:
            return {"ok": False, "error": "Partie introuvable"}

        coups = safe_query(
            conn,
            """
            SELECT numero_coup, joueur, colonne
            FROM coups
            WHERE id_partie=%s
            ORDER BY numero_coup ASC;
            """,
            (id_partie,),
            fetch=True,
        ) or []

    row = p[0]
    return {
        "ok": True,
        "partie": {
            "id_partie": row[0],
            "nom": row[1],
            "statut": row[2],
            "gagnant": row[3],
            "sequence": row[4] or "",
            "created_at": row[5].isoformat() if row[5] else None,
            "nb_lignes": row[6],
            "nb_colonnes": row[7],
        },
        "coups": [{"n": n, "joueur": j, "col": c} for (n, j, c) in coups],
    }


@app.get("/api/about/details")
def api_about_details():
    with get_conn() as conn:
        stats = safe_query(
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
        total, rouge, jaune, nuls = stats[0] if stats else (0, 0, 0, 0)

        by_day = safe_query(
            conn,
            """
            SELECT DATE(created_at) AS d, COUNT(*) AS n
            FROM parties
            GROUP BY DATE(created_at)
            ORDER BY d DESC
            LIMIT 14;
            """,
            fetch=True,
        ) or []

    return {
        "ok": True,
        "summary": {
            "total": int(total or 0),
            "rouge": int(rouge or 0),
            "jaune": int(jaune or 0),
            "nuls": int(nuls or 0),
        },
        "activity": [{"day": str(d), "n": int(n)} for (d, n) in reversed(by_day)],
        "author": "Emma Le Cloirec",
    }


# -------------------------
# API - BGA import
# -------------------------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/import-bga-auto")
def import_bga_auto(payload: dict = Body(...)):
    moves = payload.get("moves") or []
    starts_with = (payload.get("starts_with") or "rouge").lower()

    if not moves:
        return {"imported": False, "reason": "moves vides"}

    try:
        seq = [int(c) - 1 for c in moves]
    except Exception:
        return {"imported": False, "reason": "moves invalides"}

    if any(c < 0 or c >= COLONNES for c in seq):
        return {"imported": False, "reason": "colonnes hors limites"}

    plateau = creer_plateau()
    coups = []
    winner = None
    win_pos = None

    joueur = ROUGE if starts_with == "rouge" else JAUNE

    with get_conn() as conn:
        pid = db_creer_partie(
            conn,
            nom=f"BGA_AUTO_{int(time.time())}",
            nb_lignes=LIGNES,
            nb_colonnes=COLONNES,
            confiance=1
        )

        for i, col in enumerate(seq):
            if not coup_valide(plateau, col):
                break

            jouer_coup(plateau, col, joueur)
            coups.append(col)
            db_ajouter_coup(conn, pid, i + 1, joueur, col)

            wp = verifier_victoire(plateau, joueur)
            if wp:
                winner = joueur
                win_pos = wp
                break

            if plateau_plein(plateau):
                break

            joueur = changer_joueur(joueur)

        seq_str = ",".join(str(c) for c in coups)

        safe_query(
            conn,
            """
            UPDATE parties
            SET statut='TERMINE',
                gagnant=%s,
                sequence=%s
            WHERE id_partie=%s;
            """,
            (winner, seq_str, pid),
        )

    return {
        "imported": True,
        "id_partie": pid,
        "winner": winner,
        "moves": len(coups),
        "win_pos": win_pos
    }


@app.post("/api/bga/import")
def api_bga_import(table_id: int = Query(..., ge=1)):
    try:
        from scripts.bga_scraper import BGAScraper
    except ModuleNotFoundError:
        return {
            "ok": False,
            "error": "Import BGA indisponible sur render (selenium non installé). Lance l'import en local, ou installe selenium.",
        }

    scraper = BGAScraper(headless=True)
    try:
        moves = scraper.get_moves_with_colors_from_table(table_id)
        if not moves:
            return {"ok": False, "error": "Impossible de lire la partie (non loggée / replay limité / format inconnu)."}

        seq = [col - 1 for (_color, col) in moves]
        if any(c < 0 for c in seq):
            return {"ok": False, "error": "Colonnes invalides récupérées."}

        plateau = creer_plateau()
        coups = []
        winner = None
        win_pos = None

        with get_conn() as conn:
            pid = db_creer_partie(conn, f"BGA_{table_id}", nb_lignes=LIGNES, nb_colonnes=COLONNES, confiance=2)

            joueur = ROUGE
            for i, col in enumerate(seq):
                if not coup_valide(plateau, col):
                    break

                jouer_coup(plateau, col, joueur)
                coups.append(col)
                db_ajouter_coup(conn, pid, i + 1, joueur, col)

                wp = verifier_victoire(plateau, joueur)
                if wp:
                    winner = joueur
                    win_pos = wp
                    break

                if plateau_plein(plateau):
                    break

                joueur = changer_joueur(joueur)

            seq_str = ",".join(str(c) for c in coups)
            safe_query(
                conn,
                """
                UPDATE parties
                SET statut='TERMINE', gagnant=%s, sequence=%s
                WHERE id_partie=%s;
                """,
                (winner, seq_str, pid),
            )

        return {"ok": True, "id_partie": pid, "winner": winner, "moves": len(coups), "win_pos": win_pos}
    finally:
        scraper.close()


# -------------------------
# Game API
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

    if mode == "pvp":
        internal = {"kind": "pvp"}
    elif mode == "vsai":
        internal = {"kind": "vsai", "human": human_color, "ai": changer_joueur(human_color), "ai_type": ai_type}
    else:
        internal = {"kind": "iaia", "ai_for": {"R": ai_r, "J": ai_j}}

    games[game_id] = {
        "plateau": plateau,
        "joueur": ROUGE,
        "finished": False,
        "winner": None,
        "win_pos": None,
        "coups": [],
        "id_partie": None,
        "depth": int(depth),
        "delay_ms": int(delay_ms),
        "internal": internal,
        "last_move": None,
    }

    auto = None
    if internal["kind"] == "vsai" and internal["ai"] == ROUGE:
        await asyncio.sleep(delay_ms / 1000.0)
        col = _ai_choose(internal["ai_type"], plateau, ROUGE, int(depth))
        if col is not None and coup_valide(plateau, col):
            row = jouer_coup(plateau, col, ROUGE)
            games[game_id]["coups"].append(col)
            games[game_id]["last_move"] = {"row": row, "col": col, "player": ROUGE}
            _db_add_move(games[game_id], ROUGE, col)
            games[game_id]["joueur"] = JAUNE
            auto = {"ia_move": col}

    return {
        "ok": True,
        "game_id": game_id,
        "plateau": plateau,
        "sequence": ",".join(str(c) for c in games[game_id]["coups"]),
        "auto": auto,
        "mode_summary": _build_mode_summary(games[game_id]),
    }


@app.post("/move/{game_id}")
async def move(game_id: str, col: int = Query(..., ge=0, le=50)):
    game = games.get(game_id)
    if not game:
        return {"ok": False, "error": "Game not found"}
    if game["finished"]:
        return {"ok": False, "error": "Partie terminée"}

    async with get_lock(game_id):
        internal = game["internal"]
        plateau = game["plateau"]
        joueur = game["joueur"]

        if internal["kind"] == "iaia":
            return {"ok": False, "error": "Mode IA/IA : utilise le bouton Lancer"}

        if internal["kind"] == "vsai" and joueur == internal["ai"]:
            return {"ok": False, "error": "C'est à l'IA de jouer"}

        if not coup_valide(plateau, col):
            return {"ok": False, "error": "Coup invalide"}

        row = jouer_coup(plateau, col, joueur)
        game["coups"].append(col)
        game["last_move"] = {"row": row, "col": col, "player": joueur}
        _db_add_move(game, joueur, col)

        wp = verifier_victoire(plateau, joueur)
        if wp:
            game["finished"] = True
            game["winner"] = joueur
            game["win_pos"] = wp
            _finish_db_game(game, joueur, draw=False)
            return {
                "ok": True,
                **_serialize_game(game),
                "draw": False,
                "mode_summary": _build_mode_summary(game),
            }

        if plateau_plein(plateau):
            game["finished"] = True
            _finish_db_game(game, None, draw=True)
            return {
                "ok": True,
                **_serialize_game(game),
                "draw": True,
                "mode_summary": _build_mode_summary(game),
            }

        game["joueur"] = changer_joueur(joueur)

        return {
            "ok": True,
            **_serialize_game(game),
            "draw": False,
            "mode_summary": _build_mode_summary(game),
        }


@app.post("/ai-move/{game_id}")
async def ai_move(game_id: str):
    game = games.get(game_id)
    if not game:
        return {"ok": False, "error": "Game not found"}
    if game["finished"]:
        return {"ok": False, "error": "Partie terminée"}

    async with get_lock(game_id):
        internal = game["internal"]
        if internal["kind"] != "vsai":
            return {"ok": False, "error": "Pas en mode Humain vs IA"}

        if game["joueur"] != internal["ai"]:
            return {"ok": False, "error": "Ce n'est pas le tour de l'IA"}

        await asyncio.sleep(game["delay_ms"] / 1000.0)

        plateau = game["plateau"]
        col_ia = _ai_choose(internal["ai_type"], plateau, internal["ai"], game["depth"])
        if col_ia is None or not coup_valide(plateau, col_ia):
            return {"ok": False, "error": "IA ne trouve pas de coup"}

        row = jouer_coup(plateau, col_ia, internal["ai"])
        game["coups"].append(col_ia)
        game["last_move"] = {"row": row, "col": col_ia, "player": internal["ai"]}
        _db_add_move(game, internal["ai"], col_ia)

        wp = verifier_victoire(plateau, internal["ai"])
        if wp:
            game["finished"] = True
            game["winner"] = internal["ai"]
            game["win_pos"] = wp
            _finish_db_game(game, internal["ai"], draw=False)
            return {
                "ok": True,
                **_serialize_game(game),
                "draw": False,
                "mode_summary": _build_mode_summary(game),
            }

        if plateau_plein(plateau):
            game["finished"] = True
            _finish_db_game(game, None, draw=True)
            return {
                "ok": True,
                **_serialize_game(game),
                "draw": True,
                "mode_summary": _build_mode_summary(game),
            }

        game["joueur"] = changer_joueur(internal["ai"])
        return {
            "ok": True,
            **_serialize_game(game),
            "draw": False,
            "mode_summary": _build_mode_summary(game),
        }


@app.post("/switch-mode/{game_id}")
async def switch_mode(
    game_id: str,
    mode: ModeUI = Query(...),
    human_color: Literal["R", "J"] = "R",
    ai_type: AIType = "minimax",
    ai_r: AIType = "minimax",
    ai_j: AIType = "bga",
    depth: int = Query(4, ge=1, le=9),
    delay_ms: int = Query(350, ge=0, le=2000),
):
    game = games.get(game_id)
    if not game:
        return {"ok": False, "error": "Game not found"}
    if game["finished"]:
        return {"ok": False, "error": "Partie terminée"}

    async with get_lock(game_id):
        if mode == "pvp":
            internal = {"kind": "pvp"}
        elif mode == "vsai":
            internal = {"kind": "vsai", "human": human_color, "ai": changer_joueur(human_color), "ai_type": ai_type}
        else:
            internal = {"kind": "iaia", "ai_for": {"R": ai_r, "J": ai_j}}

        game["internal"] = internal
        game["depth"] = int(depth)
        game["delay_ms"] = int(delay_ms)

        return {
            "ok": True,
            **_serialize_game(game),
            "mode_summary": _build_mode_summary(game),
        }


@app.post("/start-from-board")
async def start_from_board(
    board: List[List[str]] = Body(...),
    mode: ModeUI = Query("pvp"),
    next_player: Literal["R", "J"] = "R",
    human_color: Literal["R", "J"] = "R",
    ai_type: AIType = "minimax",
    ai_r: AIType = "minimax",
    ai_j: AIType = "bga",
    depth: int = Query(4, ge=1, le=9),
    delay_ms: int = Query(350, ge=0, le=2000),
):
    if not isinstance(board, list) or len(board) != LIGNES:
        return {"ok": False, "error": "Board invalide (lignes)"}
    for r in range(LIGNES):
        if not isinstance(board[r], list) or len(board[r]) != COLONNES:
            return {"ok": False, "error": "Board invalide (colonnes)"}
        for c in range(COLONNES):
            if board[r][c] not in (".", "R", "J"):
                return {"ok": False, "error": "Board invalide (valeurs)"}

    existing_winner, _existing_win_pos = _current_existing_winner(board)
    if existing_winner:
        return {"ok": False, "error": "Impossible de reprendre : cette position est déjà gagnante."}

    r_count, j_count = _count_pieces(board)
    if r_count < j_count or r_count > j_count + 1:
        return {"ok": False, "error": "Position incohérente : nombre de pions invalide."}

    expected_next = ROUGE if r_count == j_count else JAUNE
    if next_player != expected_next:
        return {"ok": False, "error": f"Joueur suivant incohérent. Attendu : {expected_next}"}

    game_id = uuid4().hex
    if mode == "pvp":
        internal = {"kind": "pvp"}
    elif mode == "vsai":
        internal = {"kind": "vsai", "human": human_color, "ai": changer_joueur(human_color), "ai_type": ai_type}
    else:
        internal = {"kind": "iaia", "ai_for": {"R": ai_r, "J": ai_j}}

    games[game_id] = {
        "plateau": _deepcopy_plateau(board),
        "joueur": next_player,
        "finished": False,
        "winner": None,
        "win_pos": None,
        "coups": [],
        "id_partie": None,
        "depth": int(depth),
        "delay_ms": int(delay_ms),
        "internal": internal,
        "last_move": None,
    }

    return {
        "ok": True,
        "game_id": game_id,
        "plateau": games[game_id]["plateau"],
        "sequence": "",
        "mode_summary": _build_mode_summary(games[game_id]),
    }


@app.post("/step/{game_id}")
async def step(game_id: str):
    game = games.get(game_id)
    if not game:
        return {"ok": False, "error": "Game not found"}
    if game["finished"]:
        return {"ok": False, "error": "Partie terminée"}

    async with get_lock(game_id):
        internal = game["internal"]
        if internal["kind"] != "iaia":
            return {"ok": False, "error": "Pas en mode IA/IA"}

        plateau = game["plateau"]
        joueur = game["joueur"]
        ai_type = internal["ai_for"][joueur]

        col = _ai_choose(ai_type, plateau, joueur, game["depth"])
        if col is None or not coup_valide(plateau, col):
            return {"ok": False, "error": "IA ne trouve pas de coup"}

        row = jouer_coup(plateau, col, joueur)
        game["coups"].append(col)
        game["last_move"] = {"row": row, "col": col, "player": joueur}
        _db_add_move(game, joueur, col)

        wp = verifier_victoire(plateau, joueur)
        if wp:
            game["finished"] = True
            game["winner"] = joueur
            game["win_pos"] = wp
            _finish_db_game(game, joueur, draw=False)
            return {
                "ok": True,
                **_serialize_game(game),
                "draw": False,
                "mode_summary": _build_mode_summary(game),
            }

        if plateau_plein(plateau):
            game["finished"] = True
            _finish_db_game(game, None, draw=True)
            return {
                "ok": True,
                **_serialize_game(game),
                "draw": True,
                "mode_summary": _build_mode_summary(game),
            }

        game["joueur"] = changer_joueur(joueur)
        return {
            "ok": True,
            **_serialize_game(game),
            "draw": False,
            "mode_summary": _build_mode_summary(game),
        }
