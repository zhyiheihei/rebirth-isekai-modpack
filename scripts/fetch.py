#!/usr/bin/env python3
"""拉取整合包需要的全部外部文件到 cache/，并检查 local-assets/ 是否齐全。"""
import sys

import common


def main():
    print("== mods ==")
    ok, total = common.fetch_mods()
    print(f"   {ok}/{total}")

    print("== 启动器 ==")
    print("   ok" if common.fetch_launcher() else "   失败")

    print("== Java 运行时 ==")
    print("   ok" if common.fetch_runtimes() else "   失败")

    print("== 启动器翻译 ==")
    print("   ok" if common.fetch_translations() else "   失败")

    print("== 游戏资源（客户端 jar / 库 / 素材）==")
    import resources

    resources.fetch()

    print("== 本地资产（材质/光影，不进 git）==")
    common.prune_local_assets()          # 先按清单剪枝，避免上一次构建的旧文件被当成缺件
    missing = common.check_local_assets()
    if missing:
        print("   尝试从发布资产拉取…")
        if common.fetch_local_assets():
            missing = common.check_local_assets()
    if missing:
        print("   缺少以下文件（既不随包也不在发布资产里），请补齐 local-assets/：")
        for m in missing:
            print("    -", m)
        return 1
    print("   ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
