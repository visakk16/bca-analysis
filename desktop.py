import threading
import webview
import subprocess
import time
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "bca_app.py")


def resource_path(relative_path):
    # When PyInstaller freezes this into an exe, bundled files are extracted
    # to sys._MEIPASS at runtime instead of living next to this script.
    base_path = getattr(sys, "_MEIPASS", HERE)
    return os.path.join(base_path, relative_path)


def run_streamlit():
    if getattr(sys, "frozen", False):
        # Frozen build: sys.executable is our own .exe, not a real Python
        # interpreter, so "sys.executable -m streamlit run ..." won't work.
        # Call Streamlit's CLI directly instead of shelling out.
        from streamlit.web import cli as stcli
        sys.argv = [
            "streamlit",
            "run",
            resource_path("bca_app.py"),
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ]
        stcli.main()
    else:
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
