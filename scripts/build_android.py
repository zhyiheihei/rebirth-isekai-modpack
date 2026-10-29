#!/usr/bin/env python3
"""Build an experimental FCL-importable Modrinth pack; this is not an APK."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import common
import servers

PACK = Path(common.PACK)
CACHE = Path(common.CACHE)
LOCAL = Path(common.LOCAL)
DIST = Path(common.DIST)


def digest(path, algorithm):
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def zip_file(zf, path, arcname):
    path = Path(path)
    compression = zipfile.ZIP_STORED if path.suffix.lower() in {".jar", ".zip"} else zipfile.ZIP_DEFLATED
    zf.write(path, arcname, compress_type=compression)


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise ValueError(f"不安全的文件名: {name}")
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="输出 .mrpack 路径（缺省为 dist/）")
    args = parser.parse_args()

    pack = common.load("pack.json")
    android = common.load("android.json")
    if android.get("format") != "modrinth-mrpack" or android.get("launcher") != "FCL":
        raise SystemExit("pack/android.json 的 launcher/format 配置不匹配")

    version = pack["version"]
    revision = int(android.get("revision", 1))
    output = Path(args.output) if args.output else DIST / f"Rebirth-Isekai-{version}-Android-FCL-r{revision}.mrpack"
    output.parent.mkdir(parents=True, exist_ok=True)

    excluded = set(android.get("exclude_mod_files", []))
    mods = [m for m in common.load("mods.json") if m.get("enabled") and m["file"] not in excluded]
    found_exclusions = {m["file"] for m in common.load("mods.json")} & excluded
    unknown = excluded - found_exclusions
    if unknown:
        raise SystemExit(f"pack/android.json 排除了不存在的模组: {sorted(unknown)}")

    dependencies = {
        "minecraft": pack["minecraft"],
        "fabric-loader": pack["loader"]["version"],
    }
    entries = []
    local_mods = []

    with tempfile.TemporaryDirectory(prefix="rebirth-android-") as tmp:
        stage = Path(tmp)
        overrides = stage / "overrides"
        overrides.mkdir()
        for subdir in ("mods", "config", "resourcepacks"):
            (overrides / subdir).mkdir()

        for mod in mods:
            filename = safe_name(mod["file"])
            cache_file = CACHE / "mods" / filename
            if not cache_file.is_file():
                raise SystemExit(f"模组缓存缺失，请先运行 scripts/fetch.py: {filename}")
            if mod.get("sha512") and digest(cache_file, "sha512") != mod["sha512"]:
                raise SystemExit(f"模组 sha512 校验失败: {filename}")
            if mod.get("local") or not mod.get("url"):
                shutil.copy2(cache_file, overrides / "mods" / filename)
                local_mods.append(filename)
                continue

            entries.append({
                "path": f"mods/{filename}",
                "hashes": {
                    "sha1": digest(cache_file, "sha1"),
                    "sha512": digest(cache_file, "sha512"),
                },
                "env": {"client": "required", "server": "unsupported"},
                "downloads": [mod["url"]],
                "fileSize": cache_file.stat().st_size,
            })

        shutil.copytree(PACK / "config", overrides / "config", dirs_exist_ok=True)
        options = PACK / "options.txt"
        shutil.copy2(options, overrides / "options.txt")

        # FCL 的 Android 渲染器由设备/驱动决定；先禁用未经实机验证的桌面光影，避免启动即黑屏。
        iris = overrides / "config" / "iris.properties"
        if iris.exists():
            lines = iris.read_text(encoding="utf-8").splitlines()
            values = {line.split("=", 1)[0]: line for line in lines if "=" in line}
            values["enableShaders"] = "enableShaders=false"
            values["shaderPack"] = "shaderPack="
            patched = []
            seen = set()
            for line in lines:
                key = line.split("=", 1)[0] if "=" in line else None
                if key in {"enableShaders", "shaderPack"}:
                    if key not in seen:
                        patched.append(values[key])
                        seen.add(key)
                else:
                    patched.append(line)
            for key in ("enableShaders", "shaderPack"):
                if key not in seen:
                    patched.append(values[key])
            iris.write_text("\n".join(patched) + "\n", encoding="utf-8")

        resourcepacks = []
        if android.get("include_resourcepacks", True):
            for item in common.load("resourcepacks.json"):
                filename = safe_name(item["file"])
                source = LOCAL / "resourcepacks" / filename
                if not source.is_file() or digest(source, "sha256") != item["sha256"]:
                    raise SystemExit(f"材质包缺失或 sha256 校验失败: {filename}")
                common.normalize_resourcepack(source, overrides / "resourcepacks" / filename)
                resourcepacks.append(filename)

        if android.get("include_shaderpacks", False):
            shader_dir = overrides / "shaderpacks"
            shader_dir.mkdir()
            for item in common.load("shaderpacks.json"):
                filename = safe_name(item["file"])
                source = LOCAL / "shaderpacks" / filename
                if not source.is_file() or digest(source, "sha256") != item["sha256"]:
                    raise SystemExit(f"光影包缺失或 sha256 校验失败: {filename}")
                shutil.copy2(source, shader_dir / filename)

        server = pack.get("server") or {}
        if server:
            (overrides / "servers.dat").write_bytes(servers.build([{
                "name": server["name"],
                "ip": server["ip"],
            }]))

        manifest = {
            "game": "minecraft",
            "formatVersion": 1,
            "versionId": f"{version}-android-fcl-r{revision}",
            "name": f"{pack['name']} Android 测试版 r{revision}",
            "summary": "FCL 导入包；Android 实机兼容性验证中。需要正版 Minecraft Java Edition 账号。",
            "files": entries,
            "dependencies": dependencies,
        }
        (stage / "modrinth.index.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (stage / "README.txt").write_text(
            f"重生：异世界冒险 Android/FCL 测试包 r{revision}\n\n"
            "本文件是 FCL 可导入的 Modrinth 格式整合包，不是 APK，也不包含 Minecraft 本体、游戏资源或账号信息。\n"
            "请从 FCL 官方渠道安装启动器，使用正版微软账号登录后导入本文件。\n"
            "当前全量模组集尚未完成 Android 实机验证；首次测试关闭了光影。出现崩溃时请保存 FCL 日志，\n"
            "按日志定位具体不兼容模组后再更新 pack/android.json 的排除清单。\n",
            encoding="utf-8",
        )

        temporary = output.with_suffix(output.suffix + ".tmp")
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as zf:
            for source in sorted(stage.rglob("*")):
                if source.is_file():
                    zip_file(zf, source, source.relative_to(stage).as_posix())
        os.replace(temporary, output)

    print(f"输出: {output}")
    print(f"Minecraft {pack['minecraft']} / Fabric {pack['loader']['version']} / FCL profile r{revision}")
    print(f"Modrinth 下载模组: {len(entries)}；随包本地模组: {len(local_mods)}")
    print(f"材质包: {len(resourcepacks)}；光影包: {len(common.load('shaderpacks.json')) if android.get('include_shaderpacks', False) else 0}")
    print("Android 实机状态: 未验证（此包用于 FCL 导入测试）")
    print(f"SHA-256: {digest(output, 'sha256')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"构建失败: {exc}", file=sys.stderr)
        raise SystemExit(1)
