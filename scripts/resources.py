"""从 Mojang / NeoForge / Prism 元数据下载游戏本体资源（客户端 jar、库、素材）。

产物落在 cache/resources/：
  libraries/          全部平台的库（含原生库）
  assets/indexes/     素材索引
  assets/objects/     素材对象
  meta/<uid>/<ver>.json  组件元数据（随包分发，离线时启动器不用再拉）
"""
import json
import os

import common

META = "https://meta.prismlauncher.org/v1"
LIBRARY_HOSTS = ("https://libraries.minecraft.net/", "https://maven.neoforged.net/releases/")
OS_NAMES = {"linux", "windows", "osx", "osx-arm64"}


def _get_json(url):
    return common.fetch_json(url)


def _rules_allow_any(lib):
    rules = lib.get("rules")
    if not rules:
        return True
    for rule in rules:
        os_name = (rule.get("os") or {}).get("name")
        if rule.get("action") == "allow" and (os_name in OS_NAMES or not os_name):
            return True
    return False


def _path_of(name):
    parts = name.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    rel = "/".join(group.split(".")) + f"/{artifact}/{version}/{artifact}-{version}"
    if classifier:
        rel += "-" + classifier
    return rel + ".jar"


def _download_lib(lib, libdir):
    rel = _path_of(lib["name"])
    dest = os.path.join(libdir, rel)
    artifact = (lib.get("downloads") or {}).get("artifact") or {}
    url = artifact.get("url")
    sha1 = artifact.get("sha1")
    if not url:
        url = LIBRARY_HOSTS[0] + rel
        if not common.download(url, dest, sha1, "sha1", retries=1, quiet=True):
            url = LIBRARY_HOSTS[1] + rel
    return common.download(url, dest, sha1, "sha1", retries=2, quiet=True), rel


def components(pack):
    comps = [("net.minecraft", pack["minecraft"])]
    mc = _get_json(f"{META}/net.minecraft/{pack['minecraft']}.json")
    for req in mc.get("requires", []):
        if req.get("uid") == "org.lwjgl3":
            version = req.get("equals") or req.get("suggests")
            if version:
                comps.append(("org.lwjgl3", version))
    loader = pack["loader"]
    if loader["type"] == "neoforge":
        comps.append(("net.neoforged", loader["version"]))
    return comps, mc


def fetch(pack=None):
    """拉取资源到 cache/resources，返回目录。已存在的文件会跳过。"""
    pack = pack or common.load("pack.json")
    root = os.path.join(common.CACHE, "resources")
    libdir = common.ensure_dir(os.path.join(root, "libraries"))
    asset_dir = common.ensure_dir(os.path.join(root, "assets"))
    meta_dir = common.ensure_dir(os.path.join(root, "meta"))

    comps, mc = components(pack)
    total = fetched = 0
    for uid, version in comps:
        data = _get_json(f"{META}/{uid}/{version}.json")
        os.makedirs(os.path.join(meta_dir, uid), exist_ok=True)
        with open(os.path.join(meta_dir, uid, f"{version}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        libs = [lib for lib in data.get("libraries", []) if _rules_allow_any(lib)]
        if data.get("mainJar"):
            libs.append(data["mainJar"])
        for lib in libs:
            total += 1
            ok, _ = _download_lib(lib, libdir)
            fetched += 1 if ok else 0
        print(f"  {uid}/{version}: {len(libs)} 个库", flush=True)

    index = mc.get("assetIndex") or {}
    if index.get("url"):
        os.makedirs(os.path.join(asset_dir, "indexes"), exist_ok=True)
        index_path = os.path.join(asset_dir, "indexes", index["id"] + ".json")
        if common.download(index["url"], index_path, index.get("sha1"), "sha1"):
            with open(index_path, encoding="utf-8") as f:
                objects = json.load(f)["objects"]
            pairs = [
                (
                    f"https://resources.download.minecraft.net/{obj['hash'][:2]}/{obj['hash']}",
                    os.path.join(asset_dir, "objects", obj["hash"][:2], obj["hash"]),
                    obj["hash"],
                )
                for obj in objects.values()
            ]
            failed = common.download_many(pairs)
            print(
                f"  素材 index {index['id']}: {len(objects)} 个对象，失败 {len(failed)}",
                flush=True,
            )
            print(f"  素材 index {index['id']}: {len(objects)} 个对象", flush=True)

    log = (mc.get("logging") or {}).get("file") or {}
    if log.get("url"):
        common.ensure_dir(os.path.join(root, "logs"))
        common.download(
            log["url"], os.path.join(root, "logs", os.path.basename(log["url"])), log.get("sha1"), "sha1"
        )
    print(f"  库 {fetched}/{total}", flush=True)
    return root


if __name__ == "__main__":
    fetch()
