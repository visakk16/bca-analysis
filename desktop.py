import threading
import webview
import subprocess
import time
import sys
import os
import webbrowser
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "bca_app.py")

STREAMLIT_SERVER_FLAG = "--run-streamlit-server"
PORT = 8501
URL = f"http://localhost:{PORT}"


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
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit",
        "run",
        resource_path("bca_app.py"),
        f"--server.port={PORT}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    sys.exit(stcli.main())


def launch_streamlit_subprocess():
    if getattr(sys, "frozen", False):
        # Re-launch our own frozen exe as a *child process* with a hidden
        # flag. That child process hits the STREAMLIT_SERVER_FLAG branch
        # above and runs Streamlit in ITS OWN main thread -- a real separate
        # process, just like "python -m streamlit run ..." would be.
        cmd = [sys.executable, STREAMLIT_SERVER_FLAG]
    else:
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            APP,
            f"--server.port={PORT}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_server(url=URL, timeout=30):
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
        time.sleep(2)
        
        print("Process return code:", proc.poll())
        
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            print("STDOUT:")
            print(stdout)
            print("STDERR:")
            print(stderr)
            print("Streamlit process exited immediately.")
            sys.exit(1)
        
        if not wait_for_server():
            print("Server never started.")
            sys.exit(1)
        try:
            webview.create_window("BCA Plate Analysis", URL, width=1400, height=900)
            webview.start()
        except Exception as e:
            # Most likely cause: the Microsoft Edge WebView2 runtime isn't
            # installed/available on this machine. Fall back to opening the
            # app in the user's default browser instead of just crashing.
            print(f"[desktop] Could not open the native app window: {e}")
            print(f"[desktop] Opening {URL} in your default browser instead.")
            webbrowser.open(URL)
            print("[desktop] Close this window to stop the app.")
            try:
                proc.wait()
            except KeyboardInterrupt:
                pass
        finally:
            proc.terminate()
