"""Local dev environment: API server + Mini App + ngrok tunnel.

Starts three services:
  1. functions-framework on port 8080 (Python API backend)
  2. Vite dev server on port 5173 (React Mini App)
  3. ngrok tunnel to port 5173 (public HTTPS URL for Telegram WebView)

The Vite dev server proxies /api/* requests to functions-framework,
so the Mini App and API share the same origin via the ngrok URL.

Usage:
  python run_dev.py                        # random ngrok URL each time
  python run_dev.py --domain my.ngrok.app  # fixed static domain

Set NGROK_DOMAIN in .env.yaml to avoid passing --domain every time.
Get a free static domain at https://dashboard.ngrok.com/domains

The ngrok public URL will be printed — set it as the Mini App URL
in BotFather (/mybots → your bot → Bot Menu Button).

For the Telegram bot itself, run `python run_local.py` in a separate terminal.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).parent
MINI_APP_DIR = ROOT / "mini-app"
API_PORT = 8080
VITE_PORT = 5173
NGROK_API = "http://127.0.0.1:4040/api/tunnels"


def _load_env_yaml() -> None:
    """Load .env.yaml into os.environ (same logic as run_local.py)."""
    path = ROOT / ".env.yaml"
    if not path.exists():
        print("Error: .env.yaml not found. Copy from .env.yaml.example and fill in values.")
        sys.exit(1)
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print("Error: .env.yaml is not a valid YAML mapping.")
        sys.exit(1)
    for key, value in data.items():
        if value is not None:
            os.environ.setdefault(key, str(value))


def _check_prerequisites() -> None:
    """Verify that required tools and directories exist."""
    errors: list[str] = []

    if not MINI_APP_DIR.exists():
        errors.append("mini-app/ directory not found.")

    if not shutil.which("ngrok"):
        errors.append(
            "ngrok CLI not found. Install: https://ngrok.com/download\n"
            "  macOS: brew install ngrok/ngrok/ngrok"
        )

    if not shutil.which("npm"):
        errors.append("npm not found. Install Node.js: https://nodejs.org/")

    if errors:
        for e in errors:
            print(f"Error: {e}")
        sys.exit(1)


def _ensure_node_modules() -> None:
    """Run npm install if node_modules is missing."""
    if not (MINI_APP_DIR / "node_modules").exists():
        print("[mini-app] Installing npm dependencies...")
        subprocess.run(["npm", "install"], cwd=MINI_APP_DIR, check=True)
        print()


def _get_ngrok_url(timeout: int = 15) -> str:
    """Poll ngrok local API until an HTTPS tunnel URL is available."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = Request(NGROK_API)
            with urlopen(req, timeout=2) as resp:
                tunnels = json.loads(resp.read()).get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t["public_url"]
        except (URLError, ConnectionError, OSError, json.JSONDecodeError):
            pass
        time.sleep(0.5)
    return ""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local dev environment")
    parser.add_argument(
        "--domain",
        help="ngrok static domain (overrides NGROK_DOMAIN env var)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _check_prerequisites()
    _load_env_yaml()
    _ensure_node_modules()

    ngrok_domain = args.domain or os.environ.get("NGROK_DOMAIN", "")

    procs: list[subprocess.Popen] = []

    try:
        # 1) API server (functions-framework)
        print(f"[api]      Starting functions-framework on port {API_PORT}...")
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "functions_framework",
             "--target=webhook", f"--port={API_PORT}", "--debug"],
            cwd=ROOT,
        ))

        # 2) Vite dev server (Mini App)
        print(f"[mini-app] Starting Vite dev server on port {VITE_PORT}...")
        procs.append(subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=MINI_APP_DIR,
        ))

        # 3) ngrok tunnel → Vite port
        ngrok_cmd = ["ngrok", "http", str(VITE_PORT)]
        if ngrok_domain:
            ngrok_cmd.extend(["--domain", ngrok_domain])
            print(f"[ngrok]    Tunneling to port {VITE_PORT} via {ngrok_domain}...")
        else:
            print(f"[ngrok]    Tunneling to port {VITE_PORT} (random URL)...")
        procs.append(subprocess.Popen(
            ngrok_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ))

        # Brief pause so processes have time to start before we query ngrok
        time.sleep(2)

        # Check if ngrok died immediately (e.g. auth token missing)
        ngrok_proc = procs[-1]
        if ngrok_proc.poll() is not None:
            print(
                "\nError: ngrok exited immediately. Make sure you have authenticated:\n"
                "  ngrok config add-authtoken <YOUR_TOKEN>\n"
                "  Get a free token at https://dashboard.ngrok.com/get-started/your-authtoken"
            )
            raise SystemExit(1)

        url = _get_ngrok_url()
        print()
        if url:
            is_static = bool(ngrok_domain)
            print("=" * 62)
            print(f"  Mini App URL:  {url}")
            if is_static:
                print("  (static domain — no need to update BotFather)")
            print()
            if not is_static:
                print("  Set this URL in BotFather:")
                print("    /mybots → your bot → Bot Menu Button → Edit URL")
                print()
                print("  Tip: set NGROK_DOMAIN in .env.yaml for a fixed URL")
                print()
            print("  Vite proxies /api/* → localhost:8080 (functions-framework)")
            print("  Auth uses real Telegram initData from WebView")
            print("=" * 62)
        else:
            print("Warning: could not detect ngrok tunnel URL.")
            print("Check ngrok status: http://localhost:4040")

        print()
        print("Tip: run 'python run_local.py' in another terminal for the bot (polling mode).")
        print("Press Ctrl+C to stop all services.\n")

        # Keep running until Ctrl+C or a process exits unexpectedly
        while True:
            for p in procs:
                ret = p.poll()
                if ret is not None and ret != 0:
                    name = {0: "api", 1: "mini-app", 2: "ngrok"}.get(procs.index(p), "?")
                    print(f"\n[{name}] Process exited with code {ret}.")
                    raise SystemExit(1)
            time.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        print("\nShutting down...")
    finally:
        for p in reversed(procs):
            try:
                p.terminate()
            except OSError:
                pass
        for p in reversed(procs):
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("All services stopped.")


if __name__ == "__main__":
    main()
