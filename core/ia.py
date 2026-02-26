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
    """Retourne une colonne valide choisie au hasard."""
    colonnes_valides = [c for c in range(COLONNES) if coup_valide(plateau, c)]
    return random.choice(colonnes_valides) if colonnes_valides else None


# ============================================================
# IA BGA (APPRENTISSAGE PAR DONNÉES)
# ============================================================

def coup_bga(plateau, coups_deja_joues, connexion_pg, joueur):
    prefix = ",".join(str(c) for c in coups_deja_joues)

    cur = connexion_pg.cursor()

    if prefix:
        # Matching correct
        cur.execute(
            """
            SELECT sequence, confiance FROM parties
            WHERE sequence IS NOT NULL
              AND sequence <> ''
              AND sequence LIKE %s;
            """,
            (prefix + "%",),
        )
    else:
        # Toutes les parties valides
        cur.execute(
            """
            SELECT sequence, confiance FROM parties
            WHERE sequence IS NOT NULL
              AND sequence <> '';
            """
        )

    rows = cur.fetchall()

    if not rows:
        col, _ = coup_minimax(plateau, joueur, profondeur=2)
        return col

    stats = {}
    for (seq, conf) in rows:
        seq_list = [int(x) for x in seq.split(",") if x != ""]
        if len(seq_list) > len(coups_deja_joues):
            next_col = seq_list[len(coups_deja_joues)]
            if 0 <= next_col < COLONNES and coup_valide(plateau, next_col):
                poids = max(1, conf)  # confiance = poids
                stats[next_col] = stats.get(next_col, 0) + poids

    if not stats:
        col, _ = coup_minimax(plateau, joueur, profondeur=2)
        return col

    best_col = max(stats, key=stats.get)
    return best_col


# ============================================================
# HEURISTIQUE AVANCÉE
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

    # Bonus centre
    centre_col = COLONNES // 2
    centre_count = sum(1 for l in range(LIGNES) if plateau[l][centre_col] == joueur)
    score += centre_count * 6

    # Lignes
    for l in range(LIGNES):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    # Colonnes
    for c in range(COLONNES):
        for l in range(LIGNES - 3):
            fenetre = [plateau[l + i][c] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    # Diagonales montantes
    for l in range(LIGNES - 3):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l + i][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    # Diagonales descendantes
    for l in range(3, LIGNES):
        for c in range(COLONNES - 3):
            fenetre = [plateau[l - i][c + i] for i in range(4)]
            score += evaluer_fenetre(fenetre, joueur)

    return score


# ============================================================
# MINIMAX AVEC ALPHA-BETA
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


# ============================================================
# CHOIX DU COUP MINIMAX
# ============================================================

def coup_minimax(plateau, joueur, profondeur, progress_callback=None, afficher_console=False):
    scores = {}

    for c in range(COLONNES):
        if not coup_valide(plateau, c):
            scores[c] = None
            continue

        # Simulation du coup
        cp = [row[:] for row in plateau]
        jouer_coup(cp, c, joueur)

        # Si ce coup donne déjà la victoire, on peut le marquer très haut
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

    # Choix du meilleur coup
    valeurs_valides = [v for v in scores.values() if v is not None]
    if not valeurs_valides:
        return None, scores

    best = max(valeurs_valides)
    meilleures = [c for c, v in scores.items() if v == best]
    col_choisie = random.choice(meilleures)

    return col_choisie, scores





