import tkinter as tk
from tkinter import messagebox, filedialog
import psycopg2
import os

# Plateau fixe 9x9 (exigence du prof)
LIGNES = 9
COLONNES = 9
VIDE = "."


class ViewerApp(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.pack(fill="both", expand=True)

        self.master.title("Connect4 - Viewer")
        self.master.geometry("1100x700")

        # Connexion PostgreSQL
        self.conn = psycopg2.connect(
            dbname="connect4_db",
            user="connect4_user",
            password="connect4",
            host="127.0.0.1",
            port="5432"
        )
        self.cur = self.conn.cursor()

        self.coups = []
        self.index_coup = 0
        self.plateau_replay = None
        self.positions_gagnantes = None
        self.symetrie_active = False

        self.creer_widgets()
        self.charger_parties()

    # ================== UI ==================

    def creer_widgets(self):
        frame_left = tk.Frame(self, width=250)
        frame_left.pack(side="left", fill="y")

        tk.Label(frame_left, text="Liste des parties", font=("Arial", 14)).pack(pady=10)

        self.listbox_parties = tk.Listbox(frame_left, width=40, height=25)
        self.listbox_parties.pack(padx=10, pady=10)
        self.listbox_parties.bind("<<ListboxSelect>>", self.selection_partie)

        tk.Button(frame_left, text="Exporter partie", command=self.exporter_partie).pack(pady=5)
        tk.Button(frame_left, text="Importer partie", command=self.importer_partie).pack(pady=5)

        self.label_statut = tk.Label(frame_left, text="Statut : ", font=("Arial", 12))
        self.label_statut.pack(pady=5)

        # Plateau
        self.frame_plateau = tk.Frame(self, bg="#0047ab")
        self.frame_plateau.pack(side="left", fill="both", expand=True)

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
                cell.grid(row=l, column=c, padx=2, pady=2)
                row.append(cell)
            self.cells.append(row)

        self.afficher_plateau_vide()

        # Navigation
        frame_nav = tk.Frame(self.frame_plateau, bg="white")
        frame_nav.grid(row=LIGNES, column=0, columnspan=COLONNES, pady=10)

        self.btn_start = tk.Button(frame_nav, text="⟪ Début", command=self.afficher_debut, state="disabled")
        self.btn_start.pack(side="left", padx=10)

        self.btn_prev = tk.Button(frame_nav, text="⟨ Précédent", command=self.coup_precedent, state="disabled")
        self.btn_prev.pack(side="left", padx=10)

        self.label_coup = tk.Label(frame_nav, text="Coup : 0")
        self.label_coup.pack(side="left", padx=10)

        self.btn_next = tk.Button(frame_nav, text="Suivant ⟩", command=self.coup_suivant, state="disabled")
        self.btn_next.pack(side="left", padx=10)

        self.btn_end = tk.Button(frame_nav, text="Fin ⟫", command=self.afficher_fin, state="disabled")
        self.btn_end.pack(side="left", padx=10)

        self.btn_sym = tk.Button(frame_nav, text="Symétrie ↔", command=self.toggle_symetrie, state="disabled")
        self.btn_sym.pack(side="left", padx=10)

    # ================== DB / LISTE PARTIES ==================

    def charger_parties(self):
        self.listbox_parties.delete(0, tk.END)
        self.cur.execute("SELECT id_partie, nom, statut FROM parties ORDER BY id_partie;")
        for idp, nom, statut in self.cur.fetchall():
            self.listbox_parties.insert(tk.END, f"{idp} | {nom} | {statut}")

    def charger_coups(self, id_partie):
        self.cur.execute("""
            SELECT numero_coup, joueur, colonne
            FROM coups
            WHERE id_partie = %s
            ORDER BY numero_coup;
        """, (id_partie,))
        return self.cur.fetchall()

    # ================== PLATEAU / AFFICHAGE ==================

    def plateau_vide(self):
        return [[VIDE for _ in range(COLONNES)] for _ in range(LIGNES)]

    def appliquer_coup(self, plateau, joueur, colonne):
        if len(plateau[0]) == 9 and 1 <= colonne <= 9:
            colonne -=1
        
        if colonne < 0 or colonne >= len(plateau[0]):
             print(f"[VIEWER] Colonne invalide ignorée: {colonne}")
             return

        for l in range(LIGNES - 1, -1, -1):
            if plateau[l][colonne] == VIDE:
                plateau[l][colonne] = joueur
                break

    def afficher_plateau_vide(self):
        self.positions_gagnantes = None
        for l in range(LIGNES):
            for c in range(COLONNES):
                canvas = self.cells[l][c]
                canvas.delete("all")
                canvas.create_oval(5, 5, 45, 45, fill="white", outline="#003580", width=1)

    def afficher_plateau(self, plateau):
        gagnantes = set(self.positions_gagnantes or [])
        for l in range(LIGNES):
            for c in range(COLONNES):
                val = plateau[l][c]
                canvas = self.cells[l][c]
                canvas.delete("all")

                if val == "R":
                    fill = "red"
                elif val == "J":
                    fill = "yellow"
                else:
                    fill = "white"

                if (l, c) in gagnantes:
                    canvas.create_oval(5, 5, 45, 45, fill=fill, outline="red", width=4)
                else:
                    canvas.create_oval(5, 5, 45, 45, fill=fill, outline="#003580", width=1)

    def trouver_ligne_gagnante(self, plateau):
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for l in range(LIGNES):
            for c in range(COLONNES):
                joueur = plateau[l][c]
                if joueur not in ("R", "J"):
                    continue
                for dl, dc in directions:
                    pos = []
                    ok = True
                    for k in range(4):
                        nl = l + dl * k
                        nc = c + dc * k
                        if not (0 <= nl < LIGNES and 0 <= nc < COLONNES):
                            ok = False
                            break
                        if plateau[nl][nc] != joueur:
                            ok = False
                            break
                        pos.append((nl, nc))
                    if ok:
                        return joueur, pos
        return None, None

    # ================== NAVIGATION ==================

    def selection_partie(self, event):
        selection = self.listbox_parties.curselection()
        if not selection:
            return

        index = selection[0]
        texte = self.listbox_parties.get(index)
        id_partie = int(texte.split("|")[0].strip())

        # statut
        self.cur.execute("SELECT statut FROM parties WHERE id_partie=%s;", (id_partie,))
        statut = self.cur.fetchone()[0]
        self.label_statut.config(text=f"Statut : {statut}")

        self.coups = self.charger_coups(id_partie)
        self.plateau_replay = self.plateau_vide()
        self.index_coup = 0
        self.positions_gagnantes = None
        self.symetrie_active = False

        self.afficher_plateau(self.plateau_replay)

        # activer navigation
        self.btn_start.config(state="normal")
        self.btn_end.config(state="normal")
        self.btn_sym.config(state="normal")
        self.btn_prev.config(state="disabled")
        self.btn_next.config(state="normal" if len(self.coups) > 0 else "disabled")
        self.label_coup.config(text="Coup : 0")

    def coup_suivant(self):
        if self.index_coup >= len(self.coups):
            return
        _, joueur, colonne = self.coups[self.index_coup]
        self.appliquer_coup(self.plateau_replay, joueur, colonne)
        self.index_coup += 1
        self.positions_gagnantes = None

        # Si on vient de jouer le dernier coup → afficher ligne gagnante
        if self.index_coup == len(self.coups):
            _, pos = self.trouver_ligne_gagnante(self.plateau_replay)
            self.positions_gagnantes = pos

        self.label_coup.config(text=f"Coup : {self.index_coup}")
        self.btn_prev.config(state="normal")
        if self.index_coup == len(self.coups):
            self.btn_next.config(state="disabled")

        self.redessiner_avec_symetrie()

    def coup_precedent(self):
        if self.index_coup <= 0:
            return
        self.plateau_replay = self.plateau_vide()
        self.positions_gagnantes = None

        for i in range(self.index_coup - 1):
            _, joueur, colonne = self.coups[i]
            self.appliquer_coup(self.plateau_replay, joueur, colonne)

        self.index_coup -= 1
        self.label_coup.config(text=f"Coup : {self.index_coup}")
        self.btn_next.config(state="normal")
        if self.index_coup == 0:
            self.btn_prev.config(state="disabled")

        self.redessiner_avec_symetrie()

    def afficher_debut(self):
        self.index_coup = 0
        self.plateau_replay = self.plateau_vide()
        self.positions_gagnantes = None
        self.label_coup.config(text="Coup : 0")
        self.btn_prev.config(state="disabled")
        self.btn_next.config(state="normal" if len(self.coups) > 0 else "disabled")
        self.redessiner_avec_symetrie()

    def afficher_fin(self):
        self.plateau_replay = self.plateau_vide()
        for _, joueur, colonne in self.coups:
            self.appliquer_coup(self.plateau_replay, joueur, colonne)

        self.index_coup = len(self.coups)
        _, pos = self.trouver_ligne_gagnante(self.plateau_replay)
        self.positions_gagnantes = pos

        self.label_coup.config(text=f"Coup : {self.index_coup}")
        self.btn_next.config(state="disabled")
        self.btn_prev.config(state="normal")

        self.redessiner_avec_symetrie()

    # ================== SYMÉTRIE ==================

    def toggle_symetrie(self):
        self.symetrie_active = not self.symetrie_active
        self.redessiner_avec_symetrie()

    def redessiner_avec_symetrie(self):
        plateau = self.plateau_replay

        if self.symetrie_active:
            plateau = [row[::-1] for row in plateau]
            if self.positions_gagnantes:
                self.afficher_plateau_symetrique(plateau)
                return

        self.afficher_plateau(plateau)

    def afficher_plateau_symetrique(self, plateau_sym):
        gagnantes = set()
        if self.positions_gagnantes:
            gagnantes = {(l, COLONNES - 1 - c) for (l, c) in self.positions_gagnantes}

        for l in range(LIGNES):
            for c in range(COLONNES):
                val = plateau_sym[l][c]
                canvas = self.cells[l][c]
                canvas.delete("all")

                if val == "R":
                    fill = "red"
                elif val == "J":
                    fill = "yellow"
                else:
                    fill = "white"

                if (l, c) in gagnantes:
                    canvas.create_oval(5, 5, 45, 45, fill=fill, outline="red", width=4)
                else:
                    canvas.create_oval(5, 5, 45, 45, fill=fill, outline="#003580", width=1)

    # ================== EXPORT ==================

    def exporter_partie(self):
        selection = self.listbox_parties.curselection()
        if not selection:
            return
        index = selection[0]
        texte = self.listbox_parties.get(index)
        id_partie = int(texte.split("|")[0].strip())

        self.cur.execute("SELECT nom, statut, sequence FROM parties WHERE id_partie=%s;", (id_partie,))
        row = self.cur.fetchone()
        if not row:
            messagebox.showerror("Erreur", "Partie introuvable.")
            return
        nom, statut, sequence = row

        coups = self.charger_coups(id_partie)

        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Fichiers texte", "*.txt")])
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"ID: {id_partie}\n")
            f.write(f"Nom: {nom}\n")
            f.write(f"Statut: {statut}\n")
            f.write(f"Sequence: {sequence if sequence else ''}\n\n")
            for numero, joueur, col in coups:
                f.write(f"{numero} {joueur} {col}\n")

        messagebox.showinfo("Export", "Partie exportée.")

    # ================== IMPORT ==================

    def importer_partie(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers texte", "*.txt")])
        if not path:
            return

        nom_fichier = os.path.basename(path)
        nom_sans_ext = os.path.splitext(nom_fichier)[0]

        # CAS 1 : fichier vide → nom = séquence
        try:
            is_empty = os.path.getsize(path) == 0
        except OSError:
            is_empty = False

        if nom_sans_ext.isdigit() and is_empty:
            sequence_list = [int(x) for x in nom_sans_ext]
            sequence_str = ",".join(str(x) for x in sequence_list)

            sym_list = [(COLONNES - 1) - c for c in sequence_list]
            sym_sequence_str = ",".join(str(x) for x in sym_list)

            # Doublons
            self.cur.execute("SELECT id_partie FROM parties WHERE nom = %s;", (nom_sans_ext,))
            if self.cur.fetchone():
                messagebox.showinfo("Info", "Cette partie est déjà enregistrée (même nom).")
                return

            self.cur.execute("""
                SELECT id_partie FROM parties
                WHERE sequence = %s OR sequence = %s;
            """, (sequence_str, sym_sequence_str))
            if self.cur.fetchone():
                messagebox.showinfo("Info", "Cette partie (ou sa symétrie) est déjà enregistrée.")
                return

            # Insertion partie
            self.cur.execute("""
                INSERT INTO parties (nom, statut, sequence)
                VALUES (%s, %s, %s)
                RETURNING id_partie;
            """, (nom_sans_ext, "TERMINE", sequence_str))
            id_partie = self.cur.fetchone()[0]

            # Insertion coups
            for i, col in enumerate(sequence_list):
                joueur = "R" if i % 2 == 0 else "J"
                self.cur.execute("""
                    INSERT INTO coups (id_partie, numero_coup, joueur, colonne)
                    VALUES (%s, %s, %s, %s);
                """, (id_partie, i + 1, joueur, col))

            self.conn.commit()
            messagebox.showinfo("Import", "Partie importée depuis le nom du fichier.")
            self.charger_parties()
            return

        # CAS 2 : import classique
        with open(path, "r", encoding="utf-8") as f:
            lignes = f.read().strip().splitlines()

        if len(lignes) < 4:
            messagebox.showerror("Erreur", "Fichier invalide.")
            return

        try:
            nom = lignes[1].split(":", 1)[1].strip()
            statut = lignes[2].split(":", 1)[1].strip()
            seq_line = lignes[3].split(":", 1)[1].strip()
            sequence_str = seq_line if seq_line else None
        except Exception:
            messagebox.showerror("Erreur", "Format de fichier invalide.")
            return

        coups_lignes = lignes[5:] if len(lignes) > 5 else []
        sequence_list = []
        for ligne in coups_lignes:
            if not ligne.strip():
                continue
            try:
                numero, joueur, col = ligne.split()
                sequence_list.append(int(col))
            except ValueError:
                messagebox.showerror("Erreur", f"Ligne invalide : {ligne}")
                return

        if not sequence_str and sequence_list:
            sequence_str = ",".join(str(x) for x in sequence_list)

        # Séquence symétrique
        if sequence_str:
            seq_nums = [int(x) for x in sequence_str.split(",")]
            sym_nums = [(COLONNES - 1) - c for c in seq_nums]
            sym_sequence_str = ",".join(str(x) for x in sym_nums)
        else:
            sym_sequence_str = None

        # Doublons par nom
        self.cur.execute("SELECT id_partie FROM parties WHERE nom = %s;", (nom,))
        if self.cur.fetchone():
            messagebox.showinfo("Info", "Cette partie est déjà enregistrée (même nom).")
            return

        # Doublons par séquence exacte
        self.cur.execute("SELECT id_partie FROM parties WHERE sequence = %s;", (sequence_str,))
        if self.cur.fetchone():
            messagebox.showinfo("Info", "Cette partie existe déjà (séquence identique).")
            return

        # Doublons par séquence symétrique
        if sym_sequence_str:
            self.cur.execute("SELECT id_partie FROM parties WHERE sequence = %s;", (sym_sequence_str,))
            if self.cur.fetchone():
                messagebox.showinfo("Info", "Cette partie existe déjà (symétrie détectée).")
                return

        # Si tout est OK → insertion
        self.cur.execute("""
            INSERT INTO parties (nom, nb_lignes, nb_colonnes, sequence, confiance, statut)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (nom, LIGNES, COLONNES, sequence_str, 1, "TERMINE"))

        self.conn.commit()
        messagebox.showinfo("Succès", "Partie enregistrée avec succès.")
        self.charger_parties()
        return  # fin de l'import

# Fin de la classe Viewer
# ------------------------------------------------------------

if __name__ == "__main__":
    import tkinter as tk
    root = tk.Tk()
    app = ViewerApp(root)
    root.mainloop()


