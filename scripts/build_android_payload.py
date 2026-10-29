#!/usr/bin/env python3
"""Build the Android payload bundled inside the FCL fork APK.

The payload is a zip with everything a player would otherwise download on first
launch: Minecraft assets, the libraries the merged version json references, the
client jar and the modpack instance (mods/config/resourcepacks/servers.dat).

Layout matches FCL's shared game directory (`/storage/emulated/0/FCL/.minecraft`):

    assets/indexes/30.json, assets/objects/xx/<hash>
    libraries/<maven path>
    versions/<VERSION_ID>/<VERSION_ID>.json, <VERSION_ID>.jar, mods/, config/, ...

Usage:
    python3 scripts/build_android_payload.py            # build + verify
    python3 scripts/build_android_payload.py --no-zip   # only stage the tree
"""
import argparse
import json
import os
import shutil
import sys
import zipfile

import common

VERSION_ID = "RebirthIsekai"
VANILLA_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_PROFILE = "https://meta.fabricmc.net/v2/versions/loader/{mc}/{loader}/profile/json"

# 已压缩过的格式不再 deflate，省时间也几乎不损失体积
STORE_EXT = (".jar", ".zip", ".ogg", ".png", ".jpg", ".jpeg", ".webp", ".nbt", ".dat", ".ttf", ".otf")


def cache_dir():
    path = os.path.join(common.CACHE, "android")
    common.ensure_dir(path)
    return path


