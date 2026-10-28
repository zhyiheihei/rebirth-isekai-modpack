#!/usr/bin/env python3
"""把 local-assets/ 打成可分发的 tar.zst，并输出 sha256/size（用于发布 release 资产）。"""
import json
import os
import subprocess
import sys

import common

NAME = "local-assets"


def main():
    version = common.load("pack.json")["version"]
    archive = os.path.join(common.DIST, f"{NAME}-{version}.tar.zst")
    common.ensure_dir(common.DIST)
    if os.path.exists(archive):
        os.remove(archive)
    cmd = ["zstd", "-19", "-T0", "-o", archive, "--format=zstd"]
    if shutil_which("zstd") is None:
        print("需要 zstd 命令", file=sys.stderr)
        return 1
    subprocess.run(["tar", "--zstd", "-cf", archive, "-C", common.ROOT, "local-assets"], check=True)
    info = {
        "version": version,
        "file": os.path.basename(archive),
        "size": os.path.getsize(archive),
        "sha256": common.sha("sha256", archive),
        "url": "",
    }
    print(json.dumps(info, ensure_ascii=False, indent=1))
    print("把它上传成 release 资产后，把下载地址填进 pack/local-assets.json 的 url 字段")
    return 0


def shutil_which(name):
    from shutil import which

    return which(name)


if __name__ == "__main__":
    sys.exit(main())
