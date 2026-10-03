"""Small Windows launcher for the project-local Python environment."""
import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


def project_root():
    binary = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return binary.parent.parent if binary.parent.name.lower() == "artifacts" else binary.parent
    return Path(__file__).resolve().parents[1]


def main():
    root = project_root()
    script = root / "src" / "desktop_app.py"
    env_dir = root / ".venv" / "Scripts"
    interpreter = env_dir / ("pythonw.exe" if (env_dir / "pythonw.exe").exists() else "python.exe")
    if "--check" in sys.argv:
        return 0 if script.is_file() and interpreter.is_file() else 2
    if not script.is_file() or not interpreter.is_file():
        dialog = tk.Tk(); dialog.withdraw()
        messagebox.showerror("Kotoba Practice", f"Project files or the Python environment are missing.\n\nExpected project folder:\n{root}\n\nRun the setup steps in README.md first.")
        dialog.destroy()
        return 2
    kwargs = {"cwd": str(root)}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([str(interpreter), str(script)], **kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
