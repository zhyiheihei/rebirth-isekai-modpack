#!/usr/bin/env python3
"""生成 release 说明（写入 GITHUB_OUTPUT 或 stdout）。"""
import sys

import common


def main():
    pack = common.load("pack.json")
    mods = common.load("mods.json")
    enabled = [m for m in mods if m["enabled"]]
    disabled = [m for m in mods if not m["enabled"]]
    lines = [
        f"# {pack['name']} v{pack['version']}",
        "",
        f"- Minecraft **{pack['minecraft']}** + NeoForge **{pack['loader']['version']}**",
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
        "2. 双击启动脚本，等启动器打开",
        "3. 右上角「账户」→ 添加 Microsoft 正版账号，或添加离线账户直接玩单人",
        "4. 选中实例 → 启动",
        "",
        "光影：进游戏后在「选项 → 视频设置 → 光影包」里选，默认推荐 Complementary Reimagined。",
        "",
    ]
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
