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
ARCHIVE_PREFIX = "Rebirth-Isekai"

TARGETS = {
    "linux": "Linux-x64",
    "windows": "Windows-x64",
    "macos": "macOS",
}

PRISM_CFG = """[General]
ConfigVersion=1.3
Language=zh
ApplicationTheme=system
IconTheme=pe_colored
IgnoreJavaWizard=true
AutomaticJavaDownload=false
AutomaticJavaSwitch=false
UserAskedAboutAutomaticJavaDownload=true
PastebinURL=
UseNativeGLFW=true
JavaArchitecture=64
MinMemAlloc={min_mem}
MaxMemAlloc={max_mem}
JavaPath=__BUNDLED_JAVA__
AutoUpdateCheckEnabled=false
"""

# 占位账户的静默刷新必须以「网络错误」收场（STATE_OFFLINE），启动器才不会弹
# 重新认证框。死代理让 OAuth 请求连接被拒 = NetworkError；游戏联机不走这个代理。
DEAD_PROXY_CFG = """[General]
ProxyType=SOCKS5
ProxyAddr=127.0.0.1
ProxyPort=9
"""

UPDATE_CFG = """[General]
auto_check=false
allow_beta=false
update_interval=31536000
"""

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
LowMemWarning=false
"""

# mmc-pack 组件声明本地 sha256，Prism 校验通过后不再远程拉 meta



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
    if os.path.exists(mc_json):
        manifests.append(mc_json)
    for uid, version in common.loader_components(PACK):
        path = os.path.join(meta_dir, uid, version + ".json")
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
    write_servers(dest)
    return dest


def lwjgl_version():
    """从缓存的 net.minecraft 元数据里取 LWJGL 版本。"""
    import json as _json

    path = os.path.join(common.CACHE, "resources", "meta", "net.minecraft", PACK["minecraft"] + ".json")
    try:
        data = _json.load(open(path, encoding="utf-8"))
    except Exception:
        return "3.4.1"
    for req in data.get("requires", []):
        if req.get("uid") == "org.lwjgl3":
            return req.get("equals") or req.get("suggests") or "3.4.1"
    return "3.4.1"


def meta_sha256(uid, version):
    """从缓存的 meta index.json 里取组件 json 的 sha256。"""
    import json as _json

    path = os.path.join(common.CACHE, "resources", "meta", "index.json")
    try:
        index = _json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    for pkg in index.get("packages", []):
        if pkg["uid"] == uid:
            return pkg.get("sha256")
    return None


def write_mmc_pack(dest):
    import json as _json

    lwjgl = lwjgl_version()
    sha = lambda uid, ver: meta_sha256(uid, ver)

    def comp(uid, version, **extra):
        entry = {"uid": uid, "version": version, "cachedName": uid,
                 "cachedVersion": version}
        if uid == "org.lwjgl3":
            entry["cachedVolatile"] = True
            entry["dependencyOnly"] = True
        else:
            entry["important"] = uid == "net.minecraft"
            if uid == "net.minecraft":
                entry["cachedRequires"] = [{"uid": "org.lwjgl3", "suggests": lwjgl}]
            elif uid == "net.fabricmc.fabric-loader":
                entry["cachedRequires"] = [
                    {"uid": "net.minecraft", "equals": PACK["minecraft"]},
                    {"uid": "net.fabricmc.intermediary", "equals": PACK["minecraft"]},
                ]
            else:
                entry["cachedRequires"] = [{"uid": "net.minecraft", "equals": PACK["minecraft"]}]
        s = sha(uid, version)
        if s:
            entry["cachedSha256"] = s
        entry.update(extra)
        return entry

    data = {
        "components": [comp("org.lwjgl3", lwjgl), comp("net.minecraft", PACK["minecraft"])]
        + [comp(uid, version) for uid, version in common.loader_components(PACK)],
        "formatVersion": 1,
    }
    with open(os.path.join(dest, "mmc-pack.json"), "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=4)


def build_instance(dest, bundled_java=True):
    common.ensure_dir(dest)
    write_mmc_pack(dest)
    cfg = INSTANCE_CFG.format(
        name=NAME,
        min_mem=PACK["memory"]["min_mb"],
        max_mem=PACK["memory"]["max_mb"],
    )
    if not bundled_java:
        cfg = "\n".join(
            line
            for line in cfg.splitlines()
            if not line.startswith(("JavaPath=", "OverrideJavaLocation="))
        ) + "\n"
    with open(os.path.join(dest, "instance.cfg"), "w", encoding="utf-8") as f:
        f.write(cfg)
    build_gamedir(os.path.join(dest, "minecraft"))
    return dest


def write_prism_cfg(datadir):
    """生成预配置好的启动器设置：跳过首次向导、不联网检查更新。"""
    with open(os.path.join(datadir, "prismlauncher.cfg"), "w", encoding="utf-8") as f:
        f.write(
            PRISM_CFG.format(
                min_mem=PACK["memory"]["min_mb"],
                max_mem=PACK["memory"]["max_mb"],
            )
            + DEAD_PROXY_CFG
        )
    with open(os.path.join(datadir, "prismlauncher_update.cfg"), "w", encoding="utf-8") as f:
        f.write(UPDATE_CFG)


def write_accounts(datadir):
    """写入占位账户，玩家名留 __RANDOM_NAME__ 由启动脚本首次运行时随机生成。

    机制：Arclight 服务端 online-mode=false 时离线登录可用。占位账户用
    带 msaClientID 的 MSA 结构压掉首次启动向导；其 token 无效，Prism 静默
    刷新失败后账号进入 Disabled 态，但 LaunchController 对 Offline 模式
    直接放行（--offline 启动），不会打断游戏。
    """
    import json as _json
    import time
    import uuid

    data = {
        "accounts": [
            {
                "active": True,
                "entitlement": {"ownsMinecraft": True, "canPlayMinecraft": True},
                "type": "MSA",
                "msa-client-id": "c36a9fb6-4f2a-41ff-90bd-ae7cc92031eb",
                "msa": {
                    "iat": int(time.time()),
                    "exp": int(time.time()) + 86400,
                    "token": "placeholder",
                    "refresh_token": "placeholder",
                    "extra": {},
                },
                "utoken": {"iat": int(time.time()), "exp": 0, "token": "", "refresh_token": "", "extra": {}},
                "xrp-mc": {"iat": int(time.time()), "exp": 0, "token": "", "refresh_token": "", "extra": {}},
                "ygg": {
                    "iat": int(time.time()),
                    "exp": int(time.time()) + 86400,
                    "token": "placeholder",
                    "refresh_token": "",
                    "extra": {"userName": "__RANDOM_NAME__", "clientToken": uuid.uuid4().hex},
                },
                "profile": {
                    "id": uuid.uuid4().hex,
                    "name": "__RANDOM_NAME__",
                    "skin": {"id": "", "url": "", "variant": ""},
                    "capes": [],
                },
            }
        ],
        "formatVersion": 3,
    }
    with open(os.path.join(datadir, "accounts.json"), "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False)


def write_servers(gamedir):
    import servers

    srv = PACK.get("server")
    if not srv:
        return
    servers.write(os.path.join(gamedir, "servers.dat"), [{"name": srv["name"], "ip": srv["ip"]}])


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
    write_prism_cfg(datadir)
    write_accounts(datadir)
    trans_src = os.path.join(common.CACHE, "translations")
    if os.path.isdir(trans_src):
        shutil.copytree(trans_src, os.path.join(datadir, "translations"), dirs_exist_ok=True)

    server_arg = f' -s {PACK["server"]["ip"]}' if PACK.get("server", {}).get("auto_join") else ""
    if platform == "linux":
        launcher_script = (
            "#!/bin/sh\n"
            'cd "$(dirname "$0")" || exit 1\n'
            f'JAVA="$(pwd)/java/{JRE_DIRNAME}/{runtime["java_path"]}"\n'
            f'sed -i "s|^JavaPath=.*|JavaPath=$JAVA|" "prismlauncher.cfg" "instances/{NAME}/instance.cfg"\n'
            'if [ -f player.txt ]; then\n'
            '  PLAYER="$(cat player.txt)"\n'
            'else\n'
            '  PLAYER="Player$(od -An -N3 -tx1 /dev/urandom | tr -d \' \\n\')"\n'
            '  printf "%s" "$PLAYER" > player.txt\n'
            '  sed -i "s/__RANDOM_NAME__/$PLAYER/g" accounts.json\n'
            'fi\n'
            f'exec ./PrismLauncher -l "{NAME}"{server_arg} --offline "$PLAYER" "$@"\n'
        )
        path = os.path.join(root, "启动游戏.sh")
        open(path, "w", encoding="utf-8").write(launcher_script)
        os.chmod(path, 0o755)
    elif platform == "windows":
        java_rel = runtime["java_path"].replace("/", "\\")
        ps = (
            "$d = Get-Location; "
            "if (-not (Test-Path 'player.txt')) { "
            "$n = 'Player' + (-join (1..6 | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) })); "
            "[IO.File]::WriteAllText((Join-Path $d 'player.txt'), $n, (New-Object System.Text.ASCIIEncoding)); "
            "$a = Join-Path $d 'accounts.json'; "
            "$t = [IO.File]::ReadAllText($a); "
            "[IO.File]::WriteAllText($a, $t.Replace('__RANDOM_NAME__', $n), (New-Object System.Text.UTF8Encoding($false))) }; "
            "$j = Join-Path $d 'java\\" + JRE_DIRNAME + "\\" + java_rel + "'; "
            "foreach ($p in @('prismlauncher.cfg','instances\\" + NAME + "\\instance.cfg')) "
            "{ $t = Get-Content -LiteralPath $p -Raw -Encoding UTF8; "
            "$t = [regex]::Replace($t, '(?m)^JavaPath=.*', 'JavaPath=' + $j); "
            "[IO.File]::WriteAllText((Resolve-Path $p).Path, $t, (New-Object System.Text.UTF8Encoding($false))) }"
        )
        bat = (
            "@echo off\r\n"
            "chcp 65001 >nul\r\n"
            'cd /d "%~dp0"\r\n'
            f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{ps}"\r\n'
            "set /p PLAYER=<player.txt\r\n"
            f'start "" "prismlauncher.exe" -l "{NAME}"{server_arg} --offline "%PLAYER%"\r\n'
        )
        open(os.path.join(root, "启动游戏.bat"), "w", encoding="utf-8").write(bat)
    else:
        launcher_script = (
            "#!/bin/sh\n"
            'cd "$(dirname "$0")" || exit 1\n'
            'ARCH="$(uname -m)"\n'
            'case "$ARCH" in\n'
            f'  arm64) JRE="${{PWD}}/PrismLauncher-data/java/{JRE_DIRNAME}-aarch64" ;;\n'
            f'  *)     JRE="${{PWD}}/PrismLauncher-data/java/{JRE_DIRNAME}-x64" ;;\n'
            'esac\n'
            'JAVA="$JRE/Contents/Home/bin/java"\n'
            f'sed -i "" "s|^JavaPath=.*|JavaPath=$JAVA|" "PrismLauncher-data/prismlauncher.cfg" "PrismLauncher-data/instances/{NAME}/instance.cfg"\n'
            'if [ -f player.txt ]; then\n'
            '  PLAYER="$(cat player.txt)"\n'
            'else\n'
            '  PLAYER="Player$(od -An -N3 -tx1 /dev/urandom | tr -d \' \\n\')"\n'
            '  printf "%s" "$PLAYER" > player.txt\n'
            '  sed -i "" "s/__RANDOM_NAME__/$PLAYER/g" "PrismLauncher-data/accounts.json"\n'
            'fi\n'
            f'exec "./Prism Launcher.app/Contents/MacOS/prismlauncher" -d "$(pwd)/PrismLauncher-data" -l "{NAME}"{server_arg} --offline "$PLAYER" "$@"\n'
        )
        path = os.path.join(root, "启动游戏.command")
        open(path, "w", encoding="utf-8").write(launcher_script)
        os.chmod(path, 0o755)

    write_guide(root)
    return root


def write_guide(root):
    text = open(os.path.join(common.PACK, "使用说明.txt"), encoding="utf-8").read()
    text = text.format(
        minecraft=PACK["minecraft"],
        loader=PACK["loader"]["version"],
        modcount=sum(1 for m in common.load("mods.json") if m["enabled"]),
        rpcount=len(common.load("resourcepacks.json")),
        spcount=len(common.load("shaderpacks.json")),
    )
    with open(os.path.join(root, "使用说明.txt"), "w", encoding="utf-8") as f:
        f.write(text)


def build_mmc(root_dir):
    """MultiMC/Prism 格式实例包，供 PCL2 / HMCL 导入。"""
    root = os.path.join(common.DIST, f"{NAME}-{VERSION}-MMC")
    if os.path.exists(root):
        shutil.rmtree(root)
    common.ensure_dir(root)
    instance = build_instance(root, bundled_java=False)
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
            suffix = os.path.basename(root).replace(f"{NAME}-", ARCHIVE_PREFIX + "-")
            archive = os.path.join(common.DIST, suffix + ".7z")
            print("打包：", archive, flush=True)
            zip_dir(root, archive)
            built.append(archive)
    for path in built:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
