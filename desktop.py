import threading
import webview
import subprocess
import time
import sys
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "bca_app.py")

STREAMLIT_SERVER_FLAG = "--run-streamlit-server"


def resource_path(relative_path):
    # When PyInstaller freezes this into an exe, bundled files are extracted
    # to sys._MEIPASS at runtime instead of living next to this script.
    base_path = getattr(sys, "_MEIPASS", HERE)
    return os.path.join(base_path, relative_path)


def run_streamlit_server_in_this_process():
    """Runs Streamlit's CLI directly in THIS process's main thread.
    Streamlit installs signal handlers on startup, which Python only allows
    from the main thread of the main interpreter -- so this must never be
    called from a background thread."""
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit",
        "run",
        resource_path("bca_app.py"),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    sys.exit(stcli.main())


def launch_streamlit_subprocess():
    if getattr(sys, "frozen", False):
        # Re-launch our own frozen exe as a *child process* with a hidden
        # flag. That child process hits the STREAMLIT_SERVER_FLAG branch
        # below and runs Streamlit in ITS OWN main thread -- a real separate
        # process, just like "python -m streamlit run ..." would be.
        cmd = [sys.executable, STREAMLIT_SERVER_FLAG]
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
    return subprocess.Popen(cmd)


def wait_for_server(url="http://localhost:8501", timeout=30):
    """Poll until Streamlit responds instead of guessing with a fixed sleep --
    first launches can be slow while antivirus scans freshly-extracted files."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


if __name__ == "__main__":
    if STREAMLIT_SERVER_FLAG in sys.argv:
        # This branch only runs inside the child process spawned above.
        run_streamlit_server_in_this_process()
    else:
        proc = launch_streamlit_subprocess()
        wait_for_server()
        webview.create_window("BCA Plate Analysis", "http://localhost:8501", width=1400, height=900)
        webview.start()
        proc.terminate()
