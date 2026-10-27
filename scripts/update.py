#!/usr/bin/env python3
"""检查/升级 mods.json 里的模组版本。

  python3 scripts/update.py          # 只报告可升级项
  python3 scripts/update.py --write  # 写回 mods.json
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

import common


def versions_for(project, mc, loader):
    query = urllib.parse.urlencode(
        {"game_versions": json.dumps([mc]), "loaders": json.dumps([loader])}
    )
    url = f"https://api.modrinth.com/v2/project/{project}/version?{query}"
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.load(resp)
        except Exception:
            continue
    return []


def newest(versions):
    releases = [v for v in versions if v["version_type"] == "release"]
    pool = releases or versions
    return max(pool, key=lambda v: v["date_published"]) if pool else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    pack = common.load("pack.json")
    mods = common.load("mods.json")
    updates, incompatible = [], []

    for mod in mods:
        versions = versions_for(mod["project"], pack["minecraft"], pack["loader"]["type"])
        if not versions:
            incompatible.append((mod["file"], "该版本无可用构建"))
            continue
        best = newest(versions)
        if not best:
            continue
        if best["id"] == mod["version_id"]:
            continue
        primary = [f for f in best["files"] if f["primary"]] or best["files"]
        file = primary[0]
        updates.append(
            {
                "file": mod["file"],
                "new_file": file["filename"],
                "old": mod["version"],
                "new": best["version_number"],
                "version_id": best["id"],
                "url": file["url"],
                "sha512": file["hashes"]["sha512"],
            }
        )
        if args.write:
            mod.update(
                {
                    "file": file["filename"],
                    "version": best["version_number"],
                    "version_id": best["id"],
                    "url": file["url"],
                    "sha512": file["hashes"]["sha512"],
                }
            )

    print(f"可升级 {len(updates)} 个，无可用构建 {len(incompatible)} 个")
    for u in updates:
        print(f"  {u['old']:>16} → {u['new']:<16} {u['new_file']}")
    for name, why in incompatible:
        print(f"  !! {name}: {why}")
    if args.write and updates:
        common.save("mods.json", mods)
        print("已写回 pack/mods.json；接着跑 scripts/fetch.py 再 build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
