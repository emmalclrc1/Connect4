from .config import VIDE, ROUGE, JAUNE, LIGNES, COLONNES


def creer_plateau():
    """Crée un plateau vide selon la configuration actuelle."""
    return [[VIDE for _ in range(COLONNES)] for _ in range(LIGNES)]


def afficher_plateau_console(plateau):
    print()
    for l in plateau:
        print(" ".join(l))
    print(" ".join(str(i) for i in range(COLONNES)))
    print()


def changer_joueur(j):
    return JAUNE if j == ROUGE else ROUGE


def coup_valide(plateau, col):
    """Un coup est valide si la colonne existe et que la case du haut est vide."""
    return 0 <= col < COLONNES and plateau[0][col] == VIDE


def jouer_coup(plateau, col, joueur):
    """
    Joue un coup dans la colonne donnée.
    Retourne la ligne où le pion est tombé.
    """
    for l in range(LIGNES - 1, -1, -1):
        if plateau[l][col] == VIDE:
            plateau[l][col] = joueur
            return l  # <-- très utile pour le GUI / IA
    return None  # colonne pleine (ne devrait pas arriver si coup_valide est utilisé)


def plateau_plein(plateau):
    """Retourne True si aucune colonne n'est jouable."""
    return all(plateau[0][c] != VIDE for c in range(COLONNES))


def verifier_victoire(plateau, joueur):
    """
    Vérifie si *ce joueur* a 4 pions alignés.
    Retourne la liste des positions gagnantes ou None.
    """
    directions = [(0, 1), (1, 0), (1, 1), (-1, 1)]

    for l in range(LIGNES):
        for c in range(COLONNES):

            if plateau[l][c] != joueur:
                continue

            for dl, dc in directions:
                pos = [(l, c)]
                for i in range(1, 4):
                    nl, nc = l + dl * i, c + dc * i
                    if (
                        0 <= nl < LIGNES
                        and 0 <= nc < COLONNES
                        and plateau[nl][nc] == joueur
                    ):
                        pos.append((nl, nc))
                    else:
                        break

                if len(pos) == 4:
                    return pos

    return None


def marquer_ligne_gagnante(plateau, pos):
    """Ne modifie plus le plateau. Le GUI gère l'affichage."""
    return pos



