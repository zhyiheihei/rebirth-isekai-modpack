# 重生：异世界冒险 —— Minecraft 26.1.2 整合包

> **版本：Minecraft 26.1.2 / Fabric 0.20.1。** 唯一事实来源是 `pack/pack.json` 的 `minecraft` 字段。
> 模组文件名里出现 `26.2`/`26.3`、材质包里出现 `EnderEyes_26.3`、`dropped.json` 里写「止于 26.3」，
> 都是上游的版本命名或排除原因，不代表本项目目标版本。详见 `AGENTS.md` 的「版本」一节。

Minecraft 26.1.2 + **Fabric 0.20.1** 的整合包。客户端版本与服务器保持一致（服务端为 26.1.2 混合端），267 个模组、45 个材质包、9 个光影包，打包成开箱即玩的三平台便携包（自带 Java 25 与全部游戏资源），Windows 另有 PCL2 可导入的 MMC 实例包。三个便携包都是双击启动脚本即进游戏：自带 Java、预置服务器、首次运行随机分配一个离线玩家名；「启动正版」脚本可登录微软账号联机，登录过一次后「启动游戏」会自动识别并用正版启动，删掉账号即回离线模式。

Android 目前提供 **FCL 可导入的 `.mrpack` 实验包**，不是自制 APK；使用 FCL 官方 APK 启动。当前保留完整客户端模组清单，首次测试不带光影；尚未通过 Android 实机验证，不能视为已支持设备。

名字取自「重生」+「异世界冒险」：进服那一刻起，你在一个重开的世界里从头活一遍——不是快节奏的战斗包，而是偏探索与建造的长期生存。地图换了、生物群系重织、村庄与要塞重做，附魔与饰品把成长线拉长；难度靠结构与地牢推进，不靠数值堆砌。适合几个人长期泡在一个存档里，也适合单人慢慢逛。

模组、材质、光影逐条核对到 26.1.2 有可用构建后固定版本，不追最新、只追能跑。加载器是按可移植数量选出来的：Fabric **244** / NeoForge **209**（252 个可移植模组里 Fabric 覆盖 96.8%），且仅 Fabric 可用的 43 个里多为内容模组（BetterEnd、BetterNether、BCLib、The Bumblezone、Brewery、Macaw's Holidays、Sit、Ube's Delight 等）。


## 目录结构

