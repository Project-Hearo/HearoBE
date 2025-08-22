import subprocess, sys, os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent   # ./app
GEN_PATH = BASE_DIR / "slam_to_wall_shell_from_yaml.py"

def generate_wall_and_meta():
    """slam_to_wall_shell_from_yaml.py 실행해서 wall_shell.json, meta.json 생성"""
    if not GEN_PATH.exists():
        raise FileNotFoundError(f"Map generator not found: {GEN_PATH}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        [sys.executable, str(GEN_PATH)],
        cwd=str(BASE_DIR),
        env=env,
        capture_output=True,
        text=True
    )
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.rstrip())
        raise RuntimeError(f"Map generator failed with code {proc.returncode}")
    print("Map data generated (public/wall_shell.json, public/meta.json).")
