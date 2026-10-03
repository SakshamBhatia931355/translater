"""Run Sakura Practice on this PC and publish a protected temporary tunnel."""
import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 5055
QUICK_TUNNEL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)


def cloudflared_path() -> Path:
    installed = shutil.which("cloudflared")
    if installed:
        return Path(installed)
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    target = local_app_data / "JapanesePractice" / "cloudflared.exe"
    if target.exists():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading Cloudflare Tunnel from the official Cloudflare GitHub release…", flush=True)
    request = urllib.request.Request(
        "https://api.github.com/repos/cloudflare/cloudflared/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "JapanesePractice"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.loads(response.read().decode("utf-8"))
    asset = next((item for item in release.get("assets", [])
                  if item.get("name") == "cloudflared-windows-amd64.exe"), None)
    if not asset:
        raise RuntimeError("Cloudflare's latest release did not include its Windows 64-bit client.")

    part = target.with_suffix(".download")
    download = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "JapanesePractice"})
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(download, timeout=60) as response, part.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
        expected = asset.get("digest", "")
        if expected.startswith("sha256:") and digest.hexdigest().lower() != expected.partition(":")[2].lower():
            raise RuntimeError("Cloudflare client checksum verification failed; the file was discarded.")
        part.replace(target)
    finally:
        if part.exists():
            part.unlink()
    return target


def wait_for_local_server(process: subprocess.Popen, code: str) -> None:
    import urllib.error
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The translation server exited while starting.")
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{PORT}/health",
                headers={"X-Sakura-Access-Code": code},
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)
    raise RuntimeError("The local translation server did not become ready in time.")


def terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    if os.name != "nt":
        print("ERROR=Public-link launcher is currently configured for Windows.", flush=True)
        return 2

    code = f"{secrets.randbelow(100_000_000):08d}"
    server = None
    tunnel = None
    reader = None
    output = queue.Queue()
    try:
        exe = cloudflared_path()
        server = subprocess.Popen(
            [sys.executable, str(ROOT / "src" / "mobile_server.py"), "--host", "127.0.0.1",
             "--port", str(PORT)],
            env={**os.environ, "SAKURA_ACCESS_CODE": code},
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        wait_for_local_server(server, code)
        tunnel = subprocess.Popen(
            [str(exe), "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        def read_tunnel_output():
            assert tunnel is not None and tunnel.stdout is not None
            for line in tunnel.stdout:
                output.put(line.rstrip())
            output.put(None)

        reader = threading.Thread(target=read_tunnel_output, daemon=True)
        reader.start()
        public_url = None
        published_credentials = False
        while tunnel.poll() is None:
            try:
                line = output.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                break
            if public_url is None:
                match = QUICK_TUNNEL_PATTERN.search(line)
                if match:
                    public_url = match.group(0)
            if public_url and not published_credentials:
                print(f"PUBLIC_URL={public_url}", flush=True)
                print(f"ACCESS_CODE={code}", flush=True)
                published_credentials = True

        if tunnel.poll() is not None and not published_credentials:
            raise RuntimeError("Cloudflare Tunnel stopped before it created a public link. Check this PC's internet connection.")
        print("Public link is ready. Keep this PC and this window running.", flush=True)
        while server.poll() is None and tunnel.poll() is None:
            time.sleep(1)
        if tunnel.poll() is not None:
            raise RuntimeError("Cloudflare Tunnel disconnected. Stop and start the public link again to get a new URL.")
        raise RuntimeError("The local translation server stopped.")
    except Exception as error:
        print(f"ERROR={error}", flush=True)
        return 1
    finally:
        terminate(tunnel)
        terminate(server)


if __name__ == "__main__":
    raise SystemExit(main())
