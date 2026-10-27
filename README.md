# 重生：异世界冒险 —— Minecraft 26.3 整合包

Minecraft 26.3 + NeoForge 26.3.0.99 的整合包，166 个模组、45 个材质包、7 个光影包，打包成开箱即玩的三平台便携包（自带 Java 25 与全部游戏资源），Windows 另有 PCL2 可导入的 MMC 实例包。

## 目录结构

```
pack/            整合包定义（进 git 的唯一事实来源）
  pack.json        整合包元数据：MC / NeoForge / Java / 内存
  mods.json        模组清单：Modrinth 项目 + 固定版本 + sha512（含被禁用的 4 个及原因）
  resourcepacks.json / shaderpacks.json   材质与光影清单（本地文件，记录 sha256）
  launcher.json    启动器版本与校验和
  runtimes.json    Temurin JRE 25 各平台下载地址与校验和
  config/          模组配置（290 个文件）
  options.txt      游戏设置（含已启用材质包顺序）
  mmc-pack.json    MultiMC/Prism 实例组件声明
  使用说明.txt     随包分发的说明
scripts/
  common.py        路径/清单/下载校验
  fetch.py         拉取全部外部文件到 cache/
  build.py         组装三平台便携包 + PCL2 用的 MMC 实例包
  update.py        检查并升级模组版本
local-assets/    不进 git：材质与光影原始压缩包（约 266MB）
cache/           不进 git：下载缓存
dist/            不进 git：产物
```

## 构建

```bash
# 1) 拉取 mods / 启动器 / Java 到 cache/（国内可走代理）
MODPACK_PROXY=192.168.0.62:1080 python3 scripts/fetch.py

# 2) 组装全部平台并打包
python3 scripts/build.py --zip

# 只做某个平台
python3 scripts/build.py --target linux
python3 scripts/build.py --target windows,macos
python3 scripts/build.py --target mmc --zip     # PCL2 / HMCL 导入用
```

`build.py` 需要一台已经有 PrismLauncher 数据目录的机器来提供 `assets/ libraries/ meta/`（默认 `~/.local/share/PrismLauncher`，可用 `--prism-data` 指定）。Windows/macOS 专属原生库会在构建时按 Mojang 元数据自动补齐。

## 更新维护

```bash
python3 scripts/update.py            # 报告有哪些模组在 26.3 上有新版本
python3 scripts/update.py --write    # 写回 pack/mods.json
python3 scripts/fetch.py && python3 scripts/build.py --zip
```

- 升级 Minecraft / NeoForge：改 `pack/pack.json` 与 `pack/mmc-pack.json`，再跑一次 `update.py --write` 让所有模组对齐新版本。
- 换材质/光影：把新压缩包放进 `local-assets/<类别>/`，改对应 JSON 的 `file`/`sha256`/`size`。
- 禁用某个模组：把 `mods.json` 里的 `enabled` 改成 `false` 并写上 `disabled_reason`。

## local-assets 来源

`local-assets/resourcepacks/` 与 `local-assets/shaderpacks/` 不进 git（体积与再分发限制），需要从原始来源补齐：

- 材质包：乌托邦探险之旅 3.5.2 的 `resourcepacks/` 目录
- 光影包：Complementary / Bliss / Photon 可从 Modrinth 下载，Helian-MMCO、Derivative 来自各自作者的发布页

`fetch.py` 会校验 sha256，缺文件会直接报出缺哪个。

## 已知不适配 26.3 的模组

| 模组 | 原因 |
| --- | --- |
| FancyMenu 3.9.14 | mixin 在早期窗口 resize 时 `Minecraft.gui` 为 null，NPE 崩溃 |
| Carry On 2.12.0 | `NoSuchFieldError: ModConfig$Type.COMMON`，与 NeoForge 26.3.0.99 API 不匹配 |
| Reese's Sodium Options 2.2.5 | 硬绑 `sodium` 版本区间 `[0.9.2+mc26.3]` |
| Sodium Extra 0.9.5 | 同上；而 Sodium 0.9.2 在 26.3 上 mixin 目标失效，必须用 0.9.3-beta.1 |

## 版权

模组、材质、光影版权归各自作者所有。本仓库只包含整合配置；不含游戏本体、不含存档。
