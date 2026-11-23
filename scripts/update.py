#!/usr/bin/env python3
"""检查/升级 mods.json 里的模组版本。

只接受与 pack.json 当前版本同时匹配的构建：game_versions 必须包含 pack.minecraft，
loaders 必须包含 pack.loader.type。不匹配的版本直接跳过，不会把整合包拽到别的 MC 版本上。

  python3 scripts/update.py                  # 只报告可升级项
  python3 scripts/update.py --write          # 写回 mods.json
  python3 scripts/update.py --only <jar...> --write   # 只更新指定 jar

日常不手跑：.github/workflows/update.yml 在 Actions 里跑 --write 并触发新版本构建。
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import common

UA = {"User-Agent": "rebirth-isekai-modpack/update (+https://github.com/__SECRET_NEXTTODO_ADMIN_PASSWORD__heihei/rebirth-isekai-modpack)"}
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    delay = 3
    last = None
    for _ in range(6):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code not in RETRY_STATUS:
                raise RuntimeError(f"Modrinth 请求失败: {url}: {last}") from exc
            wait = int(exc.headers.get("Retry-After") or delay)
            time.sleep(min(wait, 60))
        except Exception as exc:
            last = repr(exc)
            time.sleep(delay)
        delay = min(delay * 2, 30)
    raise RuntimeError(f"Modrinth 请求失败（重试已尽）: {url}: {last}")


def versions_for(project, mc, loader):
    query = urllib.parse.urlencode(
        {"game_versions": json.dumps([mc]), "loaders": json.dumps([loader])}
    )
    return get_json(f"https://api.modrinth.com/v2/project/{project}/version?{query}")


def matches(version, mc, loader):
    return mc in version.get("game_versions", []) and loader in version.get("loaders", [])


def pick_file(version):
    files = [
        f
        for f in version.get("files", [])
        if not any(x in f["filename"] for x in ("-sources", "-dev", "-javadoc"))
    ]
    if not files:
        return None
    return next((f for f in files if f.get("primary")), files[0])


def newest(versions, mc, loader):
    pool = [v for v in versions if matches(v, mc, loader)]
    if not pool:
        return None
    releases = [v for v in pool if v.get("version_type") == "release"]
    pool = releases or pool
    return max(pool, key=lambda v: v.get("date_published") or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only", nargs="+", metavar="JAR", help="只检查指定的模组文件名")
    args = ap.parse_args()

    pack = common.load("pack.json")
    mc, loader = pack["minecraft"], pack["loader"]["type"]
    all_mods = common.load("mods.json")
    mods = [
        m
        for m in all_mods
        if not m.get("local") and m.get("project") not in (None, "", "local")
    ]
    # hold=True 的条目钉死在当前版本：上游有新构建也不动。用于上游走太快、
    # 新版本与包里其它模组互相 breaks 的情况（见 AGENTS.md「Sodium 0.9.3 事件」）。
    held = [m for m in mods if m.get("hold")]
    mods = [m for m in mods if not m.get("hold")]
    if args.only:
        requested = set(args.only)
        known = {m["file"] for m in all_mods}
        unknown = requested - known
        if unknown:
            raise SystemExit(f"清单中找不到这些模组: {sorted(unknown)}")
        mods = [m for m in mods if m["file"] in requested]

    print(f"目标版本：minecraft={mc} loader={loader}，待检查 {len(mods)} 个模组")
    if held:
        print(f"已锁定 {len(held)} 个（hold=true，不参与自动更新）：" + "、".join(
            f"{m['file']}({m.get('version')})" for m in held
        ))
    updates, incompatible = [], []

    for mod in mods:
        versions = versions_for(mod["project"], mc, loader)
        best = newest(versions, mc, loader)
        if not best:
            incompatible.append((mod["file"], f"无匹配 {mc}/{loader} 的构建"))
            continue
        if best["id"] == mod.get("version_id"):
            continue
        file = pick_file(best)
        if not file:
            incompatible.append((mod["file"], "版本下没有可用 jar"))
            continue
        updates.append(
            {
                "file": mod["file"],
                "new_file": file["filename"],
                "old": mod.get("version", "?"),
                "new": best.get("version_number", best["id"]),
                "version_id": best["id"],
                "url": file["url"],
                "sha512": file.get("hashes", {}).get("sha512", ""),
            }
        )
        if args.write:
            mod.update(
                {
                    "file": file["filename"],
                    "version": best.get("version_number", best["id"]),
                    "version_id": best["id"],
                    "url": file["url"],
                    "sha512": file.get("hashes", {}).get("sha512", ""),
                }
            )

    print(f"可升级 {len(updates)} 个，无匹配构建 {len(incompatible)} 个")
    for u in updates:
        print(f"  {u['old']:>16} → {u['new']:<16} {u['new_file']}")
    for name, why in incompatible:
        print(f"  !! {name}: {why}")

    if args.write and updates:
        common.save("mods.json", all_mods)
        print("已写回 pack/mods.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