```
pack/            整合包定义（进 git 的唯一事实来源）
  pack.json        整合包元数据：MC / 加载器 / Java / 内存
  mods.json        模组清单：Modrinth 项目 + 固定版本 + sha512（含源整合包的 modid 便于对齐）
  dropped.json     未纳入的 213 个源模组及原因（无 26.1.2 Fabric 构建 / 仅 CurseForge）
  resourcepacks.json / shaderpacks.json   材质与光影清单（本地文件，记录 sha256）
  launcher.json    启动器版本与校验和
  runtimes.json    Temurin JRE 25 各平台下载地址与校验和
  config/          模组配置（290 个文件）
  options.txt      游戏设置（含已启用材质包顺序）
  mmc-pack.json    MultiMC/Prism 实例组件声明
  android.json     FCL/Android 实验包策略（单独排除清单，不改桌面配置）
  使用说明.txt     随包分发的说明
scripts/
  common.py        路径/清单/下载校验（支持 MODPACK_PROXY）
  fetch.py         拉取 mods / 启动器 / Java / 翻译 / 游戏资源 / 材质
  resources.py     按 Mojang+NeoForge 元数据下载客户端 jar、库、素材
  build.py         组装三平台便携包 + PCL2 用的 MMC 实例包
  build_android.py 生成 FCL 可导入的 Modrinth `.mrpack`（不生成 APK）
  verify_android.py 自检 Android 包清单、模组哈希与 overrides
  verify_bundle.py 产物自检（确认启动免下载、材质默认启用）
  update.py        检查并升级模组版本
  package_assets.py 打包材质原件用于 release 资产
  release_notes.py 生成 release 说明
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

### Android / FCL 实验包

```bash
python3 scripts/fetch.py
MODPACK_DIST=/var/tmp/rebirth-android-dist python3 scripts/build_android.py
MODPACK_DIST=/var/tmp/rebirth-android-dist python3 scripts/verify_android.py
```

将生成的 `Rebirth-Isekai-<版本>-Android-FCL.mrpack` 传到手机，在 FCL 的本地整合包导入页导入。[FCL 官方仓库](https://github.com/FCL-Team/FoldCraftLauncher)列明支持 Fabric 与 Java 25；[Modrinth 导入实现](https://github.com/FCL-Team/FoldCraftLauncher/blob/main/FCL/src/main/java/com/tungsten/fclcore/mod/modrinth/ModrinthInstallTask.java)会读取 Modrinth manifest 和 `overrides/`，本包已按该格式生成。游戏本体与资源不放进包，玩家需在 FCL 中用正版微软账号登录并下载。

本包沿用 `pack/mods.json` 的客户端清单（按设备日志排除了 Distant Horizons），Modrinth 模组由 FCL 下载，4 个本地模组和材质配置放入 overrides；光影包暂不打包，并在 Android overrides 中关闭 Iris 光影。**这只是可导入的测试包，当前没有 Android 实机验收；**遇到启动失败或渲染问题时请保留 FCL 日志，再根据具体日志更新 `pack/android.json`，不要凭猜测删模组。通过实机验收前不并入滚动 Release。要做自有品牌 APK，需要后续单独维护 FCL fork；本项目不复制或修改 FCL 启动器源码。

## 更新维护

```bash
python3 scripts/update.py            # 报告有哪些模组在 26.3 上有新版本
python3 scripts/update.py --write    # 写回 pack/mods.json
python3 scripts/fetch.py && python3 scripts/build.py --zip
```

- 升级 Minecraft / Fabric：改 `pack/pack.json` 与 `pack/mmc-pack.json`，再跑一次 `update.py --write` 让所有模组对齐新版本。
- 换材质/光影：把新压缩包放进 `local-assets/<类别>/`，改对应 JSON 的 `file`/`sha256`/`size`；批量对齐上游用 `python3 scripts/update_assets.py`（见下）。
  45 个材质包里，能查到上游发布者的最新版本已替换（`options.txt` 的 `resourcePacks` 引用同步更新）。Minecraft 26.1 的 resource pack format 65 使用顶层 `min_format` / `max_format`，多版本资源包的最低格式不得小于 15；若兼容范围从旧格式开始，还需保留相匹配的旧版兼容字段，构建时会规范化。`xali's Enhanced Vanilla` 上游 zip 本身是重叠条目的畸形包（`unzip` 只报 warning，Python zipfile 直接抛错），本地是用 `unzip` 兜底解出后重建的等价副本。
- 禁用某个模组：把 `mods.json` 里的 `enabled` 改成 `false` 并写上 `disabled_reason`。

## 材质/光影批量对齐上游

```bash
python3 scripts/update_assets.py            # 只报告：每个包的上游候选与判定
python3 scripts/update_assets.py --apply    # 落地：替换文件、补 mcmeta、更新清单与 options.txt
```

判定不靠名字相似度：每个候选都会下载下来算**zip 内路径集合重合度**，同一项目的相邻版本重合度通常 >0.9，搜索误配到的别的包只有 0.0~0.4。重合度不够但作者/描述能对上的（FreshAnimations 这类结构重排过的）走脚本里的 `FORCE` 白名单。Modrinth 上找不到的项目保持原样。

## 已知坑（都已在本包里处理，改包时别退化）

1. **MC 26.x 需要 GLFW 3.5。** 客户端要调 `glfwSetPreeditCallback`，官方 `lwjgl-glfw-natives-linux-3.4.1.jar` 里编的其实是 GLFW 3.5.0（有 preedit 符号）。NixOS 的 prismlauncher 包装器把 `glfw-minecraft-3.4` 塞进 `LD_LIBRARY_PATH` 并默认 `UseNativeGLFW=true`，于是 `dlopen` 拿到没有该符号的 3.4 → `InputConstants.setupKeyboardCallbacks` NPE、启动即崩。本包的 `PRISM_CFG` 因此设 `UseNativeGLFW=false`；如果目标机器仍崩，用 `-Dorg.lwjgl.glfw.libname=/path/to/libglfw.so` 显式钉住正确的库。
2. **`options.txt` 里的键位不能带 Forge 修饰符。** 原 1.20.1 包留下的 `key_xxx:key.keyboard.o:CONTROL_OR_COMMAND` 会让 26.x 的 `InputConstants.getKey` 抛 `NumberFormatException`，整个 options 加载失败（连带材质包启用顺序丢失）。写回前必须剥掉 `:MODIFIER` 后缀。
3. **`config/iris.properties` 的 `shaderPack` 必须与实际光影文件名一致。** 光影回退版本后忘了改这里，Iris 会报 `Pack ... is not valid!` 并静默关闭光影。
4. **`mmc-pack.json` 要带与本地 meta 文件匹配的 `cachedSha256`。** 否则 Prism 每次启动都去远程拉组件元数据，断网/代理 fake-ip 环境下直接报「组件元数据更新失败」。

