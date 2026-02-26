import time
import re
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager


class BGAScraper:

    def __init__(self, headless=False):
        options = webdriver.ChromeOptions()

        # 🔥 Profil Chrome dédié à Selenium
        profile_dir = "/home/hafida/chrome-selenium-profile"
        options.add_argument(f"--user-data-dir={profile_dir}")

        if headless:
            options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )

    def get_tables_from_player(self, player_id: str):
        url = f"https://boardgamearena.com/player?id={player_id}&section=lastresults"
        self.driver.get(url)
        time.sleep(3)

        links = self.driver.find_elements(By.TAG_NAME, "a")
        table_ids = set()

        for link in links:
            href = link.get_attribute("href")
            text = link.text.lower()

            if "9x9" in text and href and "gamereview?table=" in href:
                m = re.search(r"table=(\d+)", href)
                if m:
                    table_ids.add(int(m.group(1)))

        return sorted(table_ids)

    def get_moves_from_table(self, table_id: int):
        url = f"https://boardgamearena.com/gamereview?table={table_id}"
        self.driver.get(url)
        time.sleep(2)

        logs = self.driver.find_elements(By.CLASS_NAME, "gamelogreview")
        moves = []

        for log in logs:
            text = log.text.strip()
            m = re.search(r"col(?:onne)?\s+(\d+)", text, re.IGNORECASE)
            if m:
                moves.append(int(m.group(1)))

        return moves

    def close(self):
        self.driver.quit()




