import tkinter as tk
from tkinter import messagebox, simpledialog
from scripts.bga_scraper import BGAScraper

from tools.viewer_launcher import ouvrir_viewer
from core.database import (
    db_connexion,
    db_creer_partie,
    db_ajouter_coup,
    db_terminer_partie,
    db_supprimer_dernier_coup,
)
from core.config import (
    LIGNES,
    COLONNES,
    JOUEUR_DEPART,
    ROUGE,
    JAUNE,
    VIDE,
    sauvegarder_configuration,
    charger_configuration,
)
from core.modele import (
    creer_plateau,
    changer_joueur,
    coup_valide,
    jouer_coup,
    plateau_plein,
    verifier_victoire,
)
from core.ia import coup_aleatoire, coup_minimax, coup_bga
from core.sauvegarde import (
    generer_index_partie,
    sauvegarder_partie,
    lister_sauvegardes,
    charger_partie_par_index,
    annuler_dernier_coup,
)

# ============================================================
#  IMPORT BGA → BASE EXISTANTE (parties + coups)
# ============================================================

def importer_partie_bga(conn, table_id, moves):
    if not moves:
        return None
    
    # Vérifier si déjà importée
    cur = conn.cursor()
    cur.execute("SELECT id_partie FROM parties WHERE nom=%s", (f"BGA_{table_id}",))
    row = cur.fetchone()
    cur.close()

    if row:
        return row[0]  # déjà importée

    # Créer la partie
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO parties (nom, statut, nb_lignes, nb_colonnes, confiance)
        VALUES (%s, 'TERMINE', 9, 9, 4)
        RETURNING id_partie
    """, (f"BGA_{table_id}",))
    id_partie = cur.fetchone()[0]
    cur.close()

    # Insérer les coups
    for i, (couleur, col_bga) in enumerate(moves):
        col0 = col_bga - 1  # ✅ conversion BGA 1..9 -> interne 0..8
        if col0 < 0 or col0 >= 9:
            continue 
    
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO coups (id_partie, numero_coup, joueur, colonne)
            VALUES (%s, %s, %s, %s)
        """, (id_partie, i+1, joueur, col))
        cur.close()
    
    valid = [(couleur, col) for (couleur, col) in moves if 1 <= col <= 9]
    if not valid:
        return None
    moves = valid
    
    conn.commit()
    return id_partie


# ============================================================
#  GUI PRINCIPAL
# ============================================================

