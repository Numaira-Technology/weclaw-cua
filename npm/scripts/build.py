"""Build weclaw standalone binaries with PyInstaller.

Usage:
    python npm/scripts/build.py                    # build for current platform
    python npm/scripts/build.py darwin-arm64       # specific platform
    python npm/scripts/build.py darwin-arm64 win32-x64  # multiple platforms
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NPM_DIR = ROOT / "npm"
PLATFORMS_DIR = NPM_DIR / "platforms"

PLATFORM_MAP = {
    "darwin-arm64": {"target": "macos"},
    "darwin-x64":   {"target": "macos"},
    "linux-x64":    {"target": "linux"},
    "linux-arm64":  {"target": "linux"},
    "win32-x64":    {"target": "win"},
}


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return
    except ImportError:
        pass
    print("[+] Installing PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_platform(platform: str) -> bool:
    os_name = platform.split("-")[0]
    ext = ".exe" if os_name == "win32" else ""

    output_dir = PLATFORMS_DIR / platform / "bin"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"Building for {platform}...")
    print(f"{'=' * 60}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "weclaw",
        "--distpath", str(output_dir),
        "--workpath", str(ROOT / "build" / f"weclaw_{platform}"),
        "--specpath", str(ROOT / "build"),
        "--noconfirm",
        "--clean",
    ]

    hidden = [
        "litellm", "openai", "numpy", "cv2", "PIL",
        "pyautogui", "click",
    ]
    for h in hidden:
        cmd.extend(["--hidden-import", h])

    cmd.append(str(ROOT / "entry.py"))

    print(f"[+] Running: {' '.join(cmd)}")

    try:
        subprocess.check_call(cmd, cwd=str(ROOT))
    except subprocess.CalledProcessError as e:
        print(f"[-] Build failed for {platform}: {e}")
        return False

    binary_path = output_dir / f"weclaw{ext}"
    if not binary_path.exists():
        print(f"[-] Binary not found: {binary_path}")
        return False

    print(f"[+] Built: {binary_path}")
    print(f"    Size: {binary_path.stat().st_size / 1024 / 1024:.1f} MB")
    return True


def main():
    if len(sys.argv) > 1:
        platforms = sys.argv[1:]
    else:
        import platform as _pf
        current = f"{_pf.system().lower()}-{_pf.machine()}"
        platforms = []
        if current == "darwin-arm64":
            platforms = ["darwin-arm64"]
        elif current in ("darwin-x86_64", "darwin-amd64"):
            platforms = ["darwin-x64"]
        else:
            for p in PLATFORM_MAP:
                os_name, arch = p.split("-")
                if os_name in current and (
                    arch in current
                    or (arch == "x64" and ("x86_64" in current or "amd64" in current))
                ):
                    platforms = [p]
                    break
            if not platforms:
                print(f"Cannot determine platform from '{current}'")
                print(f"Usage: {sys.argv[0]} [platform...]")
                print(f"  Platforms: {', '.join(PLATFORM_MAP.keys())}")
                sys.exit(1)

    print(f"[+] Building for: {', '.join(platforms)}")
    ensure_pyinstaller()

    results = {}
    for p in platforms:
        if p not in PLATFORM_MAP:
            print(f"[-] Unknown platform: {p}")
            results[p] = False
            continue
        results[p] = build_platform(p)

    print(f"\n{'=' * 60}")
    print("Build Summary:")
    for p, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {p}: {status}")
    print(f"{'=' * 60}")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
