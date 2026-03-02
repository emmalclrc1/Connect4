import random
import time

from core.config import COLONNES, LIGNES, VIDE
from core.modele import (
    coup_valide,
    jouer_coup,
    plateau_plein,
    verifier_victoire,
    changer_joueur,
)

# ============================================================
# IA ALEATOIRE
# ============================================================
def coup_aleatoire(plateau):
    colonnes_valides = [c for c in range(COLONNES) if coup_valide(plateau, c)]
    return random.choice(colonnes_valides) if colonnes_valides else None


# ============================================================
# BGA - POIDS (DEBUG + CONSEIL)
# ============================================================
def bga_poids(plateau, coups_deja_joues, connexion_pg, joueur):
    prefix = ",".join(str(c) for c in coups_deja_joues)
    cur = connexion_pg.cursor()

    if prefix:
        cur.execute(
            """
            SELECT sequence, confiance, gagnant FROM parties
            WHERE sequence IS NOT NULL AND sequence <> ''
              AND sequence LIKE %s;
            """,
            (prefix + "%",),
        )
    else:
        cur.execute(
            """
            SELECT sequence, confiance, gagnant FROM parties
            WHERE sequence IS NOT NULL AND sequence <> '';
            """
        )

    rows = cur.fetchall()
    cur.close()

    stats = {}
    total_matches = 0

    for (seq, conf, gagnant) in rows:
        seq_list = [int(x) for x in seq.split(",") if x != ""]
        if len(seq_list) > len(coups_deja_joues):
            next_col = seq_list[len(coups_deja_joues)]
            if 0 <= next_col < COLONNES and coup_valide(plateau, next_col):
                total_matches += 1
                poids = max(1, conf)
                if gagnant == joueur:
                    poids *= 3
                elif gagnant is not None:
                    poids *= 0.3
                stats[next_col] = stats.get(next_col, 0) + poids

    return stats, total_matches


def coup_bga(plateau, coups_deja_joues, connexion_pg, joueur):
    stats, _ = bga_poids(plateau, coups_deja_joues, connexion_pg, joueur)
    if not stats:
        col, _ = coup_minimax(plateau, joueur, profondeur=2)
        return col
    return max(stats, key=stats.get)


# ============================================================
# HEURISTIQUE
# ============================================================
def evaluer_fenetre(fenetre, joueur):
    adv = changer_joueur(joueur)
    score = 0

    vides = fenetre.count(VIDE)
    nb_joueur = fenetre.count(joueur)
    nb_adv = fenetre.count(adv)

    if nb_joueur == 4:
        score += 100000
    elif nb_joueur == 3 and vides == 1:
        score += 100
    elif nb_joueur == 2 and vides == 2:
        score += 10

    if nb_adv == 3 and vides == 1:
        score -= 80

    return score


def evaluer_plateau(plateau, joueur):
    score = 0
    centre_col = COLONNES // 2
    centre_count = sum(1 for l in range(LIGNES) if plateau[l][centre_col] == joueur)
    score += centre_count * 6

    for l in range(LIGNES):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    for c in range(COLONNES):
        for l in range(LIGNES - 3):
            fenetre = [plateau[l + i][c] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    for l in range(LIGNES - 3):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l + i][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    for l in range(3, LIGNES):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l - i][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    return score


# ============================================================
# MINIMAX
# ============================================================
def minimax(plateau, profondeur, alpha, beta, maxing, ia):
    adv = changer_joueur(ia)

    if verifier_victoire(plateau, ia):
        return 100000
    if verifier_victoire(plateau, adv):
        return -100000

    if profondeur == 0 or plateau_plein(plateau):
        return evaluer_plateau(plateau, ia)

    if maxing:
        best = -999999
        for c in range(COLONNES):
            if coup_valide(plateau, c):
                cp = [row[:] for row in plateau]
                jouer_coup(cp, c, ia)
                val = minimax(cp, profondeur - 1, alpha, beta, False, ia)
                best = max(best, val)
                alpha = max(alpha, val)
                if beta <= alpha:
                    break
        return best
    else:
        worst = 999999
        for c in range(COLONNES):
            if coup_valide(plateau, c):
                cp = [row[:] for row in plateau]
                jouer_coup(cp, c, adv)
                val = minimax(cp, profondeur - 1, alpha, beta, True, ia)
                worst = min(worst, val)
                beta = min(beta, val)
                if beta <= alpha:
                    break
        return worst


def coup_minimax(plateau, joueur, profondeur, progress_callback=None, afficher_console=False):
    scores = {}

    for c in range(COLONNES):
        if not coup_valide(plateau, c):
            scores[c] = None
            continue

        cp = [row[:] for row in plateau]
        jouer_coup(cp, c, joueur)

        if verifier_victoire(cp, joueur):
            scores[c] = 100000
        else:
            scores[c] = minimax(cp, profondeur - 1, -999999, 999999, False, joueur)

        if afficher_console:
            ligne = "MiniMax : " + " ".join(
                str(scores[i]) if scores.get(i) is not None else " "
                for i in range(COLONNES)
            )
            print(ligne)
            time.sleep(0.05)

        if progress_callback is not None:
            progress_callback(dict(scores))
            time.sleep(0.05)

    valeurs_valides = [v for v in scores.values() if v is not None]
    if not valeurs_valides:
        return None, scores

    best = max(valeurs_valides)
    meilleures = [c for c, v in scores.items() if v == best]
    col_choisie = random.choice(meilleures)
    return col_choisie, scores


# ============================================================
# PREDICTION + ANALYSE (soutenance)
# ============================================================
def prediction_label(score: int):
    # mapping simple & stable
    if score >= 90000:
        return "victoire"
    if score <= -90000:
        return "defaite"
    if abs(score) <= 5:
        return "nul_ou_equilibre"
    return "incertaine"


def analyse_position(plateau, joueur_a_jouer: str, profondeur: int):
    """
    Retourne:
      - best_col
      - scores (minimax) pour joueur_a_jouer
      - score_best
      - label (victoire/defaite/nul/incertaine) depuis perspective joueur_a_jouer
    """
    best_col, scores = coup_minimax(plateau, joueur_a_jouer, profondeur=profondeur)
    score_best = None
    if best_col is not None:
        score_best = scores.get(best_col)
    label = prediction_label(score_best or 0)
    return best_col, scores, int(score_best or 0), label


def principal_variation_from_board(plateau, joueur_a_jouer: str, profondeur: int, max_len: int = 12):
    """
    Donne une "ligne principale" : une suite de coups recommandés.
    C'est suffisant pour montrer "les coups restants vers la victoire" en soutenance.
    """
    pv = []
    p = [row[:] for row in plateau]
    joueur = joueur_a_jouer
    d = profondeur

    while d > 0 and len(pv) < max_len and not plateau_plein(p):
        col, _, score, _ = analyse_position(p, joueur, d)
        if col is None or not coup_valide(p, col):
            break
        pv.append({"joueur": joueur, "col": col, "score": score})
        jouer_coup(p, col, joueur)
        if verifier_victoire(p, joueur):
            break
        joueur = changer_joueur(joueur)
        d -= 1

    return pv
  




