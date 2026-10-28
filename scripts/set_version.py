#!/usr/bin/env python3
"""把版本号写进 pack/pack.json（版本以提交信息为权威，CI 与本地都用这个脚本落地）。"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "pack", "pack.json")
VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?")


def main():
    if len(sys.argv) < 2:
        print("用法: set_version.py <x.y.z>", file=sys.stderr)
        return 2
    version = VERSION_RE.search(sys.argv[1]).group(0)
    data = json.load(open(PATH, encoding="utf-8"))
    data["version"] = version
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
