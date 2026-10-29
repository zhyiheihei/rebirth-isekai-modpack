#!/usr/bin/env python3
"""生成 release 说明（写入 GITHUB_OUTPUT 或 stdout）。"""
import sys

import common

LOADER_NAMES = {"fabric": "Fabric", "neoforge": "NeoForge", "forge": "Forge"}


def enabled_resourcepack_count():
    """数 options.txt 里默认启用的材质包数量。

    清单里的包不一定默认启用（玩家可在游戏里取消勾选），直接拿
    resourcepacks.json 的条目数写文案会和实际出货状态对不上。
    """
    import json
    import os

    path = os.path.join(common.PACK, "options.txt")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("resourcePacks:"):
                try:
                    arr = json.loads(line.split(":", 1)[1])
                except ValueError:
                    return None
                # 只数随包分发的 file/ 条目，vanilla、moonlight:merged_pack 这类是模组虚拟包
                return sum(1 for x in arr if x.startswith("file/"))
    return None


def selected_shader():
    """从 config/iris.properties 读默认光影包名，避免文案里写死版本号后长期漂移。"""
    import os

    path = os.path.join(common.PACK, "config", "iris.properties")
    if not os.path.exists(path):
        return "Complementary Unbound"
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("shaderPack="):
                name = line.split("=", 1)[1].strip()
                return name[:-4] if name.lower().endswith(".zip") else name
    return "Complementary Unbound"


def main():
    pack = common.load("pack.json")
    mods = common.load("mods.json")
    enabled = [m for m in mods if m["enabled"]]
    disabled = [m for m in mods if not m["enabled"]]
    rp_total = len(common.load("resourcepacks.json"))
    rp_on = enabled_resourcepack_count()
    rp_text = (f"材质包 **{rp_on}** 个（默认启用，随包 {rp_total} 个）" if rp_on is not None
               else f"材质包 **{rp_total}** 个")
    default_shader = selected_shader()
    lines = [
        f"# {pack['name']} v{pack['version']}",
        "",
        ("**测试版**：功能与配置已可用，仍在迭代。" if pack["version"].startswith("0.") else ""),
        "",
        f"- Minecraft **{pack['minecraft']}** + {LOADER_NAMES.get(pack['loader']['type'], pack['loader']['type'])} **{pack['loader']['version']}**",
        f"- 模组 **{len(enabled)}** 个，{rp_text}，光影包 **{len(common.load('shaderpacks.json'))}** 个",
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
        f"光影：进游戏后在「选项 → 视频设置 → 光影包」里选，默认 {default_shader}。",
        "",
    ]
    try:
        dropped = common.load("dropped.json")
    except Exception:
        dropped = []
    # dropped.json 是累积台账（两百多条历史剔除）。带 since 的按版本过滤，
    # 只把本次新增的剔除列出来。注意：上一版发版失败时（未出产物），
    # 其 since 记录会顺延到本版首次成功发布，一并列出，避免静默丢失。
    current = pack["version"]
    if any(d.get("since") for d in dropped):
        # 只认显式标了本版 since 的条目；没有 since 的都是历史旧账，不该重复出现。
        dropped = [d for d in dropped if d.get("since") == current]
    if dropped:
        lines += ["## 本版本剔除的模组", "| 文件 | 原因 |", "| --- | --- |"]
        lines += [f"| {d['file']} | {d['reason']} |" for d in dropped]
        lines.append("")

    if disabled:
        lines += ["## 已知不适配、已禁用", "| 模组 | 原因 |", "| --- | --- |"]
        lines += [f"| {m['file']} | {m.get('disabled_reason', '')} |" for m in disabled]
        lines.append("")
    if not dropped and not disabled:
        lines.append("本版本模组集合无增删。")
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
