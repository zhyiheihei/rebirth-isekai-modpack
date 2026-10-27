#!/usr/bin/env python3
"""组装各平台的便携整合包，以及给 PCL2/HMCL 用的 MultiMC 实例包。

用法：
  python3 scripts/build.py                      # 全部平台 + 打包 7z/zip
  python3 scripts/build.py --target linux       # 只做 Linux
  python3 scripts/build.py --target mmc --zip   # 只做 PCL2 用的实例包
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

import common

PACK = common.load("pack.json")
NAME = PACK["name"]
VERSION = PACK["version"]
JRE_DIRNAME = "jre" + str(PACK["java"]["major"])

OS_KEY = {"linux": "linux", "windows": "windows", "macos": "osx"}
TARGETS = {
    "linux": "Linux-x64",
    "windows": "Windows-x64",
    "macos": "macOS",
}

INSTANCE_CFG = """[General]
ConfigVersion=1.3
InstanceType=OneSix
name={name}
OverrideMemory=true
MinMemAlloc={min_mem}
MaxMemAlloc={max_mem}
OverrideJavaArgs=false
OverrideJavaLocation=true
JavaPath=__BUNDLED_JAVA__
JoinServerOnLaunch=false
"""


def resource_source(explicit):
    """返回 (资源目录, 是否需要按平台补原生库)。缓存的 resources 已含全部平台库。"""
    cached = os.path.join(common.CACHE, "resources")
    if os.path.isdir(os.path.join(cached, "libraries")):
        return cached, False
    return os.path.expanduser(explicit or "~/.local/share/PrismLauncher"), True


def natives(libdir, os_key, meta_dir):
    """补齐目标系统专属的原生库（linux 包本身已有，windows/macos 需要下载）。"""
    allowed = {"windows": {"windows"}, "osx": {"osx", "osx-arm64"}, "linux": {"linux"}}[os_key]
    manifests = []
    mc_json = os.path.join(meta_dir, "net.minecraft", PACK["minecraft"] + ".json")
    nf_json = os.path.join(
        meta_dir, "net.neoforged", "neoforge", PACK["loader"]["version"] + ".json"
    )
    for path in (mc_json, nf_json):
        if os.path.exists(path):
            manifests.append(path)
    fetched = 0
    for manifest in manifests:
        with open(manifest, encoding="utf-8") as f:
            data = json.load(f)
        for lib in data.get("libraries", []):
            rules = lib.get("rules")
            ok = True
            if rules:
                ok = False
                for rule in rules:
                    os_rule = (rule.get("os") or {}).get("name")
                    if rule.get("action") == "allow" and (os_rule in allowed or not os_rule):
                        ok = True
            if not ok:
                continue
            parts = lib["name"].split(":")
            group, artifact, version = parts[0], parts[1], parts[2]
            classifier = parts[3] if len(parts) > 3 else None
            rel = "/".join(group.split(".")) + f"/{artifact}/{version}/{artifact}-{version}"
            if classifier:
                rel += "-" + classifier
            rel += ".jar"
            dest = os.path.join(libdir, rel)
            if os.path.exists(dest):
                continue
            url = (lib.get("downloads", {}).get("artifact") or {}).get("url")
            url = url or ("https://libraries.minecraft.net/" + rel)
            if common.download(url, dest, retries=2):
                fetched += 1
    return fetched


def build_gamedir(dest):
    """实例的游戏目录：mods / config / options.txt / resourcepacks / shaderpacks"""
    common.ensure_dir(dest)
    mods_dir = common.ensure_dir(os.path.join(dest, "mods"))
    for m in common.load("mods.json"):
        if not m["enabled"]:
            continue
        shutil.copy2(os.path.join(common.CACHE, "mods", m["file"]), os.path.join(mods_dir, m["file"]))
    shutil.copytree(os.path.join(common.PACK, "config"), os.path.join(dest, "config"), dirs_exist_ok=True)
    shutil.copy2(os.path.join(common.PACK, "options.txt"), os.path.join(dest, "options.txt"))
    for sub in ("resourcepacks", "shaderpacks"):
        target = common.ensure_dir(os.path.join(dest, sub))
        for e in common.load(sub + ".json"):
            shutil.copy2(os.path.join(common.LOCAL, sub, e["file"]), os.path.join(target, e["file"]))
    return dest


def build_instance(dest):
    common.ensure_dir(dest)
    shutil.copy2(os.path.join(common.PACK, "mmc-pack.json"), os.path.join(dest, "mmc-pack.json"))
    cfg = INSTANCE_CFG.format(
        name=NAME,
        min_mem=PACK["memory"]["min_mb"],
        max_mem=PACK["memory"]["max_mb"],
    )
    with open(os.path.join(dest, "instance.cfg"), "w", encoding="utf-8") as f:
        f.write(cfg)
    build_gamedir(os.path.join(dest, "minecraft"))
    return dest


def write_prism_cfg(datadir, source):
    cfg_path = os.path.join(source, "prismlauncher.cfg")
    text = open(cfg_path, encoding="utf-8").read() if os.path.exists(cfg_path) else "[General]\n"
    text = re.sub(r"(?m)^Language=.*$", "Language=zh", text)
    if "Language=" not in text:
        text = text.rstrip() + "\nLanguage=zh\n"
    with open(os.path.join(datadir, "prismlauncher.cfg"), "w", encoding="utf-8") as f:
        f.write(text)


def extract_launcher(archive, kind, root):
    if kind == "tar":
        with tarfile.open(archive) as tar:
            tar.extractall(root)
    else:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.filename.startswith("__MACOSX/"):
                    continue
                zf.extract(info, root)
    entries = os.listdir(root)
    if kind != "mac" and len(entries) == 1 and os.path.isdir(os.path.join(root, entries[0])):
        inner = os.path.join(root, entries[0])
        for item in os.listdir(inner):
            shutil.move(os.path.join(inner, item), os.path.join(root, item))
        os.rmdir(inner)


def extract_runtime(archive, kind, dest):
    common.ensure_dir(dest)
    tmp = dest + ".tmp"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    common.ensure_dir(tmp)
    if kind == "zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
    else:
        with tarfile.open(archive) as tar:
            tar.extractall(tmp)
    inner = os.path.join(tmp, os.listdir(tmp)[0])
    for item in os.listdir(inner):
        shutil.move(os.path.join(inner, item), os.path.join(dest, item))
    shutil.rmtree(tmp)


def assemble(platform, source, fill_natives=True):
    launcher_key = {"linux": "linux-x64", "windows": "windows-x64", "macos": "macos"}[platform]
    launcher = common.load("launcher.json")["artifacts"][launcher_key]
    runtime_key = "macos-aarch64" if platform == "macos" else platform + "-x64"
    runtime = common.load("runtimes.json")["artifacts"][runtime_key]
    root = os.path.join(common.DIST, f"{NAME}-{VERSION}-{TARGETS[platform]}")
    if os.path.exists(root):
        shutil.rmtree(root)
    common.ensure_dir(root)

    extract_launcher(
        os.path.join(common.CACHE, "launcher", launcher["file"]), launcher["kind"], root
    )
    datadir = root if platform != "macos" else os.path.join(root, "PrismLauncher-data")
    common.ensure_dir(datadir)

    print(f"[{platform}] 实例与配置", flush=True)
    build_instance(os.path.join(datadir, "instances", NAME))

    print(f"[{platform}] 游戏资源（assets/libraries/meta）", flush=True)
    shutil.copytree(os.path.join(source, "assets"), os.path.join(datadir, "assets"), symlinks=False)
    shutil.copytree(os.path.join(source, "libraries"), os.path.join(datadir, "libraries"), symlinks=False)
    shutil.copytree(os.path.join(source, "meta"), os.path.join(datadir, "meta"), symlinks=False)
    if fill_natives:
        got = natives(os.path.join(datadir, "libraries"), OS_KEY[platform], os.path.join(datadir, "meta"))
        print(f"[{platform}]   补下 {got} 个原生库", flush=True)
    logs = os.path.join(source, "logs")
    if os.path.isdir(logs):
        shutil.copytree(logs, os.path.join(datadir, "assets", "log_configs"), dirs_exist_ok=True)

    print(f"[{platform}] Java {PACK['java']['release']}", flush=True)
    if platform == "macos":
        for arch in ("aarch64", "x64"):
            art = common.load("runtimes.json")["artifacts"]["macos-" + arch]
            extract_runtime(
                os.path.join(common.CACHE, "runtimes", art["file"]),
                art["kind"],
                os.path.join(datadir, "java", f"{JRE_DIRNAME}-{arch}"),
            )
    else:
        extract_runtime(
            os.path.join(common.CACHE, "runtimes", runtime["file"]),
            runtime["kind"],
            os.path.join(datadir, "java", JRE_DIRNAME),
        )
    write_prism_cfg(datadir, source)
    trans_src = os.path.join(common.CACHE, "translations")
    if os.path.isdir(trans_src):
        shutil.copytree(trans_src, os.path.join(datadir, "translations"), dirs_exist_ok=True)

    if platform == "linux":
        launcher_script = (
            "#!/bin/sh\n"
            'cd "$(dirname "$0")" || exit 1\n'
            f'CFG="instances/{NAME}/instance.cfg"\n'
            f'JAVA="$(pwd)/java/{JRE_DIRNAME}/{runtime["java_path"]}"\n'
            'sed -i "s|^JavaPath=.*|JavaPath=$JAVA|" "$CFG"\n'
            'exec ./PrismLauncher "$@"\n'
        )
        path = os.path.join(root, "启动游戏.sh")
        open(path, "w", encoding="utf-8").write(launcher_script)
        os.chmod(path, 0o755)
    elif platform == "windows":
        java_rel = runtime["java_path"].replace("/", "\\")
        ps = (
            "$p = 'instances\\" + NAME + "\\instance.cfg'; "
            "$j = Join-Path (Get-Location) 'java\\" + JRE_DIRNAME + "\\" + java_rel + "'; "
            "$t = Get-Content -LiteralPath $p -Raw -Encoding UTF8; "
            "$t = [regex]::Replace($t, '(?m)^JavaPath=.*', 'JavaPath=' + $j); "
            "[IO.File]::WriteAllText((Resolve-Path $p).Path, $t, (New-Object System.Text.UTF8Encoding($false)))"
        )
        bat = (
            "@echo off\r\n"
            "chcp 65001 >nul\r\n"
            'cd /d "%~dp0"\r\n'
            f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{ps}"\r\n'
            'start "" "prismlauncher.exe"\r\n'
        )
        open(os.path.join(root, "启动游戏.bat"), "w", encoding="utf-8").write(bat)
    else:
        launcher_script = (
            "#!/bin/sh\n"
            'cd "$(dirname "$0")" || exit 1\n'
            f'CFG="PrismLauncher-data/instances/{NAME}/instance.cfg"\n'
            'ARCH="$(uname -m)"\n'
            'case "$ARCH" in\n'
            f'  arm64) JRE="${{PWD}}/PrismLauncher-data/java/{JRE_DIRNAME}-aarch64" ;;\n'
            f'  *)     JRE="${{PWD}}/PrismLauncher-data/java/{JRE_DIRNAME}-x64" ;;\n'
            'esac\n'
            'JAVA="$JRE/Contents/Home/bin/java"\n'
            'sed -i "" "s|^JavaPath=.*|JavaPath=$JAVA|" "$CFG"\n'
            'exec "./Prism Launcher.app/Contents/MacOS/prismlauncher" -d "$(pwd)/PrismLauncher-data" "$@"\n'
        )
        path = os.path.join(root, "启动游戏.command")
        open(path, "w", encoding="utf-8").write(launcher_script)
        os.chmod(path, 0o755)

    shutil.copy2(os.path.join(common.PACK, "使用说明.txt"), os.path.join(root, "使用说明.txt"))
    return root


def build_mmc(root_dir):
    """MultiMC/Prism 格式实例包，供 PCL2 / HMCL 导入。"""
    root = os.path.join(common.DIST, f"{NAME}-{VERSION}-MMC")
    if os.path.exists(root):
        shutil.rmtree(root)
    common.ensure_dir(root)
    instance = build_instance(root)
    game = os.path.join(instance, "minecraft")
    os.rename(game, os.path.join(instance, ".minecraft"))
    return root


def zip_dir(path, archive):
    cmd = ["7z", "a", "-bd", "-mx=5", archive, "."]
    if shutil.which("7z") is None:
        cmd = ["zip", "-r", "-q", archive, "."]
    subprocess.run(cmd, cwd=path, check=True)
    return archive


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="all", help="all|linux|windows|macos|mmc，逗号分隔")
    ap.add_argument("--zip", action="store_true", help="同时打成压缩包")
    ap.add_argument("--prism-data", default="", help="提供 assets/libraries/meta 的 Prism 数据目录")
    args = ap.parse_args()

    targets = list(TARGETS) + ["mmc"] if args.target == "all" else args.target.split(",")
    source, fill_natives = resource_source(args.prism_data)

    missing = common.check_local_assets()
    if missing:
        print("local-assets 不完整：")
        for m in missing:
            print("  -", m)
        return 1
    ok, total = common.fetch_mods(quiet=True)
    if ok != total:
        print(f"mod 缓存不完整（{ok}/{total}），先运行 scripts/fetch.py")
        return 1
    common.ensure_dir(common.DIST)

    built = []
    for platform in targets:
        if platform == "mmc":
            root = build_mmc(None)
        else:
            root = assemble(platform, source, fill_natives)
        print("完成：", root, flush=True)
        built.append(root)
        if args.zip:
            archive = root.rstrip("/") + ".7z"
            print("打包：", archive, flush=True)
            zip_dir(root, archive)
            built.append(archive)
    for path in built:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
