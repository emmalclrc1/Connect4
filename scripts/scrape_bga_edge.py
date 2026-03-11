###############################################################
# Scraper Linux/Windows + Micro-service Flask
# Import d'une seule partie BGA
#
# Linux :
#   python3 scripts/scrape_bga_edge.py --serve
#
# Windows :
#   py -3.10 scripts\scrape_bga_edge.py --serve
###############################################################

import os
import re
import sys
import time
import shutil
import requests
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By

# Edge
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

# Chrome / Chromium fallback
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

###############################################################
# CONFIG
###############################################################

API_URL = os.environ.get(
    "BGA_API_URL",
    "https://connect4-vbdd.onrender.com/import-bga-auto"
)

HOST = os.environ.get("BGA_SCRAPER_HOST", "127.0.0.1")
PORT = int(os.environ.get("BGA_SCRAPER_PORT", "5001"))

# Si tu veux forcer edge/chrome :
# export BROWSER=edge
# export BROWSER=chrome
BROWSER = (os.environ.get("BROWSER") or "auto").lower()

# Chemins optionnels vers les drivers
EDGE_DRIVER_PATH = os.environ.get("EDGE_DRIVER_PATH", "").strip()
CHROME_DRIVER_PATH = os.environ.get("CHROME_DRIVER_PATH", "").strip()

# Profil Linux par défaut
LINUX_PROFILE_DIR = os.environ.get(
    "BGA_PROFILE_DIR",
    str(Path.home() / ".config" / "selenium_bga")
)

# Profil Windows par défaut
if os.name == "nt":
    USERNAME = os.environ.get("USERNAME", "User")
    WINDOWS_PROFILE_DIR = fr"C:\Users\{USERNAME}\AppData\Local\Microsoft\Edge\User Data\selenium_bga"
else:
    WINDOWS_PROFILE_DIR = ""


###############################################################
# HELPERS
###############################################################

def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_windows() -> bool:
    return os.name == "nt"


def ensure_profile_dir(path_str: str):
    Path(path_str).mkdir(parents=True, exist_ok=True)


def warm_up(api_url: str, tries: int = 3):
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


def find_binary(candidates):
    for name in candidates:
        p = shutil.which(name)
        if p:
            return p
    return None


###############################################################
# NAVIGATEUR
###############################################################

def start_edge(headless: bool = False):
    profile_path = WINDOWS_PROFILE_DIR if is_windows() else LINUX_PROFILE_DIR
    ensure_profile_dir(profile_path)

    opts = EdgeOptions()
    opts.use_chromium = True
    opts.add_argument(f"--user-data-dir={profile_path}")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1400,900")

    # Linux : essaie de trouver le binaire edge si installé
    if is_linux():
        edge_bin = find_binary(["microsoft-edge", "microsoft-edge-stable"])
        if edge_bin:
            opts.binary_location = edge_bin

    # Si un driver explicite est fourni, on l'utilise
    if EDGE_DRIVER_PATH:
        service = EdgeService(EDGE_DRIVER_PATH)
        return webdriver.Edge(service=service, options=opts)

    # Sinon Selenium essaie de le résoudre automatiquement
    return webdriver.Edge(options=opts)


def start_chrome(headless: bool = False):
    profile_path = str(Path.home() / ".config" / "selenium_bga_chrome")
    ensure_profile_dir(profile_path)

    opts = ChromeOptions()
    opts.add_argument(f"--user-data-dir={profile_path}")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1400,900")

    chrome_binary = os.environ.get("CHROME_BINARY", "").strip()
    if chrome_binary:
        opts.binary_location = chrome_binary
    else:
        for candidate in [
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]:
            if os.path.exists(candidate):
                opts.binary_location = candidate
                break

    if CHROME_DRIVER_PATH:
        service = ChromeService(CHROME_DRIVER_PATH)
        return webdriver.Chrome(service=service, options=opts)

    return webdriver.Chrome(options=opts)


def start_browser(headless: bool = False):
    errors = []

    if BROWSER in ("edge", "auto"):
        try:
            print("[browser] tentative Edge")
            return start_edge(headless=headless)
        except Exception as e:
            errors.append(f"Edge: {e}")

    if BROWSER in ("chrome", "chromium", "auto"):
        try:
            print("[browser] tentative Chrome/Chromium")
            return start_chrome(headless=headless)
        except Exception as e:
            errors.append(f"Chrome: {e}")

    raise RuntimeError("Impossible de lancer un navigateur Selenium.\n" + "\n".join(errors))


###############################################################
# Scraper class
###############################################################

class BGAScraper:
    def __init__(self, headless=False):
        self.driver = start_browser(headless=headless)
        self.wait = WebDriverWait(self.driver, 20)

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

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
        try:
            SCRAPER = BGAScraper(headless=False)
        except Exception as e:
            return jsonify({
                "ok": False,
                "error": f"Impossible de lancer Selenium : {e}"
            }), 500

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
# MAIN
###############################################################

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        print(f"🌐 Scraper Selenium actif : http://{HOST}:{PORT}")
        print(f"[config] browser={BROWSER} api={API_URL}")
        app.run(host=HOST, port=PORT, debug=False)
    else:
        print("Lance : python3 scripts/scrape_bga_edge.py --serve")
