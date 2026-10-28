#!/usr/bin/env python3
"""生成 release 说明（写入 GITHUB_OUTPUT 或 stdout）。"""
import sys

import common

LOADER_NAMES = {"fabric": "Fabric", "neoforge": "NeoForge", "forge": "Forge"}


def main():
    pack = common.load("pack.json")
    mods = common.load("mods.json")
    enabled = [m for m in mods if m["enabled"]]
    disabled = [m for m in mods if not m["enabled"]]
    lines = [
        f"# {pack['name']} v{pack['version']}",
        "",
        ("**测试版**：功能与配置已可用，仍在迭代。" if pack["version"].startswith("0.") else ""),
        "",
        f"- Minecraft **{pack['minecraft']}** + {LOADER_NAMES.get(pack['loader']['type'], pack['loader']['type'])} **{pack['loader']['version']}**",
        f"- 模组 **{len(enabled)}** 个，材质包 **{len(common.load('resourcepacks.json'))}** 个（默认启用），光影包 **{len(common.load('shaderpacks.json'))}** 个",
        f"- 内置 Eclipse Temurin JDK {pack['java']['release']}，启动无需任何下载",
        "",
        "## 下载哪个",
        "| 平台 | 文件 | 说明 |",
        "| --- | --- | --- |",
        "| Windows | `Rebirth-Isekai-<版本>-Windows-x64.7z` | 解压后双击 `启动游戏.bat` |",
        "| macOS | `Rebirth-Isekai-<版本>-macOS.7z` | 解压后双击 `启动游戏.command`（arm64/Intel 均内置 Java） |",
        "| Linux | `Rebirth-Isekai-<版本>-Linux-x64.7z` | 解压后执行 `./启动游戏.sh`（NixOS 请改用 nixpkgs 版启动器） |",
        "| PCL2 / HMCL | `Rebirth-Isekai-<版本>-MMC.7z` | 启动器里「导入整合包」选这个 |",
        "",
        "## 首次进入",
        "1. 解压到硬盘（路径别带特殊符号）",
        "2. 双击启动脚本（会直接启动游戏并进服）",
        "3. 启动器已预配离线账户与服务器，等游戏起来自动进服；玩家名首次启动随机生成",
        "4. 要正版联机再「账户」→ 添加账户 登录 Microsoft",
        "",
        "光影：进游戏后在「选项 → 视频设置 → 光影包」里选，默认 Complementary Unbound（r5.7.1）。",
        "",
    ]
    try:
        dropped = common.load("dropped.json")
    except Exception:
        dropped = []
    if dropped:
        lines += ["## 本版本相对上一版剔除", "| 文件 | 原因 |", "| --- | --- |"]
        lines += [f"| {d['file']} | {d['reason']} |" for d in dropped]
        lines.append("")

    if disabled:
        lines += ["## 已知不适配、已禁用", "| 模组 | 原因 |", "| --- | --- |"]
        lines += [f"| {m['file']} | {m.get('disabled_reason', '')} |" for m in disabled]
        lines.append("")
    out = "\n".join(lines)
    if "--github" in sys.argv:
        import os

        path = os.environ.get("GITHUB_OUTPUT")
        if path:
            with open(path, "a", encoding="utf-8") as f:
                f.write("notes<<EOF\n" + out + "\nEOF\n")
            return 0
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
