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
            for uid, ver in (
                ("net.minecraft", pack["minecraft"]),
                ("net.neoforged", pack["loader"]["version"]),
            ):
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
        for uid, ver in (
            ("net.minecraft", pack["minecraft"]),
            ("net.neoforged", pack["loader"]["version"]),
        ):
            for rel in (f"{uid}/index.json", f"{uid}/{ver}.json"):
                if not os.path.exists(os.path.join(meta_root, rel)):
                    problems.append(f"meta 缺少 {rel}")

    trans_ok = any(
        os.path.exists(os.path.join(root, base, "mmc_zh.qm"))
        for base in ("translations", "PrismLauncher-data/translations")
    )
    if not trans_ok:
        problems.append("缺少中文翻译（启动器会去联网下载）")

    return problems


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
        if comps.get("net.neoforged") != pack["loader"]["version"]:
            problems.append(f"mmc-pack 的 NeoForge {comps.get('net.neoforged')} != {pack['loader']['version']}")
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
        if os.path.isdir(os.path.join(common.DIST, d))
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
