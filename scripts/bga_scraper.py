import re
import time
from typing import List, Optional, Tuple, Dict

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class BGAScraper:
    def __init__(self, headless: bool = False):
        options = webdriver.ChromeOptions()

        profile_dir = "/home/hafida/chrome-selenium-profile"
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--disable-notifications")

        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1400,900")

        self.driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options,
        )
        self.wait = WebDriverWait(self.driver, 20)

    # ------------------------------------------------------------
    # LOGIN CHECK (heuristique DOM, pas basée sur des mots)
    # ------------------------------------------------------------
    def is_logged_in(self) -> bool:
        self.driver.get("https://boardgamearena.com/")
        try:
            WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#playerpanel, .player-name, .playeravatar, .bga-user-avatar, a[href*='logout']")
                )
            )
        except TimeoutException:
            pass

        # si on trouve un lien login explicite => pas connecté
        login_links = self.driver.find_elements(
            By.CSS_SELECTOR, "a[href*='account?section=login'], a[href*='login']"
        )
        if login_links:
            return False

        # sinon présence panel utilisateur
        user_panel = self.driver.find_elements(
            By.CSS_SELECTOR, "#playerpanel, .player-name, .playeravatar, .bga-user-avatar"
        )
        return len(user_panel) > 0

    # ------------------------------------------------------------
    # TABLE IDS (player last results)
    # ------------------------------------------------------------
    def get_table_ids_from_player_lastresults(self, player_id: str) -> List[int]:
        url = "https://boardgamearena.com/player?id={}&section=lastresults".format(player_id)
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)  # buffer (XHR)
        
        #scoll pour charger plus de resultats
        for _ in range (6):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1) 

        # Debug dump (utile si ça renvoie 0)
        ts = int(time.time())
        self.driver.save_screenshot(f"bga_lastresults_{player_id}_{ts}.png")
        with open(f"bga_lastresults_{player_id}_{ts}.html", "w", encoding="utf-8") as f:
            f.write(self.driver.page_source)

        table_ids = set()

        # Scan léger (a+button) + fallback HTML
        elems = self.driver.find_elements(By.CSS_SELECTOR, "a, button")
        for el in elems:
            for attr in ("href", "onclick", "data-table", "data-tableid", "data-id", "data-args"):
                val = el.get_attribute(attr)
                if not val:
                    continue

                m = re.search(r"table[=:](\d+)", val)
                if m:
                    table_ids.add(int(m.group(1)))

                m2 = re.search(r'"table[_ ]?id"\s*:\s*(\d+)', val)
                if m2:
                    table_ids.add(int(m2.group(1)))

        if not table_ids:
            html = self.driver.page_source
            for m in re.finditer(r"table[=:](\d+)", html):
                table_ids.add(int(m.group(1)))
            for m in re.finditer(r'"table[_ ]?id"\s*:\s*(\d+)', html):
                table_ids.add(int(m.group(1)))

        return sorted(table_ids)

    # ------------------------------------------------------------
    # MOVES (simple) : retourne [col_bga, ...] (col_bga est 1..9)
    # ------------------------------------------------------------
    def _extract_moves_from_page_text(self) -> List[int]:
        txt = self.driver.find_element(By.TAG_NAME, "body").text

        patterns = [
            r"\bcol(?:onne)?\s+(\d+)\b",
            r"\bcolumn\s+(\d+)\b",
            r"\bcol\s*:\s*(\d+)\b",
        ]

        moves: List[int] = []
        for line in txt.splitlines():
            for pat in patterns:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    moves.append(int(m.group(1)))
                    break
        return moves

    def get_moves_from_table(self, table_id: int) -> List[int]:
        url = "https://boardgamearena.com/gamereview?table={}".format(table_id)
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)

        moves: List[int] = []
        try:
            logs = self.driver.find_elements(By.CSS_SELECTOR, ".gamelogreview, .gamelogreview *")
            for el in logs:
                text = (el.text or "").strip()
                if not text:
                    continue
                m = re.search(r"\bcol(?:onne)?\s+(\d+)\b", text, re.IGNORECASE)
                if m:
                    moves.append(int(m.group(1)))
        except Exception:
            pass

        if not moves:
            moves = self._extract_moves_from_page_text()

        return moves

    # ------------------------------------------------------------
    # MOVES WITH COLORS (gère le swap) :
    # retourne [(couleur, col_bga), ...] avec couleur "R"/"J"
    #
    # Fonctionnement:
    # - On lit les lignes.
    # - Quand on voit "X joue maintenant en Jaune/Rouge", on met à jour le mapping pseudo -> couleur.
    # - Quand on voit "X place un pion ... colonne N", on enregistre (couleur_de_X, N).
    #
    # Si on n'arrive pas à déterminer la couleur du joueur au moment d'un coup -> retourne None
    # (pour éviter d'importer des données fausses).
    # ------------------------------------------------------------
    def get_moves_with_colors_from_table(self, table_id: int) -> Optional[List[Tuple[str, int]]]:
        url = "https://boardgamearena.com/gamereview?table={}".format(table_id)
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)

        text = self.driver.find_element(By.TAG_NAME, "body").text
        low = text.lower()
        
        if("relay" in low and "limit" in low) or ("limite" in low and "replay" in low) or ("too many" in low):
            print("Replay limite atteinte -> skip")
            return None
            
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        player_color: Dict[str, str] = {}  # pseudo_lower -> "R"/"J"
        moves: List[Tuple[str, int]] = []

        # Regex plus robuste (pseudos avec tirets/points)
        re_now = re.compile(r"^([^\s]+).*joue maintenant en\s+(jaune|rouge)", re.IGNORECASE)
        re_move = re.compile(r"^([^\s]+).*col(?:onne)?\s+(\d+)", re.IGNORECASE)

        for line in lines:
            low = line.lower()

            # ex: "kentino joue maintenant en Jaune !"
            m = re_now.search(line)
            if m:
                name = m.group(1).lower()
                color_word = m.group(2).lower()
                player_color[name] = ("J" if color_word == "jaune" else "R")
                continue

            # ex: "nougaro a inversé les couleurs" -> on n'a pas besoin d'agir ici
            if "inversé les couleurs" in low or "inverse les couleurs" in low:
                continue

            # ex: "kentino place un pion dans la colonne 5"
            m = re_move.search(line)
            if m:
                name = m.group(1).lower()
                col_bga = int(m.group(2))  # 1..9

                if name not in player_color:
                    # on ne sait pas sa couleur => on préfère ne pas importer cette partie
                    return None

                moves.append((player_color[name], col_bga))

        return moves

    # ------------------------------------------------------------
    # Aliases pour compat GUI
    # ------------------------------------------------------------
    def get_tables_from_player(self, player_id: str) -> List[int]:
        return self.get_table_ids_from_player_lastresults(player_id)

    def get_tables_from_player_lastresults(self, player_id: str) -> List[int]:
        return self.get_table_ids_from_player_lastresults(player_id)

    def close(self):
        self.driver.quit()


