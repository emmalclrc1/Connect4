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

WIN_SCORE = 10_000_000
LOSE_SCORE = -10_000_000


def ordered_cols():
    centre = COLONNES // 2
    return sorted(range(COLONNES), key=lambda c: abs(c - centre))


ORDERED_COLS = ordered_cols()


# ============================================================
# IA ALEATOIRE
# ============================================================
def coup_aleatoire(plateau):
    colonnes_valides = [c for c in ORDERED_COLS if coup_valide(plateau, c)]
    return random.choice(colonnes_valides) if colonnes_valides else None


# ============================================================
# OUTILS
# ============================================================
def clone_plateau(plateau):
    return [row[:] for row in plateau]


def plateau_key(plateau):
    return tuple(tuple(row) for row in plateau)


def colonnes_valides_ordonnees(plateau):
    return [c for c in ORDERED_COLS if coup_valide(plateau, c)]


def coup_gagnant_immediat(plateau, joueur):
    for c in colonnes_valides_ordonnees(plateau):
        cp = clone_plateau(plateau)
        jouer_coup(cp, c, joueur)
        if verifier_victoire(cp, joueur):
            return c
    return None


def coups_gagnants_immediats(plateau, joueur):
    res = []
    for c in colonnes_valides_ordonnees(plateau):
        cp = clone_plateau(plateau)
        jouer_coup(cp, c, joueur)
        if verifier_victoire(cp, joueur):
            res.append(c)
    return res


