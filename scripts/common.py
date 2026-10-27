"""共用工具：路径、清单读取、校验下载。"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "pack")
CACHE = os.path.join(ROOT, "cache")
LOCAL = os.path.join(ROOT, "local-assets")
DIST = os.path.join(ROOT, "dist")


def load(name):
    with open(os.path.join(PACK, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, data):
    path = os.path.join(PACK, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def sha(algorithm, path, chunk=1 << 20):
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def proxy_args():
    proxy = os.environ.get("MODPACK_PROXY", "")
    return ["--socks5-hostname", proxy] if proxy else []


def download(url, dest, expected=None, algorithm="sha256", retries=3, quiet=False):
    """下载到 dest 并校验；已存在且校验通过则跳过。返回 True/False。"""
    if os.path.exists(dest) and expected and sha(algorithm, dest) == expected:
        return True
    ensure_dir(os.path.dirname(dest))
    for _ in range(retries):
        cmd = ["curl", "-fsSL", "--max-time", "600", *proxy_args(), "-o", dest, url]
        if subprocess.run(cmd, capture_output=True).returncode == 0:
            if not expected or sha(algorithm, dest) == expected:
                return True
            os.remove(dest)
        elif os.path.exists(dest):
            os.remove(dest)
    if not quiet:
        print(f"  下载失败: {url}", file=sys.stderr)
    return False


def fetch_mods(quiet=False):
    mods = load("mods.json")
    ok = 0
    for m in mods:
        dest = os.path.join(CACHE, "mods", m["file"])
        if download(m["url"], dest, m["sha512"], "sha512", quiet=quiet):
            ok += 1
        else:
            print(f"  缺失 mod: {m['file']}", file=sys.stderr)
    return ok, len(mods)


def fetch_launcher(quiet=False):
    arts = load("launcher.json")["artifacts"]
    for key, a in arts.items():
        if not download(a["url"], os.path.join(CACHE, "launcher", a["file"]), a["sha256"], quiet=quiet):
            return False
    return True


def fetch_runtimes(quiet=False):
    arts = load("runtimes.json")["artifacts"]
    for key, a in arts.items():
        if not download(a["url"], os.path.join(CACHE, "runtimes", a["file"]), a["sha256"], quiet=quiet):
            return False
    return True


def check_local_assets():
    missing = []
    for name in ("resourcepacks.json", "shaderpacks.json"):
        for e in load(name):
            path = os.path.join(LOCAL, name.split(".")[0], e["file"])
            if not os.path.exists(path):
                missing.append(os.path.relpath(path, ROOT))
            elif sha("sha256", path) != e["sha256"]:
                missing.append(os.path.relpath(path, ROOT) + " (校验失败)")
    return missing
