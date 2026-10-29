#!/usr/bin/env python3
"""Verify the FCL Modrinth pack layout and its relationship to repository manifests."""
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import common


def fail(message):
    raise SystemExit(f"FAIL: {message}")


def zip_digest(zf, member, algorithm):
    h = hashlib.new(algorithm)
    with zf.open(member) as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    pack = common.load("pack.json")
    android = common.load("android.json")
    revision = int(android.get("revision", 1))
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(common.DIST) / f"Rebirth-Isekai-{pack['version']}-Android-FCL-r{revision}.mrpack"
    if not output.is_file():
        fail(f"找不到文件: {output}")

    with zipfile.ZipFile(output) as zf:
        bad = zf.testzip()
        if bad:
            fail(f"zip CRC 错误: {bad}")
        names = set(zf.namelist())
        if "modrinth.index.json" not in names or not any(n.startswith("overrides/") for n in names):
            fail("缺少 Modrinth manifest 或 overrides 目录")
        manifest = json.loads(zf.read("modrinth.index.json"))
        if manifest.get("formatVersion") != 1 or manifest.get("game") != "minecraft":
            fail("不是 Modrinth mrpack formatVersion 1")
        deps = manifest.get("dependencies", {})
        if deps.get("minecraft") != pack["minecraft"] or deps.get("fabric-loader") != pack["loader"]["version"]:
            fail(f"游戏/加载器版本不符: {deps}")
        if manifest.get("versionId") != f"{pack['version']}-android-fcl-r{revision}":
            fail("Android profile 修订号与 pack/android.json 不一致")

        expected = {
            m["file"]: m for m in common.load("mods.json")
            if m.get("enabled") and m["file"] not in set(android.get("exclude_mod_files", []))
        }
        indexed = {}
        for entry in manifest.get("files", []):
            path = entry.get("path", "")
            if not path.startswith("mods/") or path.count("/") != 1:
                fail(f"模组路径不规范: {path}")
            filename = path.split("/", 1)[1]
            if filename not in expected or filename in indexed:
                fail(f"清单出现未知或重复模组: {filename}")
            indexed[filename] = entry
            if entry.get("downloads") != [expected[filename].get("url")]:
                fail(f"下载地址与仓库清单不一致: {filename}")
            cache_file = common.CACHE + "/mods/" + filename
            hashes = entry.get("hashes", {})
            if not hashes.get("sha1") or hashes.get("sha512") != expected[filename].get("sha512"):
                fail(f"模组哈希缺失或与仓库清单不一致: {filename}")
            if not os.path.isfile(cache_file):
                fail(f"校验需要本地 mod 缓存: {filename}")
            if common.sha("sha1", cache_file) != hashes["sha1"] or common.sha("sha512", cache_file) != hashes["sha512"]:
                fail(f"模组哈希与缓存文件不符: {filename}")
            if entry.get("fileSize") != os.path.getsize(cache_file):
                fail(f"模组文件大小不符: {filename}")

        local = {name for name, item in expected.items() if item.get("local") or not item.get("url")}
        remote = set(expected) - local
        if set(indexed) != remote:
            fail(f"远程模组集合不符: index={len(indexed)} expected={len(remote)}")
        for filename in local:
            member = f"overrides/mods/{filename}"
            if member not in names:
                fail(f"本地模组未放入 overrides/mods: {filename}")
            if hashlib.sha512(zf.read(member)).hexdigest() != expected[filename].get("sha512"):
                fail(f"随包本地模组 sha512 不符: {filename}")
        if any(n.startswith("overrides/shaderpacks/") for n in names) != bool(android.get("include_shaderpacks")):
            fail("光影目录是否打包与 pack/android.json 不一致")
        if not android.get("include_shaderpacks"):
            iris = zf.read("overrides/config/iris.properties").decode("utf-8")
            iris_lines = iris.splitlines()
            if "enableShaders=false" not in iris_lines or "shaderPack=" not in iris_lines:
                fail("Android 首次测试必须禁用 Iris 光影")

        if android.get("include_resourcepacks", True):
            wanted = {f"overrides/resourcepacks/{item['file']}" for item in common.load("resourcepacks.json")}
            missing = wanted - names
            if missing:
                fail(f"缺少材质包: {sorted(missing)[:3]}")
            assets = {item["file"]: item for item in common.load("resourcepacks.json")}
            for filename, item in assets.items():
                member = f"overrides/resourcepacks/{filename}"
                with zipfile.ZipFile(io.BytesIO(zf.read(member))) as resourcepack:
                    pack_meta = json.loads(resourcepack.read("pack.mcmeta")).get("pack", {})
                low, high = pack_meta.get("min_format"), pack_meta.get("max_format")
                supported = pack_meta.get("supported_formats")
                if not isinstance(low, int) or not isinstance(high, int) or low < 15 or high < low:
                    fail(f"材质包 min_format/max_format 范围无效: {filename}")
                if low < 65:
                    if pack_meta.get("pack_format") is None or supported != {"min_inclusive": low, "max_inclusive": high}:
                        fail(f"旧格式材质包兼容字段不匹配: {filename}")
                elif "pack_format" in pack_meta or "supported_formats" in pack_meta:
                    fail(f"新格式材质包保留了旧字段: {filename}")

        if "overrides/servers.dat" not in names:
            fail("未预置服务端列表")
        if any("accounts.json" in n or n.startswith("assets/") for n in names):
            fail("不应打包账号或 Minecraft assets")

    print(f"OK  {output}")
    print(f"Minecraft {pack['minecraft']} / Fabric {pack['loader']['version']} / FCL Modrinth import r{revision}")
    print(f"模组 {len(expected)}（Modrinth 下载 {len(remote)} / 本地覆盖 {len(local)}）")
    print("当前状态：Android 实机未验证")


if __name__ == "__main__":
    main()
