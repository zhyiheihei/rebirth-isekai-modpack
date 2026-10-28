#!/usr/bin/env python3
"""构建产物自检：确认「启动免下载」所需的资源都在包里。"""
import json
import os
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
    for base in ("instances", "PrismLauncher-data/instances", ""):
        path = os.path.join(root, base, name, "minecraft")
        if os.path.isdir(path):
            gamedir = path
            break
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

    if server:
        for base in ("instances", "PrismLauncher-data/instances", ""):
            dat = os.path.join(root, base, name, "minecraft", "servers.dat")
            if not os.path.exists(dat):
                dat = os.path.join(root, base, ".minecraft", "servers.dat")
            if os.path.exists(dat):
                if server["ip"].encode() not in open(dat, "rb").read():
                    problems.append(f"servers.dat 里没有 {server['ip']}")
                break
        else:
            problems.append("缺少 servers.dat")

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

    return problems


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

    # 4) 材质包 mcmeta 必须是 26.x 的 min_format/max_format
    for packzip in glob.glob(os.path.join(root, "**", "resourcepacks", "*.zip"), recursive=True):
        try:
            import zipfile

            with zipfile.ZipFile(packzip) as z:
                meta = json.loads(z.read("pack.mcmeta"))
        except Exception:
            problems.append(f"材质包 mcmeta 读取失败: {os.path.basename(packzip)}")
            continue
        sf = meta.get("pack", {}).get("supported_formats")
        if not isinstance(sf, dict) or "min_format" not in sf or "max_format" not in sf:
            problems.append(f"材质包 mcmeta 字段不兼容 26.x: {os.path.basename(packzip)}")

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
