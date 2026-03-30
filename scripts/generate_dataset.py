import argparse
import random
import time
from typing import List, Optional, Tuple

from core.config import LIGNES, COLONNES, ROUGE, JAUNE
from core.database import db_connexion, safe_query
from core.modele import (
    creer_plateau,
    coup_valide,
    jouer_coup,
    changer_joueur,
    verifier_victoire,
    plateau_plein,
)
from core.ia import coup_aleatoire, coup_minimax


def mirror_col(col: int) -> int:
    return COLONNES - 1 - col


def mirror_sequence(seq: List[int]) -> List[int]:
    return [mirror_col(c) for c in seq]


def insert_game(conn, nom: str, sequence: List[int], winner: Optional[str], confiance: int):
    rows = safe_query(
        conn,
        """
        INSERT INTO parties (nom, statut, gagnant, sequence, nb_lignes, nb_colonnes, confiance)
        VALUES (%s, 'TERMINE', %s, %s, %s, %s, %s)
        RETURNING id_partie;
        """,
        (nom, winner, ",".join(str(c) for c in sequence), LIGNES, COLONNES, confiance),
        fetch=True,
    )
    pid = rows[0][0]

    joueur = ROUGE
    for i, col in enumerate(sequence, start=1):
        safe_query(
            conn,
            """
            INSERT INTO coups (id_partie, numero_coup, joueur, colonne)
            VALUES (%s, %s, %s, %s);
            """,
            (pid, i, joueur, col),
        )
        joueur = changer_joueur(joueur)

    return pid


def choose_opening_moves(plateau, joueur, max_forced: int) -> List[int]:
    """
    Force quelques coups d'ouverture pour varier la base.
    On privilégie les colonnes centrales.
    """
    seq = []
    nb = random.randint(0, max_forced)
    center = COLONNES // 2
    preferred = [center, center - 1, center + 1, center - 2, center + 2, 0, COLONNES - 1]

    for _ in range(nb):
        valid = [c for c in preferred if 0 <= c < COLONNES and coup_valide(plateau, c)]
        if not valid:
            break
        col = random.choice(valid)
        jouer_coup(plateau, col, joueur)
        seq.append(col)

        if verifier_victoire(plateau, joueur) or plateau_plein(plateau):
            break

        joueur = changer_joueur(joueur)

    return seq


def smart_move(plateau, joueur: str, mode: str, depth: int) -> Optional[int]:
    valid = [c for c in range(COLONNES) if coup_valide(plateau, c)]
    if not valid:
        return None

    if mode == "random":
        return coup_aleatoire(plateau)

    if mode == "minimax":
        col, _ = coup_minimax(plateau, joueur, profondeur=depth)
        return col

    if mode == "hybrid":
        # 80% minimax, 20% random pour simuler des erreurs humaines
        if random.random() < 0.8:
            col, _ = coup_minimax(plateau, joueur, profondeur=depth)
            return col
        return coup_aleatoire(plateau)

    raise ValueError(f"Mode inconnu: {mode}")


def play_one_game(
    red_mode: str,
    yellow_mode: str,
    red_depth: int,
    yellow_depth: int,
    max_forced_opening: int = 3,
) -> Tuple[List[int], Optional[str]]:
    plateau = creer_plateau()
    joueur = ROUGE
    sequence = []

    # Ouverture forcée pour éviter 40k parties quasi identiques
    forced = choose_opening_moves(plateau, joueur, max_forced_opening)
    sequence.extend(forced)

    if forced:
        joueur = ROUGE if len(forced) % 2 == 0 else JAUNE

    while True:
        mode = red_mode if joueur == ROUGE else yellow_mode
        depth = red_depth if joueur == ROUGE else yellow_depth

        col = smart_move(plateau, joueur, mode, depth)
        if col is None or not coup_valide(plateau, col):
            return sequence, None

        jouer_coup(plateau, col, joueur)
        sequence.append(col)

        if verifier_victoire(plateau, joueur):
            return sequence, joueur

        if plateau_plein(plateau):
            return sequence, None

        joueur = changer_joueur(joueur)


def build_profile():
    """
    Mélange de profils pour obtenir des parties intelligentes + variées.
    """
    r = random.random()

    if r < 0.45:
        return ("minimax", "minimax", 2, 2, 2)
    if r < 0.75:
        return ("minimax", "minimax", 3, 2, 3)
    if r < 0.90:
        return ("minimax", "minimax", 3, 3, 3)
    if r < 0.97:
        return ("hybrid", "minimax", 2, 3, 1)
    return ("minimax", "hybrid", 3, 2, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1000, help="Nombre de parties à générer")
    parser.add_argument("--mirror", action="store_true", help="Insère aussi la version miroir de chaque partie")
    parser.add_argument("--batch-commit", type=int, default=200, help="Commit toutes les N parties")
    args = parser.parse_args()

    conn = db_connexion()
    conn.autocommit = False

    inserted = 0
    started = time.time()

    try:
        for i in range(args.games):
            red_mode, yellow_mode, red_depth, yellow_depth, confiance = build_profile()

            seq, winner = play_one_game(
                red_mode=red_mode,
                yellow_mode=yellow_mode,
                red_depth=red_depth,
                yellow_depth=yellow_depth,
                max_forced_opening=3,
            )

            if len(seq) < 7:
                continue

            name = f"GEN_{int(time.time())}_{i}"
            insert_game(conn, name, seq, winner, confiance)
            inserted += 1

            if args.mirror:
                mirrored = mirror_sequence(seq)
                insert_game(conn, name + "_M", mirrored, winner, confiance)
                inserted += 1

            if inserted % args.batch_commit == 0:
                conn.commit()
                elapsed = time.time() - started
                print(f"{inserted} parties insérées en {elapsed:.1f}s")

        conn.commit()
        elapsed = time.time() - started
        print(f"Terminé : {inserted} parties insérées en {elapsed:.1f}s")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
