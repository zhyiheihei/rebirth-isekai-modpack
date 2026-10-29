#!/usr/bin/env python3
"""构建产物自检：确认「启动免下载」所需的资源都在包里。"""
import glob
import json
import os
import re
import sys

import common


def check_bundle(root):
    name = common.load("pack.json")["name"]
    pack = common.load("pack.json")
    problems = []
    is_mmc = root.endswith("-MMC")

    def need(rel, what):
        if not os.path.exists(os.path.join(root, rel)):
            problems.append(f"缺少{what}: {rel}")

    if is_mmc:
        return check_mmc(root, name, problems)

    index_id = None
    for candidate in ("assets", "PrismLauncher-data/assets"):
        idx_dir = os.path.join(root, candidate, "indexes")
        if os.path.isdir(idx_dir):
            files = [f for f in os.listdir(idx_dir) if f.endswith(".json")]
            if files:
                index_id = os.path.basename(files[0])[:-5]
                objects = os.path.join(root, candidate, "objects")
                count = sum(len(fs) for _, _, fs in os.walk(objects)) if os.path.isdir(objects) else 0
                if count < 1000:
                    problems.append(f"素材对象过少: {count}")
    if not index_id:
        problems.append("缺少素材索引 assets/indexes/*.json")

    for candidate in ("libraries", "PrismLauncher-data/libraries"):
        lib = os.path.join(root, candidate)
        if os.path.isdir(lib):
            jars = sum(len([f for f in fs if f.endswith(".jar")]) for _, _, fs in os.walk(lib))
            if jars < 50:
                problems.append(f"库文件过少: {jars}")
            break
    else:
        problems.append("缺少 libraries/")

    for candidate in ("meta", "PrismLauncher-data/meta"):
        meta = os.path.join(root, candidate)
        if os.path.isdir(meta):
            for uid, ver in [("net.minecraft", pack["minecraft"])] + common.loader_components(pack):
                if not os.path.exists(os.path.join(meta, uid, ver + ".json")):
                    problems.append(f"缺少组件元数据 {uid}/{ver}.json")
            break
    else:
        problems.append("缺少 meta/")

    gamedir = None
    for base in ("instances", "PrismLauncher-data/instances"):
        inst_root = os.path.join(root, base)
        if os.path.isdir(inst_root):
            for inst in sorted(os.listdir(inst_root)):
                path = os.path.join(inst_root, inst, "minecraft")
                if os.path.isdir(path):
                    gamedir = path
                    break
        if gamedir:
            break
    if not gamedir and os.path.isdir(os.path.join(root, ".minecraft")):
        gamedir = os.path.join(root, ".minecraft")
    if gamedir:
        mods = [f for f in os.listdir(os.path.join(gamedir, "mods")) if f.endswith(".jar")]
        want = sum(1 for m in common.load("mods.json") if m["enabled"])
        if len(mods) != want:
            problems.append(f"模组数量不符: {len(mods)} != {want}")
        rp = [f for f in os.listdir(os.path.join(gamedir, "resourcepacks")) if f.endswith(".zip")]
        if len(rp) != len(common.load("resourcepacks.json")):
            problems.append(f"材质包数量不符: {len(rp)}")
        sp = [f for f in os.listdir(os.path.join(gamedir, "shaderpacks")) if f.endswith(".zip")]
        if len(sp) != len(common.load("shaderpacks.json")):
            problems.append(f"光影包数量不符: {len(sp)}")
        if not os.path.exists(os.path.join(gamedir, "options.txt")):
            problems.append("缺少 options.txt")
        else:
            opts = open(os.path.join(gamedir, "options.txt"), encoding="utf-8").read()
            enabled = len([x for x in opts.splitlines() if x.startswith("resourcePacks:") and "file/" in x])
            if not enabled:
                problems.append("options.txt 里没有启用任何材质包")
    else:
        problems.append("缺少实例游戏目录")

    java_ok = False
    for base in ("java", "PrismLauncher-data/java"):
        jroot = os.path.join(root, base)
        if os.path.isdir(jroot):
            for _, _, files in os.walk(jroot):
                if "java" in files or "java.exe" in files:
                    java_ok = True
                    break
    if is_mmc:
        cfg = open(os.path.join(root, "instance.cfg"), encoding="utf-8").read()
        if "JavaPath=" in cfg:
            problems.append("MMC 包不应固定 JavaPath（由导入方启动器决定）")
    elif not java_ok:
        problems.append("缺少内置 Java")

    server = common.load("pack.json").get("server") or {}
    for base in (".", "PrismLauncher-data"):
        cfg_path = os.path.join(root, base, "prismlauncher.cfg")
        if os.path.exists(cfg_path):
            cfg = open(cfg_path, encoding="utf-8").read()
            for key, want in (
                ("IgnoreJavaWizard", "true"),
                ("AutomaticJavaSwitch", "true"),
                ("Language", "zh"),
                ("ApplicationTheme", "system"),
                ("IconTheme", "pe_colored"),
                ("AutomaticJavaDownload", "false"),
            ):
                if f"{key}={want}" not in cfg:
                    problems.append(f"prismlauncher.cfg 缺少 {key}={want}")
            break
    else:
        problems.append("缺少 prismlauncher.cfg")

    for base in (".", "PrismLauncher-data"):
        acc = os.path.join(root, base, "accounts.json")
        if os.path.exists(acc):
            import json as _json

            try:
                data = _json.load(open(acc, encoding="utf-8"))
            except Exception:
                problems.append("accounts.json 解析失败")
                break
            names = [a.get("profile", {}).get("name") for a in data.get("accounts", [])]
            if not names or not all(names):
                problems.append("accounts.json 里没有可用的离线账户")
            break
    else:
        problems.append("缺少 accounts.json（会弹首次登录向导）")

    for base in (".", "PrismLauncher-data"):
        upd = os.path.join(root, base, "prismlauncher_update.cfg")
        if os.path.exists(upd) and "auto_check=false" in open(upd, encoding="utf-8").read():
            break
    else:
        problems.append("缺少 prismlauncher_update.cfg auto_check=false（会检查更新）")

    if server and gamedir:
        dat = os.path.join(gamedir, "servers.dat")
        if not os.path.exists(dat):
            problems.append("缺少 servers.dat")
        elif server["ip"].encode() not in open(dat, "rb").read():
            problems.append(f"servers.dat 里没有 {server['ip']}")

    for base in (".", "PrismLauncher-data"):
        cfg_path = os.path.join(root, base, "prismlauncher.cfg")
        if os.path.exists(cfg_path) and "ProxyType=SOCKS5" in open(cfg_path, encoding="utf-8").read():
            break
    else:
        problems.append("prismlauncher.cfg 缺少死代理配置（占位账户会弹重新认证框）")

    inst_cfg = None
    for base in ("instances", "PrismLauncher-data/instances"):
        p = os.path.join(root, base, name, "instance.cfg")
        if os.path.exists(p):
            inst_cfg = p
            break
    if inst_cfg and "LowMemWarning=false" not in open(inst_cfg, encoding="utf-8").read():
        problems.append("instance.cfg 缺少 LowMemWarning=false（低内存机器会弹确认框）")

    meta_root = None
    for base in ("meta", "PrismLauncher-data/meta"):
        p = os.path.join(root, base)
        if os.path.isdir(p):
            meta_root = p
            break
    if meta_root:
        if not os.path.exists(os.path.join(meta_root, "index.json")):
            problems.append("meta 缺少 index.json（离线解析组件会失败）")
        for uid, ver in [("net.minecraft", pack["minecraft"])] + common.loader_components(pack):
            for rel in (f"{uid}/index.json", f"{uid}/{ver}.json"):
                if not os.path.exists(os.path.join(meta_root, rel)):
                    problems.append(f"meta 缺少 {rel}")

    trans_ok = any(
        os.path.exists(os.path.join(root, base, "mmc_zh.qm"))
        for base in ("translations", "PrismLauncher-data/translations")
    )
    if not trans_ok:
        problems.append("缺少中文翻译（启动器会去联网下载）")

    check_portable_extras(root, problems)
    check_runnable(root, problems)

    return problems