class Puissance4GUI(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.pack()

        self.mode = None
        self.profondeur = 0
        self.plateau = None
        self.joueur = None
        self.historique = []
        self.index_partie = None
        self.nom = ""
        self.types = {}

        self.cells = []
        self.col_labels = []
        self.score_labels = []

        self.frame_plateau = None
        self.label_info = None

        self.id_partie_pg = None
        self.conn_pg = None

        self.ligne_gagnante = None
        self.partie_terminee = False

        self.creer_menu()

    # ============================================================
    #  SCRAPPING BGA
    # ============================================================

    def fenetre_import_bga(self):
        win = tk.Toplevel(self)
        win.title("Importer parties BGA")
        win.geometry("600x500")

        tk.Label(win, text="ID BGA :", font=("Arial", 12)).pack(pady=5)
        entry_id = tk.Entry(win, font=("Arial", 12))
        entry_id.pack(pady=5)
        entry_id.insert(0, "94154229")

        frame_list = tk.Frame(win)
        frame_list.pack(fill="both", expand=True, pady=10)

        listbox = tk.Listbox(frame_list, selectmode="extended")
        listbox.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame_list, command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.config(yscrollcommand=scrollbar.set)

        text_logs = tk.Text(win, height=10)
        text_logs.pack(fill="x", pady=10)

        def log(msg):
            text_logs.insert("end", msg + "\n")
            text_logs.see("end")
            win.update()

        scraper = BGAScraper(headless=False)
        log("Selenium lancé (headless=False).")
        log(f"Connecté à BGA ? {scraper.is_logged_in()}")

        def charger_parties():
            listbox.delete(0, "end")
            player_id = entry_id.get().strip()
            log(f"Recherche des parties du joueur {player_id}...")

            tables = scraper.get_tables_from_player(player_id)
            for tid in tables:
                listbox.insert("end", f"Table {tid}")

            log(f"{len(tables)} parties trouvées.")

        def importer_selection():
            selection = listbox.curselection()
            if not selection:
                messagebox.showerror("Erreur", "Aucune partie sélectionnée.")
                return

            conn = db_connexion()

            for idx in selection:
                text = listbox.get(idx)
                tid = int(text.split()[1])

                log(f"Scraping table {tid}...")
                moves = scraper.get_moves_with_colors_from_table(tid)
                
                if not moves:
                    log("⚠️ Import annulé: replay inaccessible / limite atteinte / aucun coup.")
                    continue
                
                if moves is None :
                    log("⚠️ Partie ignorée: couleurs non déterminées (swap ou logs incomplets).")
                    continue
                log(f"{len(moves)} coups trouvés.")
                importer_partie_bga(conn, tid, moves)
                log(f"✔ Partie {tid} importée.")

            conn.close()
            messagebox.showinfo("OK", "Import terminé.")

        tk.Button(win, text="Charger les parties", command=charger_parties).pack(pady=5)
        tk.Button(win, text="Importer la sélection", command=importer_selection).pack(pady=5)
          
        def ouvrir_bga_login():
            scraper.driver.get("https://boardgamearena.com/")
            log("Ouvre BGA. Connecte-toi dans la fenêtre Chrome si nécessaire, puis re-clique 'Charger les parties'.")
        
        tk.Button(win, text="Ouvrir BGA (login)", command=ouvrir_bga_login).pack(pady=5)

    # ============================================================
    #  IA PRÉDICTIVE
    # ============================================================

    def fenetre_predictive(self):
        win = tk.Toplevel(self)
        win.title("Tester IA prédictive")
        win.geometry("400x250")

        tk.Label(win, text="Séquence de coups (ex: 3,4,3,5)", font=("Arial", 12)).pack(pady=10)

        entry = tk.Entry(win, font=("Arial", 14))
        entry.pack(pady=10, fill="x", padx=20)

        result_label = tk.Label(win, text="", font=("Arial", 14))
        result_label.pack(pady=20)

        def predire():
            seq_str = entry.get().strip()
            if not seq_str:
                result_label.config(text="Séquence vide.")
                return

            try:
                seq = [int(x) for x in seq_str.split(",")]
            except Exception:
                result_label.config(text="Format invalide.")
                return

            plateau = [[VIDE for _ in range(COLONNES)] for _ in range(LIGNES)]

            conn = db_connexion()
            try:
                coup = coup_bga(plateau, seq, conn, ROUGE)
                result_label.config(text=f"Prochain coup probable : {coup}")
            except Exception as e:
                result_label.config(text=f"Erreur : {e}")
            finally:
                conn.close()

        tk.Button(win, text="Prédire", command=predire, font=("Arial", 12)).pack(pady=10)

    # ============================================================
    #  MENU PRINCIPAL
    # ============================================================

    def creer_menu(self):
        if self.conn_pg is not None:
            try:
                self.conn_pg.close()
            except Exception:
                pass
            self.conn_pg = None

        for w in self.winfo_children():
            w.destroy()

        tk.Label(self, text="=== PUISSANCE 4 (GUI) ===", font=("Arial", 16)).pack(pady=10)

        tk.Button(self, text="1 Humain vs Humain",
                  command=lambda: self.demarrer_partie("H_H")).pack(fill="x", padx=20, pady=2)
        tk.Button(self, text="2 Humain vs IA aléatoire",
                  command=lambda: self.demarrer_partie("H_IA_ALEA")).pack(fill="x", padx=20, pady=2)
        tk.Button(self, text="3 Humain vs IA MiniMax",
                  command=lambda: self.demarrer_partie("H_IA_MINIMAX", demander_profondeur=True)).pack(fill="x", padx=20, pady=2)
        tk.Button(self, text="4 IA vs IA aléatoire",
                  command=lambda: self.demarrer_partie("IA_IA_ALEA")).pack(fill="x", padx=20, pady=2)
        tk.Button(self, text="5 IA vs IA MiniMax",
                  command=lambda: self.demarrer_partie("IA_IA_MINIMAX", demander_profondeur=True)).pack(fill="x", padx=20, pady=2)
        tk.Button(self, text="6 Humain vs IA BGA",
                  command=lambda: self.demarrer_partie("H_IA_BGA")).pack(fill="x", padx=20, pady=2)
        tk.Button(self, text="7 IA vs IA BGA",
                  command=lambda: self.demarrer_partie("IA_IA_BGA")).pack(fill="x", padx=20, pady=2)
        tk.Button(self, text="8 Reprendre partie",
                  command=self.menu_reprendre).pack(fill="x", padx=20, pady=2)

        tk.Button(self, text="Paramétrage",
                  command=self.parametrage_gui).pack(fill="x", padx=20, pady=10)
        tk.Button(self, text="Ouvrir Viewer",
                  command=ouvrir_viewer).pack(fill="x", padx=20, pady=10)
        tk.Button(self, text="Tester IA prédictive",
                  command=self.fenetre_predictive).pack(fill="x", padx=20, pady=10)

        tk.Button(self, text="Importer parties BGA",
                  command=self.fenetre_import_bga).pack(fill="x", padx=20, pady=10)


    # ================= PARAMETRAGE =================

    def parametrage_gui(self):
        lignes, colonnes, joueur_depart = charger_configuration()
        l = simpledialog.askinteger("Paramétrage", f"Lignes (actuel {lignes}, 4-12) :", minvalue=4, maxvalue=12)
        if l is None:
            return
        c = simpledialog.askinteger("Paramétrage", f"Colonnes (actuel {colonnes}, 4-12) :", minvalue=4, maxvalue=12)
        if c is None:
            return
        j = simpledialog.askstring("Paramétrage", f"Joueur qui commence (R/J, actuel {joueur_depart}) :")
        if j is None:
            return
        j = j.upper()

        if 4 <= l <= 12 and 4 <= c <= 12 and j in [ROUGE, JAUNE]:
            sauvegarder_configuration(l, c, j)
            messagebox.showinfo("OK", "Configuration sauvegardée.\nRelance l'application pour appliquer.")
        else:
            messagebox.showerror("Erreur", "Valeurs invalides.")

    # ================= DEMARRAGE PARTIE =================

    def demarrer_partie(self, mode, demander_profondeur=False, reprise=None):
        for w in self.winfo_children():
            w.destroy()

        self.ligne_gagnante = None
        self.partie_terminee = False

        self.mode = mode
        self.profondeur = 0
        if demander_profondeur:
            p = simpledialog.askinteger("MiniMax", "Profondeur MiniMax :", minvalue=1, maxvalue=7)
            if p is None:
                p = 2
            self.profondeur = p

        if reprise:
            self.plateau = reprise["plateau"]
            self.joueur = reprise["joueur"]
            self.historique = reprise["historique"]
            self.index_partie = reprise["index"]
            self.nom = reprise["nom"]
            self.id_partie_pg = None
            self.conn_pg = db_connexion()
        else:
            self.plateau = creer_plateau()
            self.joueur = JOUEUR_DEPART
            self.historique = []
            self.index_partie = generer_index_partie()
            self.nom = simpledialog.askstring("Nom de la partie", "Nom de la partie :")
            if not self.nom:
                self.nom = f"Partie {self.index_partie}"

            self.conn_pg = db_connexion()
            self.id_partie_pg = db_creer_partie(
                self.conn_pg,
                self.nom,
                nb_lignes=9,
                nb_colonnes=9,
                confiance=self.confiance_pour_mode(mode),
            )

        self.types = self.definir_types(mode)
        self.creer_widgets_plateau()
        self.mettre_a_jour_affichage()
        self.jouer_si_ia()

    def definir_types(self, mode):
        if mode == "H_H":
            return {ROUGE: "HUMAIN", JAUNE: "HUMAIN"}
        if mode == "H_IA_ALEA":
            return {ROUGE: "HUMAIN", JAUNE: "IA_ALEA"}
        if mode == "H_IA_MINIMAX":
            return {ROUGE: "HUMAIN", JAUNE: "IA_MINIMAX"}
        if mode == "IA_IA_ALEA":
            return {ROUGE: "IA_ALEA", JAUNE: "IA_ALEA"}
        if mode == "IA_IA_MINIMAX":
            return {ROUGE: "IA_MINIMAX", JAUNE: "IA_MINIMAX"}
        if mode == "H_IA_BGA":
            return {ROUGE: "HUMAIN", JAUNE: "IA_BGA"}
        if mode == "IA_IA_BGA":
            return {ROUGE: "IA_BGA", JAUNE: "IA_BGA"}
        return {ROUGE: "HUMAIN", JAUNE: "HUMAIN"}

    def confiance_pour_mode(self, mode):
        if mode == "H_H":
            return 3
        if mode == "H_IA_ALEA":
            return 1
        if mode == "H_IA_MINIMAX":
            return 2
        if mode == "IA_IA_ALEA":
            return 1
        if mode == "IA_IA_MINIMAX":
            return 2
        if mode == "H_IA_BGA":
            return 4
        if mode == "IA_IA_BGA":
            return 4
        return 3

    # ================= WIDGETS PLATEAU =================

    def creer_widgets_plateau(self):
        top = tk.Frame(self)
        top.pack(fill="x", pady=5)

        tk.Button(top, text="Menu", command=self.creer_menu).pack(side="left", padx=5)
        tk.Button(top, text="Annuler", command=self.annuler_coup_gui).pack(side="left", padx=5)
        tk.Button(top, text="Sauvegarder", command=self.sauvegarder_gui).pack(side="left", padx=5)

        self.label_info = tk.Label(top, text="")
        self.label_info.pack(side="right", padx=10)

        self.frame_plateau = tk.Frame(self, bg="#0047ab")
        self.frame_plateau.pack(pady=5)

        self.cells = []

        for l in range(LIGNES):
            row = []
            for c in range(COLONNES):
                cell = tk.Canvas(
                    self.frame_plateau,
                    width=50,
                    height=50,
                    bg="#0047ab",
                    highlightthickness=0
                )
                cell.grid(row=l, column=c, padx=1, pady=1)
                row.append(cell)
            self.cells.append(row)

        self.col_labels = []
        for c in range(COLONNES):
            lbl = tk.Label(
                self.frame_plateau,
                text=str(c),
                font=("Arial", 12, "bold"),
                bg="#e6e6e6",
                fg="black",
                width=4,
                height=1,
                relief="ridge",
                bd=1
            )
            lbl.grid(row=LIGNES, column=c, padx=1, pady=(4, 0))
            lbl.bind("<Button-1>", lambda e, col=c: self.jouer_colonne(col))
            lbl.bind("<Enter>", lambda e, col=c: self.surligner_colonne(col, True))
            lbl.bind("<Leave>", lambda e, col=c: self.surligner_colonne(col, False))
            self.col_labels.append(lbl)

        self.score_labels = []
        for c in range(COLONNES):
            lbl = tk.Label(
                self.frame_plateau,
                text="",
                font=("Arial", 10),
                fg="blue",
                bg="white",
                width=4,
                height=1
            )
            lbl.grid(row=LIGNES + 1, column=c, padx=1, pady=(0, 5))
            self.score_labels.append(lbl)

    # ================= AFFICHAGE =================

    def mettre_a_jour_affichage(self, scores=None):
        for l in range(LIGNES):
            for c in range(COLONNES):
                val = self.plateau[l][c]
                canvas = self.cells[l][c]
                canvas.delete("all")

                is_win = False
                if self.ligne_gagnante and (l, c) in self.ligne_gagnante:
                    is_win = True

                if val == ROUGE:
                    fill = "red"
                elif val == JAUNE:
                    fill = "yellow"
                else:
                    fill = "white"

                outline = "black"
                width = 1

                if is_win:
                    outline = "red"
                    width = 5

                canvas.create_oval(5, 5, 45, 45, fill=fill, outline=outline, width=width)

        self.label_info.config(text=f"Joueur : {self.joueur}")

        if scores:
            for c in range(COLONNES):
                v = scores.get(c)
                self.score_labels[c].config(text=str(v) if v is not None else "")
        else:
            for lbl in self.score_labels:
                lbl.config(text="")

    # ================= SURBRILLANCE COLONNES + PION FANTÔME =================

    def surligner_colonne(self, col, entrer):
        if self.partie_terminee:
            return
        if entrer:
            self.col_labels[col].config(bg="#cccccc")
            self.afficher_pion_fantome(col)
        else:
            self.col_labels[col].config(bg="#e6e6e6")
            self.effacer_pion_fantome(col)

    def afficher_pion_fantome(self, col):
        ligne = None
        for l in range(LIGNES - 1, -1, -1):
            if self.plateau[l][col] == VIDE:
                ligne = l
                break
        if ligne is None:
            return
        canvas = self.cells[ligne][col]
        canvas.delete("ghost")
        canvas.create_oval(5, 5, 45, 45, outline="gray", width=2, tags="ghost")

    def effacer_pion_fantome(self, col):
        for l in range(LIGNES):
            self.cells[l][col].delete("ghost")

    # ================= LOGIQUE DE JEU =================

    def jouer_colonne(self, col):
        if self.partie_terminee:
            return
        if self.types[self.joueur] != "HUMAIN":
            return
        if not coup_valide(self.plateau, col):
            return

        self.animer_chute(col, self.joueur, callback=self._fin_coup_humain)

    def _fin_coup_humain(self, col, joueur):
        self.historique.append({"joueur": joueur, "colonne": col})
        if self.id_partie_pg is not None and self.conn_pg is not None:
            numero = len(self.historique)
            db_ajouter_coup(self.conn_pg, self.id_partie_pg, numero, joueur, col)
        self.apres_coup()

    def apres_coup(self):
        if self.partie_terminee:
            return

        win = verifier_victoire(self.plateau, self.joueur)
        if win:
            self.ligne_gagnante = win
            self.partie_terminee = True
            self.mettre_a_jour_affichage()
            messagebox.showinfo("Fin", f"Victoire : {self.joueur}")

            if self.id_partie_pg is not None and self.conn_pg is not None:
                db_terminer_partie(self.conn_pg, self.id_partie_pg, self.joueur)

            sauvegarder_partie(
                self.index_partie,
                self.nom,
                self.plateau,
                self.joueur,
                self.historique,
                True,
            )
            return

        if plateau_plein(self.plateau):
            self.partie_terminee = True
            self.mettre_a_jour_affichage()
            messagebox.showinfo("Fin", "Match nul.")
            if self.id_partie_pg is not None and self.conn_pg is not None:
                db_terminer_partie(self.conn_pg, self.id_partie_pg, None)
            sauvegarder_partie(
                self.index_partie,
                self.nom,
                self.plateau,
                self.joueur,
                self.historique,
                True,
            )
            return

        self.joueur = changer_joueur(self.joueur)
        self.mettre_a_jour_affichage()
        self.jouer_si_ia()

    def jouer_si_ia(self):
        if self.partie_terminee:
            return
        t = self.types[self.joueur]
        if t == "IA_ALEA":
            self.master.after(200, self.coup_ia_aleatoire)
        elif t == "IA_MINIMAX":
            self.master.after(200, self.coup_ia_minimax)
        elif t == "IA_BGA":
            self.master.after(200, self.coup_ia_bga)

    def coup_ia_aleatoire(self):
        if self.partie_terminee:
            return
        col = coup_aleatoire(self.plateau)
        if col is None or not coup_valide(self.plateau, col):
            return
        self.animer_chute(col, self.joueur, callback=self._fin_coup_ia)

    def coup_ia_minimax(self):
        if self.partie_terminee:
            return

        def progress(scores):
            self.mettre_a_jour_affichage(scores=scores)
            self.update_idletasks()

        col, scores = coup_minimax(
            self.plateau,
            self.joueur,
            self.profondeur,
            progress_callback=progress,
        )
        self.mettre_a_jour_affichage(scores=scores)
        if col is None or not coup_valide(self.plateau, col):
            return
        self.master.after(200, lambda: self.animer_chute(col, self.joueur, callback=self._fin_coup_ia))

    def coup_ia_bga(self):
        # Construire la séquence des coups déjà joués
        if not hasattr(self, "historique") or not self.historique : 
            seq = []
        else:
            seq = [h["colonne"] for h in self.historique]

        # Appel IA BGA
        col = coup_bga(self.plateau, seq, self.conn_pg, self.joueur)

        # Jouer le coup
        self.jouer_coup(col)

    def jouer_coup(self, col):
        # 1. Vérifier validité
        if not coup_valide(self.plateau, col):
            return

        # 2. Jouer le coup sur le plateau (fonction du modèle)
        jouer_coup(self.plateau, col, self.joueur)

        # 3. Mettre à jour l’historique
        if not hasattr(self, "historique") or self.historique is None:
            self.historique = []

        self.historique.append({
            "joueur": self.joueur,
            "colonne": col
        })

        # 4. Changer de joueur
        self.joueur = changer_joueur(self.joueur)

        # 5. Mettre à jour l’affichage
        self.afficher_plateau(self.plateau)


    def _fin_coup_ia(self, col, joueur):
        self.historique.append({"joueur": joueur, "colonne": col})
        if self.id_partie_pg is not None and self.conn_pg is not None:
            numero = len(self.historique)
            db_ajouter_coup(self.conn_pg, self.id_partie_pg, numero, joueur, col)
        self.apres_coup()

    # ================= ANIMATION CHUTE =================

    def animer_chute(self, col, joueur, callback):
        ligne_finale = None
        for l in range(LIGNES - 1, -1, -1):
            if self.plateau[l][col] == VIDE:
                ligne_finale = l
                break
        if ligne_finale is None:
            return

        couleur = "red" if joueur == ROUGE else "yellow"

        def step(l_actuel, prev_l=None):
            self.effacer_pion_fantome(col)

            if prev_l is not None:
                canvas_prev = self.cells[prev_l][col]
                canvas_prev.delete("all")
                val_prev = self.plateau[prev_l][col]
                if val_prev == ROUGE:
                    fill_prev = "red"
                elif val_prev == JAUNE:
                    fill_prev = "yellow"
                else:
                    fill_prev = "white"
                outline_prev = "black"
                if self.ligne_gagnante and (prev_l, col) in self.ligne_gagnante:
                    outline_prev = "red"
                canvas_prev.create_oval(5, 5, 45, 45, fill=fill_prev, outline=outline_prev, width=1)

            canvas = self.cells[l_actuel][col]
            canvas.delete("all")
            canvas.create_oval(5, 5, 45, 45, fill=couleur, outline="black", width=1)

            if l_actuel < ligne_finale:
                self.master.after(30, lambda: step(l_actuel + 1, l_actuel))
            else:
                self.plateau[ligne_finale][col] = joueur
                self.mettre_a_jour_affichage()
                callback(col, joueur)

        step(0)

    # ================= ANNULER / SAUVEGARDER =================

    def annuler_coup_gui(self):
        if self.partie_terminee:
            return
        if self.types[self.joueur] != "HUMAIN":
            return

        # Annuler coup IA
        if len(self.historique) > 0:
            annuler_dernier_coup(self.plateau, self.historique)
            if self.id_partie_pg is not None and self.conn_pg is not None:
                db_supprimer_dernier_coup(self.conn_pg, self.id_partie_pg)

        # Annuler coup humain
        if len(self.historique) > 0:
            annuler_dernier_coup(self.plateau, self.historique)
            if self.id_partie_pg is not None and self.conn_pg is not None:
                db_supprimer_dernier_coup(self.conn_pg, self.id_partie_pg)

        for joueur, type_j in self.types.items():
            if type_j == "HUMAIN":
                self.joueur = joueur
                break

        self.ligne_gagnante = None
        self.mettre_a_jour_affichage()

    def sauvegarder_gui(self):
        sauvegarder_partie(
            self.index_partie,
            self.nom,
            self.plateau,
            self.joueur,
            self.historique,
            False,
        )
        messagebox.showinfo("Sauvegarde", "Partie sauvegardée.")

    # ================= REPRENDRE =================

    def menu_reprendre(self):
        for w in self.winfo_children():
            w.destroy()

        tk.Label(self, text="Reprendre une partie", font=("Arial", 14)).pack(pady=10)

        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(frame)
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame, command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.parties = lister_sauvegardes()
        for p in self.parties:
            term = "terminée" if p["terminee"] else "en cours"
            self.listbox.insert("end", f"{p['index']} - {p['nom']} ({term})")

        tk.Button(self, text="Reprendre", command=self.reprendre_selection).pack(pady=5)
        tk.Button(self, text="Retour menu", command=self.creer_menu).pack()

    def reprendre_selection(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        data = self.parties[sel[0]]
        if data["terminee"]:
            messagebox.showerror("Erreur", "Partie terminée.")
            return
        self.demarrer_partie("H_H", reprise=data)



