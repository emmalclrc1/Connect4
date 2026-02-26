import sys

from core.console_game import main_console
import tkinter as tk
from ui.gui import Puissance4GUI


def main():
    # Choix rapide : console ou GUI
    print("Lancer en :")
    print("1 - Console")
    print("2 - Interface graphique (Tkinter)")
    choix = input("Choix (1/2) : ").strip()
    if choix == "1":
        while True:
            main_console()
            again = input("Rejouer ? (o/n) : ").lower()
            if again != "o":
                break
    else:
        root = tk.Tk()
        root.title("Puissance 4")
        app = Puissance4GUI(root)
        root.mainloop()


if __name__ == "__main__":
    main()







