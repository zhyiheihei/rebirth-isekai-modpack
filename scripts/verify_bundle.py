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

    def need(rel, what):
        if not os.path.exists(os.path.join(root, rel)):
            problems.append(f"缺少{what}: {rel}")

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
    for base in ("instances", "PrismLauncher-data/instances"):
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
    if not java_ok:
        problems.append("缺少内置 Java")

    trans_ok = any(
        os.path.exists(os.path.join(root, base, "mmc_zh.qm"))
        for base in ("translations", "PrismLauncher-data/translations")
    )
    if not trans_ok:
        problems.append("缺少中文翻译（启动器会去联网下载）")

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
        if root.endswith("-MMC"):
            continue
        problems = check_bundle(root)
        status = "OK" if not problems else "有问题"
        print(f"{status}  {os.path.basename(root)}")
        for p in problems:
            print("   -", p)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