def _read(path):
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8", errors="replace").read()


def check_runnable(root, problems):
    """各平台「双击就能起来」的必要条件：实例目录、自带 Java、启动脚本、配置占位符。"""
    pack = common.load("pack.json")
    name = pack["name"]
    jre = "jre" + str(pack["java"]["major"])

    # 平台按产物自身的标志文件判断，不看宿主机
    is_windows = os.path.exists(os.path.join(root, "prismlauncher.exe"))
    apps = glob.glob(os.path.join(root, "*.app"))
    is_macos = bool(apps)
    is_linux = os.path.exists(os.path.join(root, "PrismLauncher"))
    if os.path.basename(root).endswith("-MMC"):
        return

    base = "PrismLauncher-data" if os.path.isdir(os.path.join(root, "PrismLauncher-data")) else "."
    inst_root = os.path.join(root, base, "instances")
    ids = [d for d in os.listdir(inst_root) if os.path.isdir(os.path.join(inst_root, d))] if os.path.isdir(inst_root) else []
    if not ids:
        problems.append("instances/ 里没有实例")
        return
    if len(ids) != 1:
        problems.append(f"instances/ 里有 {len(ids)} 个实例目录：{ids}")
    inst_id = ids[0]
    if not inst_id.isascii():
        problems.append(f"实例目录名不是 ASCII（Windows 上会因代码页出问题）：{inst_id}")

    inst_cfg = os.path.join(inst_root, inst_id, "instance.cfg")
    cfg = open(inst_cfg, encoding="utf-8").read()
    if f"name={name}" not in cfg:
        problems.append("instance.cfg 的显示名不是整合包名")
    if "JavaPath=__BUNDLED_JAVA__" not in cfg:
        problems.append("instance.cfg 缺少 JavaPath 占位符（启动脚本靠它写包内 Java）")
    if "LowMemWarning=false" not in cfg:
        problems.append("instance.cfg 缺少 LowMemWarning=false")

    java_root = os.path.join(root, base, "java")
    if is_macos:
        for arch in ("aarch64", "x64"):
            exe = os.path.join(java_root, f"{jre}-{arch}", "Contents", "Home", "bin", "java")
            if not os.path.exists(exe):
                problems.append(f"macOS 包缺少 {jre}-{arch} 的 java 可执行文件")
        for script in ("启动游戏.command", "启动正版.command"):
            path = os.path.join(root, script)
            if not os.path.exists(path):
                problems.append(f"macOS 包缺少 {script}")
            elif not os.access(path, os.X_OK):
                problems.append(f"{script} 没有可执行权限")
        text = _read(os.path.join(root, "启动游戏.command"))
        if text and "refresh_token" not in text:
            problems.append("启动游戏.command 缺少正版账号检测（登录微软后无法自动切正版）")
    elif is_windows:
        exe = os.path.join(java_root, jre, "bin", "java.exe")
        if not os.path.exists(exe):
            problems.append(f"Windows 包缺少包内 java.exe: {os.path.relpath(exe, root)}")
        for f in ("启动游戏.bat", "launch.ps1", "启动正版.bat"):
            if not os.path.exists(os.path.join(root, f)):
                problems.append(f"Windows 包缺少 {f}")
        for f in ("启动游戏.bat", "启动正版.bat"):
            bat = os.path.join(root, f)
            if os.path.exists(bat):
                raw = open(bat, "rb").read()
                if b"\r\r\n" in raw:
                    problems.append(f"{f} 的换行是 CRCRLF（cmd 会解析异常）")
                if b"-File" not in raw or b"launch.ps1" not in raw:
                    problems.append(f"{f} 没有用 -File 调用 launch.ps1")
        if os.path.exists(os.path.join(root, "启动正版.bat")) and b"-Mode msa" not in open(os.path.join(root, "启动正版.bat"), "rb").read():
            problems.append("启动正版.bat 没有传 -Mode msa")
        ps1 = os.path.join(root, "launch.ps1")
        if os.path.exists(ps1):
            raw = open(ps1, "rb").read()
            if not raw.startswith(b"\xef\xbb\xbf"):
                problems.append("launch.ps1 缺少 UTF-8 BOM（PowerShell 5.1 会把中文读成乱码）")
            if b"Start-Process" not in raw:
                problems.append("launch.ps1 没有启动启动器")
            text = raw.decode("utf-8-sig")
            if "refresh_token" not in text:
                problems.append("launch.ps1 缺少正版账号检测（登录微软后无法自动切正版）")
            if "ProxyType" not in text:
                problems.append("launch.ps1 缺少死代理维护逻辑（占位账号会弹重新认证框）")
    elif is_linux:
        exe = os.path.join(java_root, jre, "bin", "java")
        if not os.path.exists(exe):
            problems.append(f"Linux 包缺少包内 java: {os.path.relpath(exe, root)}")
        for script in ("启动游戏.sh", "启动正版.sh"):
            path = os.path.join(root, script)
            if not os.path.exists(path):
                problems.append(f"Linux 包缺少 {script}")
            elif not os.access(path, os.X_OK):
                problems.append(f"{script} 没有可执行权限")
        text = _read(os.path.join(root, "启动游戏.sh"))
        if text and "refresh_token" not in text:
            problems.append("启动游戏.sh 缺少正版账号检测（登录微软后无法自动切正版）")
    else:
        problems.append("无法判断平台（没有 prismlauncher.exe / *.app / PrismLauncher）")

    # 启动脚本里引用的实例 id 必须与实际目录一致
    for script in ("启动游戏.sh", "启动正版.sh", "启动游戏.command", "启动正版.command", "launch.ps1"):
        path = os.path.join(root, script)
        if os.path.exists(path):
            text = open(path, encoding="utf-8", errors="replace").read()
            if inst_id not in text:
                problems.append(f"{script} 里没有引用实例 {inst_id}")

    iris = os.path.join(inst_root, inst_id, "minecraft", "config", "iris.properties")
    if os.path.exists(iris):
        want = [l.split("=", 1)[1] for l in open(iris, encoding="utf-8").read().splitlines() if l.startswith("shaderPack=")]
        if want:
            sp_dir = os.path.join(inst_root, inst_id, "minecraft", "shaderpacks")
            have = set(os.listdir(sp_dir)) if os.path.isdir(sp_dir) else set()
            if want[0] not in have:
                problems.append(f"iris 默认光影不存在: {want[0]}")

    opts = os.path.join(inst_root, inst_id, "minecraft", "options.txt")
    rp_dir = os.path.join(inst_root, inst_id, "minecraft", "resourcepacks")
    if os.path.exists(opts) and os.path.isdir(rp_dir):
        line = [l for l in open(opts, encoding="utf-8").read().splitlines() if l.startswith("resourcePacks:[")]
        if line:

            def gson_unescape(s):
                # options.txt 里 resourcePacks 的值是 Gson 序列化的 JSON，会把 & ' " 等写成 \uXXXX
                return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)

            refs = [gson_unescape(r) for r in re.findall(r'file/([^"]+)"', line[0])]
            have = set(os.listdir(rp_dir))
            missing = [r for r in refs if r not in have]
            if missing:
                problems.append(f"options.txt 引用了不存在的材质包: {missing[:3]}")


