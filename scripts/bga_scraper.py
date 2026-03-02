import os
import re
import time
from typing import Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from webdriver_manager.chrome import ChromeDriverManager


class BGAScraper:
    """
    Scraper BGA pour extraire une séquence de coups depuis un gamereview.

    Env utiles:
      - BGA_PROFILE_DIR : dossier chrome user-data (si tu veux être déjà loggée)
      - BGA_HEADLESS=1  : force headless
    """

    def __init__(self, headless: Optional[bool] = None):
        options = webdriver.ChromeOptions()

        # Profile persistant (si tu veux rester connecté)
        profile_dir = os.getenv("BGA_PROFILE_DIR", "").strip()
        if profile_dir:
            options.add_argument(f"--user-data-dir={profile_dir}")

        options.add_argument("--disable-notifications")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        if headless is None:
            headless = os.getenv("BGA_HEADLESS", "0") == "1"

        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1400,900")

        self.driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options,
        )
        self.wait = WebDriverWait(self.driver, 20)

    def _body_text(self) -> str:
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        return self.driver.find_element(By.TAG_NAME, "body").text

    def get_moves_with_colors_from_table(self, table_id: int) -> Optional[List[Tuple[str, int]]]:
        """
        Retourne [(couleur, col_bga), ...] avec couleur 'R'/'J' et col_bga en 1..N
        Si on ne peut pas déduire les couleurs => None (pour éviter import faux)
        """
        url = f"https://boardgamearena.com/gamereview?table={table_id}"
        self.driver.get(url)
        time.sleep(1)

        text = self._body_text()
        low = text.lower()

        # anti rate-limit BGA
        if ("replay" in low and "limit" in low) or ("limite" in low and "replay" in low) or ("too many" in low):
            return None

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        player_color: Dict[str, str] = {}
        moves: List[Tuple[str, int]] = []

        re_now = re.compile(r"^([^\s]+).*joue maintenant en\s+(jaune|rouge)", re.IGNORECASE)
        re_move = re.compile(r"^([^\s]+).*col(?:onne)?\s+(\d+)", re.IGNORECASE)

        for line in lines:
            m = re_now.search(line)
            if m:
                name = m.group(1).lower()
                color_word = m.group(2).lower()
                player_color[name] = ("J" if color_word == "jaune" else "R")
                continue

            m = re_move.search(line)
            if m:
                name = m.group(1).lower()
                col_bga = int(m.group(2))
                if name not in player_color:
                    return None
                moves.append((player_color[name], col_bga))

        return moves if moves else None

    def close(self):
        self.driver.quit()

