#!/usr/bin/env python3
"""Axiom 简中资源包的维护脚本：跟随 Axiom 最新版，不锁定具体版本号。

用法：
    python scripts/axiom_zh.py check            # 对比当前资源包与 Axiom 最新版的语言键
    python scripts/axiom_zh.py check --mc 26.1.2
    python scripts/axiom_zh.py repack           # 用现有译文重新打包，并同步清单/options.txt
    python scripts/axiom_zh.py repack --jar D:/Axiom.jar   # 离线：本地 jar 取语言键

要点：
- 只做 HTTP Range 读取，不下载 40MB+ 的 jar；
- 现有译文是唯一数据源（取自 zip 内的 zh_cn.json），无需额外源文件；
- 新增键不自动机翻，只报告出来，由人补译（避免出现半吊子英文混中文）。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_NAME = "Axiom-简中汉化.zip"
PACK_DIR = os.path.join(ROOT, "pack", "resourcepacks-local")
PACK_PATH = os.path.join(PACK_DIR, PACK_NAME)
LIST_PATH = os.path.join(ROOT, "pack", "resourcepacks.json")
OPTIONS_PATH = os.path.join(ROOT, "pack", "options.txt")
LANG_ENTRY = "assets/axiom/lang/zh_cn.json"
SRC_ENTRY = "assets/axiom/lang/en_us.json"
PROJECT = "N6n5dqoA"


class HttpFile(io.RawIOBase):
    """把 HTTP Range 伪装成可随机读取的文件，供 zipfile 直接解析远端 jar。"""

    def __init__(self, url: str, size: int):
        self.url = url
        self._size = size
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        else:
            self.pos = self._size + offset
        return self.pos

    def readinto(self, buf):
        if not buf or self.pos >= self._size:
            return 0
        end = min(self.pos + len(buf), self._size) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        buf[: len(data)] = data
        self.pos += len(data)
        return len(data)

    def read(self, size=-1):
        if size is None or size < 0:
            size = self._size - self.pos
        buf = bytearray(size)
        got = self.readinto(buf)
        return bytes(buf[:got])


def latest_release(mc: str | None = None) -> dict:
    url = f"https://api.modrinth.com/v2/project/{PROJECT}/version"
    with urllib.request.urlopen(url, timeout=30) as resp:
        versions = json.load(resp)
    if mc:
        versions = [v for v in versions if mc in v["game_versions"]]
    if not versions:
        raise SystemExit(f"没有找到匹配的 Axiom 版本（mc={mc}）")
    return max(versions, key=lambda v: v["date_published"])


def read_source_keys(mc: str | None, jar: str | None) -> tuple[dict, str]:
    if jar:
        with zipfile.ZipFile(jar) as z:
            return json.loads(z.read(SRC_ENTRY).decode("utf-8-sig")), os.path.basename(jar)
    version = latest_release(mc)
    f = version["files"][0]
    with zipfile.ZipFile(HttpFile(f["url"], f["size"])) as z:
        data = json.loads(z.read(SRC_ENTRY).decode("utf-8-sig"))
    return data, f"{version['version_number']} ({'/'.join(version['game_versions'])})"


def read_pack() -> dict:
    if not os.path.exists(PACK_PATH):
        raise SystemExit(f"找不到资源包：{PACK_PATH}")
    with zipfile.ZipFile(PACK_PATH) as z:
        return json.loads(z.read(LANG_ENTRY).decode("utf-8"))


def cmd_check(args):
    base = read_pack()
    source, tag = read_source_keys(args.mc, args.jar)
    missing = [k for k in source if k not in base]
    extra = [k for k in base if k not in source]
    print(f"Axiom 目标版本：{tag}")
    print(f"原文 en_us：{len(source)} 键  |  当前译文：{len(base)} 键")
    print(f"缺失（新增未译）：{len(missing)}  |  多余（已删除的旧键）：{len(extra)}")
    for k in missing[:40]:
        print(f"  + {k} = {source[k]}")
    if len(missing) > 40:
        print(f"  ... 另有 {len(missing) - 40} 条")
    for k in extra[:20]:
        print(f"  - {k}")
    if missing:
        print("\n结论：需要补译后执行 repack。")
        return 1
    print("\n结论：译文已覆盖当前最新版全部键。")
    return 0


def build_pack(translations: dict, tag: str) -> tuple[int, str]:
    short = tag.split(" (")[0]
    meta = {
        "pack": {
            "pack_format": 8,
            "description": f"§bAxiom 简体中文§r\n§7界面汉化 · {len(translations)} 条 · 随 Axiom {short} 更新",
            "supported_formats": {"min_format": 8, "max_format": 999},
        }
    }
    os.makedirs(PACK_DIR, exist_ok=True)
    with zipfile.ZipFile(PACK_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.mcmeta", json.dumps(meta, ensure_ascii=False, indent=2))
        z.writestr(LANG_ENTRY, json.dumps(translations, ensure_ascii=False, indent=1))
    data = open(PACK_PATH, "rb").read()
    return len(data), hashlib.sha256(data).hexdigest()


def sync_manifests(size: int, digest: str, count: int, tag: str):
    entries = json.load(open(LIST_PATH, encoding="utf-8"))
    keep = [e for e in entries if not e.get("file", "").startswith("Axiom-简中汉化")]
    keep.append(
        {
            "file": PACK_NAME,
            "sha256": digest,
            "size": size,
            "source": "local",
            "note": f"自制：Axiom 界面汉化，{count} 键 · 目标 {tag}（中文缺键时自动回退英文）",
        }
    )
    keep.sort(key=lambda e: e.get("file", ""))
    with open(LIST_PATH, "w", encoding="utf-8") as fh:
        json.dump(keep, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    raw = open(OPTIONS_PATH, encoding="utf-8").read()
    if PACK_NAME not in raw:
        old = [line for line in raw.splitlines() if line.startswith("resourcePacks:")]
        if not old:
            raise SystemExit("options.txt 缺少 resourcePacks 行")
        arr = json.loads(old[0].split("resourcePacks:", 1)[1].strip())
        arr = [x for x in arr if not x.startswith("file/Axiom-简中汉化")]
        arr.insert(arr.index("serilum_mod_translations") if "serilum_mod_translations" in arr else len(arr),
                   f"file/{PACK_NAME}")
        raw = raw.replace(old[0], "resourcePacks:" + json.dumps(arr, ensure_ascii=False, separators=(",", ":")))
        with open(OPTIONS_PATH, "w", encoding="utf-8", newline="") as fh:
            fh.write(raw)
    print(f"清单与 options.txt 已同步：{PACK_NAME}")


def cmd_repack(args):
    base = read_pack()
    source, tag = read_source_keys(args.mc, args.jar)
    missing = [k for k in source if k not in base]
    if missing and not args.allow_missing:
        print(f"有 {len(missing)} 条新增键未翻译，先补译或加 --allow-missing 强制打包：")
        for k in missing[:20]:
            print(f"  + {k} = {source[k]}")
        return 1
    size, digest = build_pack(base, tag)
    sync_manifests(size, digest, len(base), tag)
    print(f"已重新打包：{size:,} B  sha256 {digest[:16]}…  译文 {len(base)} 条  目标 {tag}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Axiom 简中资源包维护")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "repack"):
        p = sub.add_parser(name)
        p.add_argument("--mc", help="限定 MC 版本，如 26.1.2；省略取最新")
        p.add_argument("--jar", help="本地 Axiom jar 路径（离线用）")
        if name == "repack":
            p.add_argument("--allow-missing", action="store_true", help="存在未译键时仍然打包")
    args = parser.parse_args()
    if not args.mc and not args.jar:
        meta_path = os.path.join(ROOT, "pack", "pack.json")
        if os.path.exists(meta_path):
            args.mc = json.load(open(meta_path, encoding="utf-8")).get("minecraft")
    sys.exit(cmd_check(args) if args.cmd == "check" else cmd_repack(args))


if __name__ == "__main__":
    main()