def check_portable_extras(root, problems):
    """针对已经踩过的坑加回归检查，避免改包时静默退化。"""
    import glob
    import hashlib

    # 1) 启动器配置：必须关闭「使用系统 GLFW」（MC 26.x 要 GLFW 3.5）
    for cfg in glob.glob(os.path.join(root, "**", "prismlauncher.cfg"), recursive=True):
        text = open(cfg, encoding="utf-8").read()
        if "UseNativeGLFW=false" not in text:
            problems.append(f"{os.path.relpath(cfg, root)} 未关闭系统 GLFW（MC 26.x 需 GLFW 3.5）")

    # 2) 组件 meta 的 cachedSha256 必须与随包 meta 文件一致，否则启动要联网取元数据
    for manifest in glob.glob(os.path.join(root, "**", "mmc-pack.json"), recursive=True):
        data = json.load(open(manifest, encoding="utf-8"))
        meta_root = os.path.join(os.path.dirname(manifest), "meta")
        if not os.path.isdir(meta_root):
            continue
        for comp in data.get("components", []):
            path = os.path.join(meta_root, comp["uid"], comp["version"] + ".json")
            if not os.path.exists(path):
                problems.append(f"缺少组件 meta: {comp['uid']} {comp['version']}")
                continue
            sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
            if comp.get("cachedSha256") != sha:
                problems.append(f"{comp['uid']} 的 cachedSha256 与包内 meta 不一致（会触发联网更新）")

    # 3) options.txt 不能残留 Forge 修饰符键位（会让整个 options 加载失败）
    for opts in glob.glob(os.path.join(root, "**", "options.txt"), recursive=True):
        text = open(opts, encoding="utf-8").read()
        if "CONTROL_OR_COMMAND" in text or ":\u0000" in text:
            problems.append(f"{os.path.relpath(opts, root)} 残留 Forge 风格键位修饰符")

    # 4) 26.1 pack format 65 使用顶层 min/max；仅为旧格式兼容时保留 supported_formats。
    for packzip in glob.glob(os.path.join(root, "**", "resourcepacks", "*.zip"), recursive=True):
        try:
            import zipfile

            with zipfile.ZipFile(packzip) as z:
                meta = json.loads(z.read("pack.mcmeta"))
        except Exception:
            problems.append(f"材质包 mcmeta 读取失败: {os.path.basename(packzip)}")
            continue
        pack_meta = meta.get("pack", {})
        low, high = pack_meta.get("min_format"), pack_meta.get("max_format")
        sf = pack_meta.get("supported_formats")
        if not isinstance(low, int) or not isinstance(high, int) or low < 15 or high < low:
            problems.append(f"材质包 mcmeta 的 min_format/max_format 范围无效: {os.path.basename(packzip)}")
        elif low < 65:
            if pack_meta.get("pack_format") is None or sf != {"min_inclusive": low, "max_inclusive": high}:
                problems.append(f"旧格式材质包缺少匹配的 pack_format/supported_formats: {os.path.basename(packzip)}")
        elif "supported_formats" in pack_meta or "pack_format" in pack_meta:
            problems.append(f"新格式材质包仍带已移除的旧字段: {os.path.basename(packzip)}")

    # 5) iris 默认光影必须真实存在（光影回退版本后容易忘记改这里）
    for props in glob.glob(os.path.join(root, "**", "config", "iris.properties"), recursive=True):
        text = open(props, encoding="utf-8").read()
        want = None
        for line in text.splitlines():
            if line.startswith("shaderPack="):
                want = line.split("=", 1)[1].strip()
        if want and want != "(internal)" and want != "OFF":
            folder = os.path.join(os.path.dirname(os.path.dirname(props)), "shaderpacks")
            if not os.path.exists(os.path.join(folder, want)):
                problems.append(f"iris 默认光影不存在: {want}")