def fetch_json(url, name):
    path = os.path.join(cache_dir(), name)
    if not os.path.isfile(path):
        if not common.download(url, path):
            raise SystemExit(f"下载失败: {url}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_file(url, name):
    path = os.path.join(cache_dir(), name)
    if not os.path.isfile(path):
        if not common.download(url, path):
            raise SystemExit(f"下载失败: {url}")
    return path


def vanilla_json(mc):
    manifest = fetch_json(VANILLA_MANIFEST, "version_manifest.json")
    entry = next((v for v in manifest["versions"] if v["id"] == mc), None)
    if entry is None:
        raise SystemExit(f"官方版本清单里没有 {mc}")
    return fetch_json(entry["url"], f"version_{mc}.json")


def fabric_profile(mc, loader):
    return fetch_json(
        FABRIC_PROFILE.format(mc=mc, loader=loader), f"fabric_{loader}_{mc}.json"
    )


def library_path(lib):
    artifact = (lib.get("downloads") or {}).get("artifact") or {}
    if artifact.get("path"):
        return artifact["path"]
    parts = lib["name"].split(":")
    group, artifact_id, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    rel = "/".join(group.split(".")) + f"/{artifact_id}/{version}/{artifact_id}-{version}"
    if classifier:
        rel += "-" + classifier
    return rel + ".jar"


def allows_linux(lib):
    """跳过只为别的系统准备的库；LWJGL 整套由 FCL 自带的 natives 接管。"""
    name = lib.get("name", "")
    if name.startswith("org.lwjgl:"):
        return False
    if ":natives-windows" in name or ":natives-macos" in name or ":natives-osx" in name:
        return False
    rules = lib.get("rules")
    if not rules:
        return True
    for rule in rules:
        os_name = (rule.get("os") or {}).get("name")
        if rule.get("action") == "allow" and os_name in (None, "linux"):
            return True
    return False


def merge_version(vanilla, fabric, version_id):
    merged = dict(vanilla)
    merged.pop("inheritsFrom", None)
    merged["id"] = version_id
    merged["mainClass"] = fabric["mainClass"]
    merged["type"] = fabric.get("type") or vanilla.get("type", "release")

    libraries = [lib for lib in vanilla.get("libraries", []) if allows_linux(lib)]
    seen = {lib["name"] for lib in libraries}
    for lib in fabric.get("libraries", []):
        if lib["name"] not in seen:
            libraries.append(lib)
            seen.add(lib["name"])
    merged["libraries"] = libraries

    arguments = dict(vanilla.get("arguments") or {})
    fabric_args = fabric.get("arguments") or {}
    for key in ("game", "jvm"):
        extra = fabric_args.get(key) or []
        if extra:
            arguments[key] = list(arguments.get(key) or []) + list(extra)
    if arguments:
        merged["arguments"] = arguments
    return merged


def stage_tree(root, pack, android, version_json):
    """把 assets / libraries / versions/<id> 铺进 root。"""
    resources = os.path.join(common.CACHE, "resources")

    # 1) 素材：只带当前 assetIndex 的索引与对象
    index_id = version_json["assetIndex"]["id"]
    assets_src = os.path.join(resources, "assets")
    assets_dst = common.ensure_dir(os.path.join(root, "assets"))
    common.ensure_dir(os.path.join(assets_dst, "indexes"))
    shutil.copy2(
        os.path.join(assets_src, "indexes", f"{index_id}.json"),
        os.path.join(assets_dst, "indexes", f"{index_id}.json"),
    )
    objects_dst = common.ensure_dir(os.path.join(assets_dst, "objects"))
    objects_src = os.path.join(assets_src, "objects")
    count = 0
    for prefix in sorted(os.listdir(objects_src)):
        src_dir = os.path.join(objects_src, prefix)
        if not os.path.isdir(src_dir):
            continue
        dst_dir = common.ensure_dir(os.path.join(objects_dst, prefix))
        for name in os.listdir(src_dir):
            common.link_or_copy(os.path.join(src_dir, name), os.path.join(dst_dir, name))
            count += 1
    print(f"  assets: {count} 个对象（index {index_id}）", flush=True)

    # 2) 运行库：只带版本 json 真正引用的 jar
    libs_src = os.path.join(resources, "libraries")
    libs_dst = common.ensure_dir(os.path.join(root, "libraries"))
    missing = []
    total = 0
    for lib in version_json["libraries"]:
        rel = library_path(lib)
        src = os.path.join(libs_src, rel)
        dst = os.path.join(libs_dst, rel)
        if not os.path.isfile(src):
            artifact = (lib.get("downloads") or {}).get("artifact") or {}
            url = artifact.get("url")
            if not url:
                base = lib.get("url")
                if not base:
                    missing.append(rel)
                    continue
                url = base.rstrip("/") + "/" + rel
            common.ensure_dir(os.path.dirname(dst))
            if common.download(url, dst):
                total += 1
                continue
            missing.append(rel)
            continue
        common.link_or_copy(src, dst)
        total += 1
    print(f"  libraries: {total} 个 jar", flush=True)
    if missing:
        raise SystemExit(f"缺少运行库: {missing[:5]}")

    # 3) 实例目录
    version_dir = common.ensure_dir(os.path.join(root, "versions", VERSION_ID))
    with open(os.path.join(version_dir, f"{VERSION_ID}.json"), "w", encoding="utf-8") as f:
        json.dump(version_json, f, ensure_ascii=False, indent=2)

    client = version_json["downloads"]["client"]
    jar_src = fetch_file(client["url"], f"client_{pack['minecraft']}.jar")
    if common.sha("sha1", jar_src) != client["sha1"]:
        raise SystemExit("客户端 jar 校验失败")
    common.link_or_copy(jar_src, os.path.join(version_dir, f"{VERSION_ID}.jar"))

    excluded = set(android.get("exclude_mod_files", []))
    mods_dir = common.ensure_dir(os.path.join(version_dir, "mods"))
    mods = 0
    for m in common.load("mods.json"):
        if not m["enabled"] or m["file"] in excluded:
            continue
        common.link_or_copy(os.path.join(common.CACHE, "mods", m["file"]), os.path.join(mods_dir, m["file"]))
        mods += 1
    print(f"  mods: {mods} 个", flush=True)

    shutil.copytree(os.path.join(common.PACK, "config"), os.path.join(version_dir, "config"), dirs_exist_ok=True)
    shutil.copy2(os.path.join(common.PACK, "options.txt"), os.path.join(version_dir, "options.txt"))

    if android.get("include_resourcepacks", True):
        rp_dir = common.ensure_dir(os.path.join(version_dir, "resourcepacks"))
        for e in common.load("resourcepacks.json"):
            common.normalize_resourcepack(
                os.path.join(common.LOCAL, "resourcepacks", e["file"]),
                os.path.join(rp_dir, e["file"]),
            )

    # 光影默认关闭：Android 上首次启动不加载光影
    iris = os.path.join(version_dir, "config", "iris.properties")
    if os.path.isfile(iris):
        lines = []
        for line in open(iris, encoding="utf-8").read().splitlines():
            if line.startswith("enableShaders="):
                line = "enableShaders=false"
            lines.append(line)
        open(iris, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    import servers

    srv = pack.get("server")
    if srv:
        servers.write(os.path.join(version_dir, "servers.dat"), [{"name": srv["name"], "ip": srv["ip"]}])


def write_zip(root, output):
    entries = []
    for base, _, files in os.walk(root):
        for name in files:
            full = os.path.join(base, name)
            entries.append((full, os.path.relpath(full, root).replace(os.sep, "/")))
    entries.sort(key=lambda item: item[1])
    raw = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for full, rel in entries:
            raw += os.path.getsize(full)
            if rel.lower().endswith(STORE_EXT):
                info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as src, zf.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
            else:
                zf.write(full, rel)
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true", help="只铺目录，不打包")
    ap.add_argument("--keep", action="store_true", help="保留上次铺开的目录")
    args = ap.parse_args()

    pack = common.load("pack.json")
    android = common.load("android.json")
    mc = pack["minecraft"]
    loader = pack["loader"]["version"]

    print(f"[payload] Minecraft {mc} / Fabric {loader} / 实例 {VERSION_ID}", flush=True)
    version_json = merge_version(vanilla_json(mc), fabric_profile(mc, loader), VERSION_ID)

    root = os.path.join(common.CACHE, "android", "payload")
    if os.path.isdir(root) and not args.keep:
        shutil.rmtree(root)
    common.ensure_dir(root)
    stage_tree(root, pack, android, version_json)

    properties = os.path.join(root, "payload.properties")
    with open(properties, "w", encoding="utf-8") as f:
        f.write(f"payloadVersion={pack['version']}-android-{android.get('revision', 1)}\n")
        f.write(f"versionId={VERSION_ID}\n")
        f.write("offlineName=\n")

    if args.no_zip:
        print(f"[payload] 目录就绪: {root}", flush=True)
        return

    output = os.path.join(common.CACHE, "android", "payload.zip")
    raw = write_zip(root, output)
    size = os.path.getsize(output)
    print(f"[payload] {output}: {size / 2**20:.0f} MiB（原始 {raw / 2**20:.0f} MiB）", flush=True)
    print(f"[payload] sha256 {common.sha('sha256', output)}", flush=True)


if __name__ == "__main__":
    main()
