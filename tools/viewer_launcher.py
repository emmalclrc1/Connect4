import subprocess
import sys
import os

def ouvrir_viewer():
    chemin = os.path.join(os.path.dirname(__file__), "viewer.py")
    subprocess.Popen([sys.executable, chemin])


      