def check_mmc(root, name, problems):
    cfg = open(os.path.join(root, "instance.cfg"), encoding="utf-8").read()
    if "JavaPath=" in cfg:
        problems.append("MMC 包不应固定 JavaPath（由导入方启动器决定）")
    manifest = os.path.join(root, "mmc-pack.json")
    if not os.path.exists(manifest):
        problems.append("缺少 mmc-pack.json")
    else:
        import json as _json

        comps = {c["uid"]: c["version"] for c in _json.load(open(manifest, encoding="utf-8"))["components"]}
        pack = common.load("pack.json")
        if comps.get("net.minecraft") != pack["minecraft"]:
            problems.append(f"mmc-pack 的 MC 版本 {comps.get('net.minecraft')} != {pack['minecraft']}")
        for uid, ver in common.loader_components(pack):
            if comps.get(uid) != ver:
                problems.append(f"mmc-pack 的 {uid} {comps.get(uid)} != {ver}")
    game = os.path.join(root, ".minecraft")
    if not os.path.isdir(game):
        problems.append("缺少 .minecraft/")
        return problems
    mods = [f for f in os.listdir(os.path.join(game, "mods")) if f.endswith(".jar")]
    want = sum(1 for m in common.load("mods.json") if m["enabled"])
    if len(mods) != want:
        problems.append(f"模组数量不符: {len(mods)} != {want}")
    for sub in ("resourcepacks", "shaderpacks"):
        got = [f for f in os.listdir(os.path.join(game, sub)) if f.endswith(".zip")]
        if len(got) != len(common.load(sub + ".json")):
            problems.append(f"{sub} 数量不符: {len(got)}")
    opts = os.path.join(game, "options.txt")
    if not os.path.exists(opts):
        problems.append("缺少 options.txt")
    elif "file/" not in open(opts, encoding="utf-8").read():
        problems.append("options.txt 里没有启用材质包")
    return problems


def main():
    roots = [
        os.path.join(common.DIST, d)
        for d in sorted(os.listdir(common.DIST))
        if os.path.isdir(os.path.join(common.DIST, d)) and d.startswith(common.load("pack.json")["name"])
    ]
    if not roots:
        print("dist/ 里没有产物")
        return 1
    failed = 0
    for root in roots:
        problems = check_bundle(root)
        status = "OK" if not problems else "有问题"
        print(f"{status}  {os.path.basename(root)}")
        for p in problems:
            print("   -", p)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
