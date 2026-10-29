"""共用工具：路径、清单读取、校验下载。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "pack")
CACHE = os.path.join(ROOT, "cache")
LOCAL = os.path.join(ROOT, "local-assets")
DIST = os.environ.get("MODPACK_DIST") or os.path.join(ROOT, "dist")


def load(name):
    with open(os.path.join(PACK, name), encoding="utf-8") as f:
        return json.load(f)


def _existing_indent(path):
    """读文件现有的缩进宽度：仓库里 mods.json 是 2 空格、其余清单多是 1 空格，
    写死任何一个值都会把整份文件重排，淹没真正的改动。"""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith(" "):
                    return len(line) - len(line.lstrip(" "))
    except OSError:
        pass
    return 1


def save(name, data):
    path = os.path.join(PACK, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=_existing_indent(path))
        f.write("\n")


LOADER_COMPONENTS = {
    "neoforge": lambda pack: [("net.neoforged", pack["loader"]["version"])],
    "fabric": lambda pack: [
        ("net.fabricmc.intermediary", pack["minecraft"]),
        ("net.fabricmc.fabric-loader", pack["loader"]["version"]),
    ],
}


def loader_components(pack=None):
    """加载器在 Prism/MultiMC 里的组件列表（uid, version）；顺序即依赖顺序。"""
    pack = pack or load("pack.json")
    try:
        return LOADER_COMPONENTS[pack["loader"]["type"]](pack)
    except KeyError:
        raise SystemExit(f"未知加载器类型: {pack['loader']['type']}")


def sha(algorithm, path, chunk=1 << 20):
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def normalize_resourcepack(source, destination):
    """Normalize resource-pack version metadata for the target MC pack-format schema."""
    with zipfile.ZipFile(source) as src:
        infos = src.infolist()
        metadata_info = next((i for i in infos if i.filename == "pack.mcmeta" and not i.is_dir()), None)
        if metadata_info is None:
            raise ValueError(f"材质包缺少 pack.mcmeta: {source}")
        metadata_bytes = src.read(metadata_info)
        metadata = json.loads(metadata_bytes)
        pack = metadata.setdefault("pack", {})
        old_supported = pack.get("supported_formats")
        old_format = pack.get("pack_format")
        minimum = pack.get("min_format")
        maximum = pack.get("max_format")

        if minimum is None:
            if isinstance(old_supported, dict):
                minimum = old_supported.get("min_inclusive", old_supported.get("min_format", old_format))
            elif isinstance(old_supported, list) and old_supported:
                minimum = old_supported[0]
            elif isinstance(old_supported, int):
                minimum = old_supported
            else:
                minimum = old_format or 15
        if maximum is None:
            if isinstance(old_supported, dict):
                maximum = old_supported.get("max_inclusive", old_supported.get("max_format", 999))
            elif isinstance(old_supported, list) and old_supported:
                maximum = old_supported[-1]
            else:
                maximum = 999

        minimum = int(minimum[0] if isinstance(minimum, list) else minimum)
        maximum = int(maximum[-1] if isinstance(maximum, list) else maximum)
        minimum = max(15, minimum)
        if old_format is not None:
            old_format = max(15, int(old_format))
            minimum = min(minimum, old_format)
        maximum = max(minimum, maximum)
        pack["min_format"] = minimum
        pack["max_format"] = maximum

        if minimum < 65:
            pack["pack_format"] = old_format or minimum
            pack["supported_formats"] = {
                "min_inclusive": minimum,
                "max_inclusive": maximum,
            }
        else:
            pack.pop("pack_format", None)
            pack.pop("supported_formats", None)

        normalized = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
        changed = normalized != metadata_bytes
        with zipfile.ZipFile(destination, "w") as out:
            out.comment = src.comment
            for info in infos:
                data = normalized if info is metadata_info else src.read(info)
                out.writestr(info, data)
    return changed


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def proxy_args():
    proxy = os.environ.get("MODPACK_PROXY", "")
    return ["--socks5-hostname", proxy] if proxy else []


def fetch_json(url, retries=3):
    """走 curl（可用 MODPACK_PROXY）取 JSON。"""
    import json as _json

    for _ in range(retries):
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", "120", *proxy_args(), url], capture_output=True
        )
        if proc.returncode == 0:
            try:
                return _json.loads(proc.stdout)
            except Exception:
                continue
    raise RuntimeError(f"取 JSON 失败: {url}")


def download_many(pairs, parallel=16):
    """pairs: [(url, dest, expected_sha1)]，用 curl --parallel 批量拉，返回失败列表。"""
    todo = []
    for url, dest, expected in pairs:
        if os.path.exists(dest) and (not expected or sha("sha1", dest) == expected):
            continue
        ensure_dir(os.path.dirname(dest))
        todo.append((url, dest, expected))
    if not todo:
        return []
    px = os.environ.get("MODPACK_PROXY", "")
    lines = [f'proxy = "socks5h://{px}"'] if px else []
    for url, dest, _ in todo:
        lines += [f'url = "{url}"', f'output = "{dest}"']
    subprocess.run(
        ["curl", "--parallel", "--parallel-max", str(parallel), "-fsSL",
         "--max-time", "900", "--config", "-"],
        input="\n".join(lines), text=True, capture_output=True,
    )
    failed = [(u, d, h) for u, d, h in todo if not os.path.exists(d) or (h and sha("sha1", d) != h)]
    for url, dest, expected in failed:
        download(url, dest, expected, "sha1", retries=2, quiet=True)
    return [d for u, d, h in failed if not os.path.exists(d) or (h and sha("sha1", d) != h)]


def download(url, dest, expected=None, algorithm="sha256", retries=3, quiet=False):
    """下载到 dest 并校验；已存在且校验通过则跳过。返回 True/False。"""
    if os.path.exists(dest) and expected and sha(algorithm, dest) == expected:
        return True
    ensure_dir(os.path.dirname(dest))
    last_error = "未知错误"
    for attempt in range(retries):
        cmd = ["curl", "-fsSL", "--max-time", "600", *proxy_args(), "-o", dest, url]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode == 0 and os.path.exists(dest):
            if not expected or sha(algorithm, dest) == expected:
                return True
            last_error = f"{algorithm} 校验不符"
        else:
            last_error = proc.stderr.decode("utf-8", errors="replace").strip() or f"curl exit {proc.returncode}"
        if os.path.exists(dest):
            os.remove(dest)
        if attempt + 1 < retries:
            time.sleep(min(2 ** attempt, 8))
    if not quiet:
        print(f"  下载失败: {url} ({last_error})", file=sys.stderr)
    return False


def fetch_mods(quiet=False):
    mods = load("mods.json")
    ok = 0
    for m in mods:
        dest = os.path.join(CACHE, "mods", m["file"])
        if m.get("local"):
            # 仓库自带 jar（Modrinth 上没有的付费/自制数据包模组），按 sha512 校验后直接摆进缓存
            src = os.path.join(ROOT, m["local"])
            if not os.path.exists(src) or (m.get("sha512") and sha("sha512", src) != m["sha512"]):
                print(f"  仓库内 mod 缺失或校验失败: {m['local']}", file=sys.stderr)
                continue
            if not (os.path.exists(dest) and m.get("sha512") and sha("sha512", dest) == m["sha512"]):
                ensure_dir(os.path.dirname(dest))
                shutil.copy2(src, dest)
            ok += 1
            continue
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


# 仓库内直接携带的资产修正版：只有被修过、体积又小的包放这里。
# local-assets/ 不进 git，靠 actions/cache 或发布资产恢复，缓存里的旧副本会盖掉修正版，
# 所以每次校验前按清单 sha256 把它们复制回去。
ASSET_OVERRIDES = os.path.join(PACK, "resourcepacks-local")


def apply_asset_overrides():
    """把仓库自带的修正版资产覆盖到 local-assets/，已一致则跳过。返回被覆盖的相对路径。"""
    if not os.path.isdir(ASSET_OVERRIDES):
        return []
    applied = []
    for name in ("resourcepacks", "shaderpacks"):
        for e in load(name + ".json"):
            src = os.path.join(ASSET_OVERRIDES, e["file"])
            if not os.path.exists(src):
                continue
            dst = os.path.join(LOCAL, name, e["file"])
            if os.path.exists(dst) and sha("sha256", dst) == e["sha256"]:
                continue
            ensure_dir(os.path.dirname(dst))
            shutil.copy2(src, dst)
            applied.append(os.path.relpath(dst, ROOT))
    return applied


def check_local_assets():
    for fixed in apply_asset_overrides():
        print(f"   用仓库内修正版覆盖: {fixed}")
    missing = []
    for name in ("resourcepacks.json", "shaderpacks.json"):
        for e in load(name):
            path = os.path.join(LOCAL, name.split(".")[0], e["file"])
            if not os.path.exists(path):
                missing.append(os.path.relpath(path, ROOT))
            elif sha("sha256", path) != e["sha256"]:
                missing.append(os.path.relpath(path, ROOT) + " (校验失败)")
    return missing


I18N = "https://i18n.prismlauncher.org"


def fetch_translations(langs=("zh",)):
    """启动器界面翻译：index_v2.json + mmc_<lang>.qm，保证离线也能显示中文。"""
    dest = ensure_dir(os.path.join(CACHE, "translations"))
    index = fetch_json(f"{I18N}/index_v2.json")
    with open(os.path.join(dest, "index_v2.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    ok = True
    for lang in langs:
        info = (index.get("languages") or {}).get(lang)
        if not info:
            ok = False
            continue
        path = os.path.join(dest, f"mmc_{lang}.qm")
        ok &= download(f"{I18N}/{info['file']}", path, info["sha1"], "sha1")
    return ok


def prune_local_assets():
    """删掉 local-assets 里不在清单内的文件。

    发布资产里的 tar 会整包解压，改名/回退过的旧文件会一起落盘；清单才是唯一事实来源，
    多余文件留着会既占体积又出现在游戏内的材质包列表里。
    """
    removed = []
    for name in ("resourcepacks", "shaderpacks"):
        keep = {e["file"] for e in load(name + ".json")}
        folder = os.path.join(LOCAL, name)
        if not os.path.isdir(folder):
            continue
        for fn in os.listdir(folder):
            if fn not in keep:
                os.remove(os.path.join(folder, fn))
                removed.append(os.path.relpath(os.path.join(folder, fn), ROOT))
    return removed


def extract_tar(archive, dest):
    """解 tar / tar.zst。

    Windows 上 Git Bash 的 GNU tar 没有内置 zstd 支持，`--zstd` 会去 exec 一个
    不存在的 zstd 程序直接失败；系统自带的是 bsdtar（libarchive，自带 zstd）。
    所以按 tar --zstd -> bsdtar -> python zstandard 三级兜底，Linux/CI 走第一条。
    """
    zst = archive.endswith(".zst")
    bsdtar = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
    tries = []
    if zst:
        tries.append(["tar", "--zstd", "-xf", archive, "-C", dest])
        if os.path.exists(bsdtar):
            tries.append([bsdtar, "-xf", archive, "-C", dest])
    else:
        tries.append(["tar", "-xf", archive, "-C", dest])
    for cmd in tries:
        if subprocess.run(cmd, capture_output=True).returncode == 0:
            return True
    if not zst:
        return False
    try:
        import tarfile

        import zstandard
    except ImportError:
        return False
    with open(archive, "rb") as raw:
        reader = zstandard.ZstdDecompressor().stream_reader(raw)
        with tarfile.open(fileobj=reader, mode="r|") as tar:
            try:
                tar.extractall(dest, filter="data")
            except TypeError:  # Python < 3.12 没有 filter 参数
                tar.extractall(dest)
    return True


def fetch_local_assets():
    """按 pack/local-assets.json 拉取材质/光影原始包，解压到 local-assets/ 并按清单剪枝。"""
    info = load("local-assets.json")
    if not info.get("url"):
        return False
    archive = os.path.join(CACHE, "launcher", info["file"])
    if not download(info["url"], archive, info.get("sha256") or None):
        return False
    if not extract_tar(archive, ROOT):
        print(f"   解压失败: {os.path.basename(archive)}", file=sys.stderr)
        return False
    for gone in prune_local_assets():
        print("   清掉清单外的旧文件:", gone)
    return True
