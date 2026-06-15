import threading
import webview
import subprocess
import time
import sys
import os

HERE = os.path.dirname(__file__)
APP = os.path.join(HERE, "bca_app.py")

def run_streamlit():
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        APP,
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    subprocess.run(cmd)

if __name__ == "__main__":
    t = threading.Thread(target=run_streamlit, daemon=True)
    t.start()
    time.sleep(3)
    webview.create_window("BCA Plate Analysis", "http://localhost:8501", width=1400, height=900)
    webview.start()
