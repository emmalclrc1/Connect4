###############################################################
# Scraper Edge + Micro-service Flask
# Mission 4.1 : Import d'une seule partie BGA
# ➜ Lancement : py -3.10 scrape_bga_edge.py --serve
###############################################################

import os
import re
import time
import requests
from typing import List, Optional, Tuple, Dict

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

###############################################################
# CONFIG
###############################################################

USERNAME = os.environ["USERNAME"]
PROFILE_PATH = fr"C:\Users\{USERNAME}\AppData\Local\Microsoft\Edge\User Data\selenium_bga"

# ⭐️ TON API RENDER CORRECTE
API_URL = "https://connect4-vbdd.onrender.com/import-bga-auto"

###############################################################
# SELENIUM EDGE
###############################################################

def start_edge(headless: bool = False):
    opts = EdgeOptions()
    opts.use_chromium = True
    opts.add_argument(f"--user-data-dir={PROFILE_PATH}")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--start-maximized")

    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1400,900")

    return webdriver.Edge(options=opts)

###############################################################
# HELPERS : Warm-Up Render + POST robuste
###############################################################

def warm_up(api_url: str, tries: int = 3):
    """Réveille Render via /health + backoff."""
    health = api_url.replace("/import-bga-auto", "/health")

    for i in range(tries):
        try:
            r = requests.get(health, timeout=8)
            if r.ok:
                print(f"[warmup] /health OK ({r.status_code})")
                return True
        except Exception as e:
            print(f"[warmup] tentative {i+1}: {e}")

        time.sleep(1.5 * (i + 1))

    print("[warmup] service toujours froid, on continue")
    return False


def robust_post_json(url: str, payload: dict, attempts: int = 4):
    """POST solide avec retries exponentiels + timeout long."""
    for k in range(attempts):
        try:
            r = requests.post(url, json=payload, timeout=(10, 120))
            ct = (r.headers.get("content-type") or "").lower()

            if "json" in ct:
                return r, r.json()

            return r, None

        except Exception as e:
            print(f"[post] tentative {k+1}/{attempts}: {e}")
            time.sleep(2 ** k)

    return None, None

###############################################################
# Scraper class
###############################################################

class BGAScraper:
    def __init__(self, headless=False):
        self.driver = start_edge(headless=headless)
        self.wait = WebDriverWait(self.driver, 20)

    def _ensure_viewpoint(self):
        try:
            txt = self.driver.find_element(By.TAG_NAME, "body").text

            if "Choisissez votre point de vue" in txt or "Choose your point" in txt:
                cand = self.driver.find_elements(
                    By.XPATH,
                    "//a[normalize-space()='1er' or normalize-space()='1ᵉʳ']"
                )

                if cand:
                    self.driver.execute_script("arguments[0].click();", cand[0])
                    time.sleep(1)
        except Exception:
            pass

    def _full_log_text(self):
        self._ensure_viewpoint()

        for _ in range(6):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

        for _ in range(6):
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

        for _ in range(4):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.4)

        return self.driver.find_element(By.TAG_NAME, "body").text

    def get_moves_with_colors_from_table(self, table_id: int):
        url = f"https://boardgamearena.com/gamereview?table={table_id}&lang=fr"

        self.driver.get(url)
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)

        text_full = self._full_log_text()
        low = text_full.lower()

        if "never started" in low or "erreur inattendue" in low:
            return None

        if "puissance" not in low and "connect" not in low and "column" not in low:
            return "NOT_C4"

        lines = [l.strip() for l in text_full.splitlines() if l.strip()]

        re_now = re.compile(
            r"^\s*(.+?)\s+joue maintenant en\s+(jaune|rouge)\b",
            re.IGNORECASE
        )

        re_move = re.compile(
            r"^\s*(.+?)\s+(?:place|dépose|insère|joue)\s+(?:un\s+pion\s+)?"
            r"(?:dans\s+la\s+)?col(?:onne)?\s+(\d+)\b",
            re.IGNORECASE
        )

        re_move_en = re.compile(
            r"^\s*(.+?)\s+.*column\s+(\d+)\b",
            re.IGNORECASE
        )

        color_map = {}
        moves = []

        for line in lines:
            m = re_now.search(line)
            if m:
                name = m.group(1).strip().lower()
                col = m.group(2).lower()
                color_map[name] = "J" if col == "jaune" else "R"
                continue

            if "inversé les couleurs" in line.lower():
                continue

            m = re_move.search(line)
            if not m:
                m = re_move_en.search(line)

            if m:
                name = m.group(1).strip().lower()
                col = int(m.group(2))

                if name not in color_map:
                    continue

                moves.append((color_map[name], col))

        return moves if moves else None

    def get_moves_from_table(self, table_id: int):
        url = f"https://boardgamearena.com/gamereview?table={table_id}&lang=fr"

        self.driver.get(url)
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)

        whole = self._full_log_text()
        cols = []

        try:
            logs = self.driver.find_elements(By.CSS_SELECTOR, ".gamelogreview, .gamelogreview *")

            for el in logs:
                txt = (el.text or "").strip()
                if not txt:
                    continue

                for pat in (
                    r"\bcol(?:onne)?\s+(\d+)\b",
                    r"\bcolumn\s+(\d+)\b",
                    r"\bcol\s*[:# ]\s*(\d+)\b"
                ):
                    m = re.search(pat, txt, re.IGNORECASE)
                    if m:
                        cols.append(int(m.group(1)))
                        break
        except Exception:
            pass

        if not cols:
            for pat in (
                r"\bcol(?:onne)?\s+(\d+)\b",
                r"\bcolumn\s+(\d+)\b",
                r"\bcol\s*[:# ]\s*(\d+)\b"
            ):
                for m in re.finditer(pat, whole, re.IGNORECASE):
                    cols.append(int(m.group(1)))

        return cols

