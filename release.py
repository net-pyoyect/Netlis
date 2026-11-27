#!/usr/bin/env python3
"""Herramienta para lanzar nuevas versiones oficiales de Netlis hacia GitHub con pruebas y etiquetas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "version.json"


def bump_version_str(current: str, part: str) -> str:
    nums = [int(x) for x in str(current).lstrip("v").split(".")[:3] if x.isdigit()]
    while len(nums) < 3:
        nums.append(0)
    major, minor, patch = nums
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Publicador de actualizaciones de Netlis")
    parser.add_argument("--bump", choices=("patch", "minor", "major"), default="patch", help="Tipo de incremento de versión")
    parser.add_argument("--notes", required=True, help="Notas de la actualización para los usuarios")
    parser.add_argument("--repo", default="", help="Repositorio GitHub (ej. usuario/netlis)")
    parser.add_argument("--push", action="store_true", help="Crea commit, tag vX.Y.Z y hace git push a GitHub")
    parser.add_argument("--skip-tests", action="store_true", help="Omite la suite de pruebas antes de publicar")
    args = parser.parse_args()

    if not args.skip_tests:
        py_bin = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python3")
        if not py_bin.is_file():
            py_bin = Path(sys.executable)
        res = subprocess.run([str(py_bin), str(ROOT / "tests" / "test_suite.py"), "-v"], cwd=ROOT, check=False)
        if res.returncode != 0:
            print("ERROR: Las pruebas fallaron. Publicación cancelada.", file=sys.stderr)
            return 1

    data = {}
    if VERSION_FILE.is_file():
        data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    new_ver = bump_version_str(str(data.get("version") or "1.0.0"), args.bump)
    data["version"] = new_ver
    data["notes"] = args.notes.strip()
    if args.repo.strip():
        data["repo"] = args.repo.strip().strip("/")
    data.setdefault("branch", "main")
    VERSION_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RELEASE_PREPARED version=v{new_ver} repo={data.get('repo') or '(local)'}")

    if args.push:
        if not (ROOT / ".git").is_dir():
            print("ERROR: Este directorio aún no tiene 'git init'.", file=sys.stderr)
            return 1
        subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "commit", "-m", f"release: v{new_ver} - {args.notes.strip()}"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "tag", f"v{new_ver}"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "push"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "push", "--tags"], check=True)
        print(f"RELEASE_PUSHED v{new_ver}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