## 发布

```bash
git commit -m "release: 0.2.4 简述改动"
git push origin master
```

滚动更新，不打 tag：提交信息里带 `release: <版本>` 就自动构建并发到同一个滚动 Release（tag 固定 `rolling`，每次先清旧资产再传新包），下载入口不变。工作流完全自包含，不依赖本地任何文件。
- 工作流会校验 tag 与 `pack/pack.json` 的 `version` 一致，跑完 `scripts/verify_bundle.py` 才会上传
- 产物：`*-Windows-x64.7z`、`*-macOS.7z`、`*-Linux-x64.7z`、`*-MMC.7z`（PCL2/HMCL 导入用）
- 每个便携包内置启动器 + Temurin JDK 25 + 客户端 jar + 135 个库 + 素材对象 + 组件 meta + 中文翻译，**启动不需要联网下载任何东西**

### 材质原件托管

`local-assets/` 的约 262MB 原始材质不走 git，作为 release `assets-0.2.1` 的资产托管，`pack/local-assets.json` 记录直链与 sha256：

```
https://github.com/zhyiheihei/rebirth-isekai-modpack/releases/download/assets-0.2.1/local-assets-0.2.1.tar.zst
sha256 eea00b797562eec6a0c12bcab0ce2c5428f30045513b316367e253219200ceca
```

改材质时的流程：更新 `local-assets/` → `python3 scripts/package_assets.py` 生成新 tar.zst → `gh release create assets-<版本> dist/local-assets-<版本>.tar.zst` → 把新 url/sha256 写进 `pack/local-assets.json`。

`fetch.py` 解压后会**按清单剪枝**：清单里没有的文件一律删掉，所以改名/回退过的旧文件不会残留在产物里，也不会出现在游戏内的材质包列表。

## local-assets 来源

`local-assets/resourcepacks/` 与 `local-assets/shaderpacks/` 不进 git（体积与再分发限制），需要从原始来源补齐：

- 材质包：随包托管的 45 个（清单见 `pack/resourcepacks.json`，逐条记录 sha256）
- 光影包：Complementary Unbound / Reimagined **r5.9.3**、Bliss **2.1.2**、photon **v1.4**、Helian-MMCO 0.6.12、Derivative d24.4.14、VanillaPlus 3.3
- 两个 `…+ EuphoriaPatches_1.8.1` 合并包仍是 5.7.1：上游已改用 **EuphoriaPatcher** 模组在运行期打补丁，不再分发合并 zip，没有可更新的对象。想在新版 Complementary 上要 Euphoria 效果，得加 EuphoriaPatcher 模组（会动模组清单，默认不加）。
- 材质包里能查到上游的已对齐最新：FreshAnimations、Round-Trees、JustExpressions、EnderEyes、Assorted Allays、Better 3D Beds、Os' Colorful Grasses、3D Bamboo Shoots、xali's Enhanced Vanilla、玻璃底船、村民之声、繁花谧境、暴击音效、Excalibur 农夫乐事支持等；中文社区包（七彩花透明 GUI、自定义音乐、汉化资源包等）在 Modrinth 上没有对应项目，保持原样。

`fetch.py` 会校验 sha256，缺文件会直接报出缺哪个；解压后按清单剪枝，多出来的旧文件会被删掉。

## 未纳入的模组

评估过的 459 个模组中，211 个在 26.1.2 上没有 Fabric 构建，连同 4 个主动移除的（tectonic、a_good_place、amendments、gardeners-dream）一并记在 `pack/dropped.json`，共 215 条：

| 分类 | 数量 | 说明 |
| --- | --- | --- |
| 止步旧版本 | 148 | 最后一次更新停在 1.20.1～1.21.11，如 Farmer's Delight、Create、BiomesOPlenty、FTB 全家桶 |
| 只有 Forge/NeoForge 构建 | 8 | paragliders、kubejs、modernfix、seasonhud、inventoryhud、fastfurnace、ultimine-rewind、lavasweeper |
| CurseForge 独占 | 55 | Modrinth 上没有对应项目（MrCrayfish's Framework、FTB Quests/Chunks/Teams、Botany Pots 等） |

补齐依赖（19 个）不来自源整合包，是按所选模组的 `depends` 自动解析后加的。

## 版权

模组、材质、光影版权归各自作者所有。本仓库只包含整合配置；不含游戏本体、不含存档。