###############################################################
# FLASK MICRO-SERVICE
###############################################################

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
SCRAPER = None


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/import-bga-table", methods=["POST"])
def import_bga_table():
    global SCRAPER

    data = request.get_json(force=True)
    table_id = int(data.get("table", 0))

    if not table_id:
        return jsonify({"ok": False, "error": "table invalide"}), 400

    if SCRAPER is None:
        SCRAPER = BGAScraper(headless=False)

    mv = SCRAPER.get_moves_with_colors_from_table(table_id)

    if mv == "NOT_C4":
        return jsonify({"ok": False, "error": "pas Connect 4"}), 422

    if not mv:
        seq2 = SCRAPER.get_moves_from_table(table_id)

        if not seq2:
            return jsonify({"ok": False, "error": "aucun coup détecté"}), 422

        seq = seq2
        starts_with = "rouge"
    else:
        seq = [c for _, c in mv]
        starts_with = "rouge" if mv[0][0] == "R" else "jaune"

    payload = {
        "moves": seq,
        "starts_with": starts_with,
        "width": 9,
        "height": 9,
        "source": "bga",
        "confiance": 1
    }

    ###################################################################
    # WARM-UP RENDER + POST ROBUSTE
    ###################################################################
    warm_up(API_URL)
    r, api_json = robust_post_json(API_URL, payload)

    if r is None:
        return jsonify({"ok": False, "error": "backend unreachable"}), 502

    if api_json is None:
        api_json = {
            "imported": False,
            "reason": "non_json",
            "status": r.status_code,
            "text": (r.text or "")[:500]
        }

    print("DEBUG POST ->", API_URL)
    print("PAYLOAD ->", payload)
    print("STATUS ->", r.status_code)
    print("HEADERS ->", dict(r.headers))
    print("BODY ->", (r.text or "")[:500])

    return jsonify({
        "ok": True,
        "table": table_id,
        "seq": seq,
        "starts_with": starts_with,
        "api": api_json
    })

###############################################################
# MAIN: MODE SERVICE
###############################################################

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        print("🌐 Scraper Edge actif : http://127.0.0.1:5001")
        app.run(host="127.0.0.1", port=5001, debug=False)
    else:
        print("Lance : py -3.10 scrape_bga_edge.py --serve")
