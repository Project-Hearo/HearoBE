import subprocess, sys, os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent   # ./app
GEN_PATH = BASE_DIR / "slam_to_wall_shell_from_yaml.py"

def generate_wall_and_meta(timeout: int = 120) -> None:
    """
    slam_to_wall_shell_from_yaml.py 실행해서
    public/wall_shell.json, public/meta.json 생성
    """
    if not GEN_PATH.exists():
        raise FileNotFoundError(f"Map generator not found: {GEN_PATH}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.run(
            [sys.executable, str(GEN_PATH)],
            cwd=str(BASE_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Map generator timeout after {timeout}s")

    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        err = (proc.stderr or "").rstrip()
        raise RuntimeError(f"Map generator failed (code {proc.returncode})\n{err}")

    print("Map data generated (public/wall_shell.json, public/meta.json).")