def coup_donne_victoire_adverse_immediate(plateau, col, joueur):
    """
    True si jouer 'col' permet ensuite à l'adversaire de gagner immédiatement.
    """
    if not coup_valide(plateau, col):
        return True

    adv = changer_joueur(joueur)
    cp = clone_plateau(plateau)
    jouer_coup(cp, col, joueur)

    return coup_gagnant_immediat(cp, adv) is not None


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
        if len(seq_list) <= len(coups_deja_joues):
            continue

        next_col = seq_list[len(coups_deja_joues)]
        if not (0 <= next_col < COLONNES):
            continue
        if not coup_valide(plateau, next_col):
            continue

        total_matches += 1
        poids = max(1, int(conf or 1))

        if gagnant == joueur:
            poids *= 3
        elif gagnant is not None:
            poids *= 0.3

        # petit bonus centre
        poids *= (1.0 + max(0, 3 - abs(next_col - (COLONNES // 2))) * 0.10)

        # pénalité si le coup est immédiatement dangereux
        if coup_donne_victoire_adverse_immediate(plateau, next_col, joueur):
            poids *= 0.05

        stats[next_col] = stats.get(next_col, 0) + poids

    return stats, total_matches


def coup_bga(plateau, coups_deja_joues, connexion_pg, joueur):
    adv = changer_joueur(joueur)

    # 1) gagner tout de suite
    win_now = coup_gagnant_immediat(plateau, joueur)
    if win_now is not None:
        return win_now

    # 2) bloquer l'adversaire tout de suite
    block_now = coup_gagnant_immediat(plateau, adv)
    if block_now is not None:
        return block_now

    # 3) essayer via la base
    stats, _ = bga_poids(plateau, coups_deja_joues, connexion_pg, joueur)
    if stats:
        best_cols = sorted(stats.items(), key=lambda kv: kv[1], reverse=True)
        for c, _ in best_cols:
            if not coup_donne_victoire_adverse_immediate(plateau, c, joueur):
                return c
        return best_cols[0][0]

    # 4) fallback minimax plus sérieux que profondeur 2
    col, _ = coup_minimax(plateau, joueur, profondeur=4)
    return col


# ============================================================
# HEURISTIQUE
# ============================================================
def evaluer_fenetre(fenetre, joueur):
    adv = changer_joueur(joueur)
    score = 0

    nb_joueur = fenetre.count(joueur)
    nb_adv = fenetre.count(adv)
    nb_vides = fenetre.count(VIDE)

    if nb_joueur == 4:
        score += 100000
    elif nb_joueur == 3 and nb_vides == 1:
        score += 600
    elif nb_joueur == 2 and nb_vides == 2:
        score += 50
    elif nb_joueur == 1 and nb_vides == 3:
        score += 4

    if nb_adv == 4:
        score -= 100000
    elif nb_adv == 3 and nb_vides == 1:
        score -= 750
    elif nb_adv == 2 and nb_vides == 2:
        score -= 60

    return score


def evaluer_plateau(plateau, joueur):
    adv = changer_joueur(joueur)
    score = 0

    # Contrôle du centre
    centre_col = COLONNES // 2
    centre_count_j = sum(1 for l in range(LIGNES) if plateau[l][centre_col] == joueur)
    centre_count_a = sum(1 for l in range(LIGNES) if plateau[l][centre_col] == adv)
    score += centre_count_j * 12
    score -= centre_count_a * 10

    # Horizontales
    for l in range(LIGNES):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    # Verticales
    for c in range(COLONNES):
        for l in range(LIGNES - 3):
            fenetre = [plateau[l + i][c] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    # Diagonales descendantes
    for l in range(LIGNES - 3):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l + i][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    # Diagonales montantes
    for l in range(3, LIGNES):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l - i][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    # Menaces immédiates
    my_wins = len(coups_gagnants_immediats(plateau, joueur))
    opp_wins = len(coups_gagnants_immediats(plateau, adv))
    score += my_wins * 2000
    score -= opp_wins * 2400

    return score


# ============================================================
# MINIMAX
# ============================================================
def minimax(plateau, profondeur, alpha, beta, maxing, ia, memo=None):
    if memo is None:
        memo = {}

    adv = changer_joueur(ia)

    key = (plateau_key(plateau), profondeur, maxing, ia)
    if key in memo:
        return memo[key]

    if verifier_victoire(plateau, ia):
        val = WIN_SCORE + profondeur
        memo[key] = val
        return val

    if verifier_victoire(plateau, adv):
        val = LOSE_SCORE - profondeur
        memo[key] = val
        return val

    if plateau_plein(plateau):
        memo[key] = 0
        return 0

    if profondeur == 0:
        val = evaluer_plateau(plateau, ia)
        memo[key] = val
        return val

    valid_cols = colonnes_valides_ordonnees(plateau)

    if maxing:
        best = -10**18
        for c in valid_cols:
            cp = clone_plateau(plateau)
            jouer_coup(cp, c, ia)

            if verifier_victoire(cp, ia):
                val = WIN_SCORE + profondeur
            else:
                val = minimax(cp, profondeur - 1, alpha, beta, False, ia, memo)

            best = max(best, val)
            alpha = max(alpha, best)
            if beta <= alpha:
                break

        memo[key] = best
        return best

    worst = 10**18
    for c in valid_cols:
        cp = clone_plateau(plateau)
        jouer_coup(cp, c, adv)

        if verifier_victoire(cp, adv):
            val = LOSE_SCORE - profondeur
        else:
            val = minimax(cp, profondeur - 1, alpha, beta, True, ia, memo)

        worst = min(worst, val)
        beta = min(beta, worst)
        if beta <= alpha:
            break

    memo[key] = worst
    return worst


def coup_minimax(plateau, joueur, profondeur, progress_callback=None, afficher_console=False):
    adv = changer_joueur(joueur)
    valid_cols = colonnes_valides_ordonnees(plateau)
    scores = {c: None for c in range(COLONNES)}

    if not valid_cols:
        return None, scores

    # 1) gagner tout de suite
    win_now = coup_gagnant_immediat(plateau, joueur)
    if win_now is not None:
        scores[win_now] = WIN_SCORE
        return win_now, scores

    # 2) bloquer l'adversaire tout de suite
    block_now = coup_gagnant_immediat(plateau, adv)
    if block_now is not None:
        scores[block_now] = WIN_SCORE - 1
        return block_now, scores

    memo = {}

    for c in valid_cols:
        cp = clone_plateau(plateau)
        jouer_coup(cp, c, joueur)

        if verifier_victoire(cp, joueur):
            scores[c] = WIN_SCORE
        elif coup_gagnant_immediat(cp, adv) is not None:
            # Évite les coups suicides
            scores[c] = -5_000_000
        else:
            scores[c] = minimax(
                cp,
                profondeur - 1,
                -10**18,
                10**18,
                False,
                joueur,
                memo,
            )

        if afficher_console:
            ligne = "MiniMax : " + " ".join(
                str(scores[i]) if scores.get(i) is not None else " "
                for i in range(COLONNES)
            )
            print(ligne)

        if progress_callback is not None:
            progress_callback(dict(scores))

    valeurs_valides = [v for v in scores.values() if v is not None]
    if not valeurs_valides:
        return None, scores

    best = max(valeurs_valides)
    meilleures = [c for c, v in scores.items() if v == best]

    # tie-break stable : plus proche du centre
    meilleures.sort(key=lambda c: abs(c - (COLONNES // 2)))
    col_choisie = meilleures[0]
    return col_choisie, scores


# ============================================================
# PREDICTION + ANALYSE (soutenance)
# ============================================================
def prediction_label(score: int):
    if score >= WIN_SCORE - 1000:
        return "victoire"
    if score <= LOSE_SCORE + 1000:
        return "defaite"
    if abs(score) <= 60:
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
    Suffisant pour montrer les coups restants vers la victoire.
    """
    pv = []
    p = clone_plateau(plateau)
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
  




