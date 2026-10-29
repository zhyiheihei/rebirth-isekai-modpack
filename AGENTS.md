# AGENTS.md

给接手这个仓库的 agent 看的项目事实。改动前先读这一节，能省掉一轮误判。

## 版本（唯一权威：`pack/pack.json`）

```
minecraft      = 26.1.2      ← 整合包本体就是这个版本，别的写法都是上游元数据
minecraft_line = 26.1
loader         = fabric 0.20.1
java           = Temurin 25
```

判定规则，按顺序看：

1. `pack/pack.json` 的 `minecraft` 是唯一事实来源。文档、JSON 里任何其他版本号都不是整合包的目标版本。
2. `pack/mods.json` 当前有 267 条：263 条有 Modrinth `version_id`，另有 4 条是仓库内的 `local` 模组。版本目标只看 `pack/pack.json`；文件名里出现 `26.2`、`26.3` 只说明那个 jar 同时兼容更高版本，例如 `advancements_reloaded-0.14.0-fabric-26.2.jar`、`bigger_end_cities-26.1-26.3-1.1.3.jar`。
3. `pack/resourcepacks.json` / `shaderpacks.json` 里的 `upstream.game_versions` 是**材质/光影作者发布时声明的版本**，不是本项目的目标。带 `note` 字段的条目是名字或上游版本容易引起误读的，逐条看 note。
4. `pack/dropped.json` 里的 `reason: "止于 26.3（无 26.1.2 构建…"` 表示那个模组**没有** 26.1.2 构建、因此被排除。看到这类记录不要反推本项目用了 26.3。
5. 26.1 使用资源包 format 65：`pack.mcmeta` 的 `pack.min_format` / `pack.max_format` 是顶层字段，`min_format` 不得低于 15；兼容范围起点低于 65 的老包还必须保留 `pack_format` 与 `supported_formats: {min_inclusive, max_inclusive}`，两种范围要一致。format 65 及以上的包必须删除这两个旧字段。构建脚本会规范化上游包；不要把 `min_format/max_format` 塞进 `supported_formats`。

结论：**这个仓库是 26.1，不是 26.2，也不是 26.3。**

## 目录

```
pack/            清单与配置（唯一事实来源）：pack.json / mods.json / dropped.json /
                 resourcepacks.json / shaderpacks.json / local-assets.json / android.json / config / options.txt
pack/mods-local/ Modrinth 上拿不到的自制/付费数据包模组（jar 直接进仓库，mods.json 里 url 留空、写 local）
local-assets/    材质与光影原始 zip（约 262MB，不进 git，托管在 release 资产 assets-<版本>）
scripts/         fetch.py（拉依赖）build.py（组装）verify_bundle.py（自检）
                 update_assets.py（对齐材质/光影上游）resources.py / release_notes.py
                 build_android.py / verify_android.py（生成/检查 FCL 可导入的 Android `.mrpack`）
                 sync_client.py（把本机客户端改动同步回 pack/）
cache/           下载缓存，可删
dist/            构建产物，可删
```

## 常用命令

```bash
python3 scripts/fetch.py                        # 拉全部依赖到 cache/，并按清单校验 local-assets/
python3 scripts/build.py --zip                  # 组装四平台 + 7z
python3 scripts/build.py --fast --target linux  # 只重建实例，跳过资源复制，改配置时用这个
python3 scripts/verify_bundle.py                # 产物自检（离线可启动、材质/光影齐全等）
MODPACK_DIST=/var/tmp/android-dist python3 scripts/build_android.py
MODPACK_DIST=/var/tmp/android-dist python3 scripts/verify_android.py  # FCL Android 实验包（非 APK）
python3 scripts/update_assets.py                # 报告材质/光影有哪些上游新版本
python3 scripts/update_assets.py --apply        # 落地：替换 + 补 mcmeta + 同步清单与 options.txt
python3 scripts/package_assets.py               # 重打材质原件 tar.zst，用于发新 assets-<版本>
python3 scripts/sync_client.py                  # 客户端改动进仓库：预演差异（mods/config/options）
python3 scripts/sync_client.py --apply          # 落盘
python3 scripts/sync_client.py --apply --release 0.2.2   # 落盘 + 改版本 + 提交推送（滚动 Release 自动更新）
```

## 客户端开发流程（唯一通道）

本机实例（`MODPACK_INSTANCE`，缺省 `D:/我的世界/重生之异世界生存/.minecraft/versions/重生之异世界生成1.0v`）
里试出来的改动，必须回灌到本仓库、由 CI 出 Release，**不允许只留在本机**：

1. `python3 scripts/sync_client.py` 看差异，`--apply` 落盘。模组按 sha512 反查 Modrinth 自动补元数据；
   查不到的（付费、自制数据包）先把 jar 放进 `pack/mods-local/` 再跑，脚本会写成 `local` 条目，CI 直接从仓库取。
2. `python3 scripts/fetch.py && python3 scripts/build.py --fast --target linux` 本地抽检（可选）。
3. `python3 scripts/sync_client.py --apply --release <新版本>` → 改 `pack.json` version、提交（信息带
   `release: <新版本>`）、推送 master，Actions 构建完自动更新滚动 Release，玩家从 Release 页下载即可。

客户端实机验收使用当前 NixOS 主机上的本地 PrismLauncher 实例，不要求 ArchLinux VM；用户明确授权后可由 agent 启动 Prism 并检查该实例 `latest.log`。MCSM 测试服地址作为临时连接参数或单独服务器列表项添加，不能覆盖 `pack/pack.json` 里原有服务器地址。

## 发布（滚动更新）

只有一个分支 `master`，**不打 tag**，版本不进 git 历史文件、也不靠 tag：

- 版本号写在**提交信息**里，形如 `release: 0.2.4`（`[release 0.2.4]` 也认）。工作流看到这一句才构建，
  普通提交直接跳过；手动 `Run workflow` 无条件构建。
- 版本以提交信息为准，CI 用 `python3 scripts/set_version.py <版本>` 把它写进 `pack/pack.json` 再打包。
- 发布到**同一个滚动 Release**（tag 固定为 `rolling`，由工作流自动创建，永远不要手工打 tag）：
  每次构建先删掉旧资产再传新的，所以下载入口固定不变，内容永远是最新一次构建。
- 测试期策略：自检 `continue-on-error`，只报告不阻断，带着问题也照发；
  出问题**禁止回退旧版本**，把版本加一位、提交信息写 `release: <新版本>` 再发一次。

```bash
python3 scripts/set_version.py 0.2.4      # 本地同步版本号（CI 会自动做）
git commit -m "release: 0.2.4 简述改动"    # 提交信息带版本即触发工作流
git push origin master
```

## 已知坑（都已处理，改包时别退化）

- MC 26.x 要 GLFW 3.5 的 `glfwSetPreeditCallback`。NixOS 系统 GLFW 3.4 没有这个符号，`UseNativeGLFW=true` 会在 `InputConstants` 初始化时 NPE 崩掉；便携包的 `prismlauncher.cfg` 必须 `UseNativeGLFW=false`。
- `options.txt` 里 `key_*` 的值不能带 `o:CONTROL_OR_COMMAND` 这类 Forge 修饰符后缀，否则 `InputConstants.getKey` 抛 `NumberFormatException`，**整个 options.txt 加载失败**（材质包启用顺序全丢）。
- MC 26.1 资源包 format 65 弃用了 `supported_formats`（新包必须删除）；旧包若仍支持 format <65，则 `pack_format` 和 `supported_formats: {min_inclusive, max_inclusive}` 必须与顶层 `min_format/max_format` 范围一致。只用 `supported_formats: {min_format, max_format}` 会让资源包被标为不兼容。
- `mmc-pack.json` 里带 `cachedSha256` 且与随包 meta 文件一致，启动器才不会去远程拉组件元数据（假 IP/断网环境会直接拦住启动）。MMC 导入包不含 meta，故不写。
- `~/Documents` 是 bindfs（FUSE）挂载，同时只能再打开约 50 个文件。Minecraft 客户端/服务端都不能直接从仓库目录启动，要复制到 `/var/tmp` 之类路径再跑。
- 实例目录名固定 ASCII `RebirthIsekai`（显示名 `name=` 才是中文）：Windows 上 cmd/PowerShell 传中文参数会因代码页丢字符，`JavaPath` 替换曾经就是这样失效的。
- Windows 启动逻辑全在 `launch.ps1`（UTF-8 **带 BOM**，否则 PowerShell 5.1 读中文乱码），`启动游戏.bat` 只用 `-File` 调用；`.bat` 必须是 CRLF，写成 CRCRLF 会解析异常。
- `verify_bundle.py` 的 `check_runnable()` 按产物自身的标志文件判断平台（`prismlauncher.exe` / `*.app` / `PrismLauncher`），不看宿主机；换启动器文件名时记得同步那里。
- `xali's Enhanced Vanilla` 上游 zip 条目重叠（`unzip` 只报 warning，Python `zipfile` 直接抛错），本地是解出后重建的副本，不要用上游原包覆盖。
- Android 当前只生成 FCL 可导入的 Modrinth `.mrpack`，不生成或分发自制 APK；`pack/android.json` 维护单独的实验配置，基础依赖版本仍来自 `pack/pack.json` / `pack/mods.json`。FCL README 声明支持 Fabric 和 Java 25，导入实现读取 `modrinth.index.json` 与 `overrides/`；这只证明格式兼容，不等同于本整合包已在 Android 实机通过。先关闭光影，模组排除必须由实际设备日志证据驱动；实机验收前不要把 Android 包接入滚动 Release。
- 账号机制（别拆）：`accounts.json` 里的占位 MSA 账号 + `prismlauncher.cfg` 里的死代理（SOCKS5 127.0.0.1:9）是离线打开即用的前提——Prism 11 的 `ownsMinecraft()` 排除 Offline 类型账号，没有占位 MSA 会弹 Demo 确认框/登录向导；死代理让占位账号的静默刷新以网络错误收场（STATE_OFFLINE），不弹重新认证框。启动脚本检测到 `accounts.json` 出现非占位 `refresh_token`（玩家已登录微软正版）时，会撤掉死代理、不再传 `--offline`，由 Prism 官方逻辑用正版账号启动；「启动正版」脚本则无条件走这条路。`verify_bundle.py` 对这套机制有回归检查。
- 材质包被就地改过（如剔除包内 JSON 尾部的作者签名行）时，修正版必须放进 `pack/resourcepacks-local/`：
  `local-assets/` 不进 git，CI 靠 actions/cache 或发布资产恢复，缓存里的旧包会盖掉修正版，
  `check_local_assets()` 会在校验前把仓库内修正版复制回去。只改 `resourcepacks.json` 的 sha256
  而不带包，构建会在 fetch 阶段直接报「校验失败」。
- `AutomaticJavaSwitch=true` 是 Java 自动兜底的开关：实例固定的包内 Java 路径失效时，启动器会从系统检测到的 Java 里挑兼容主版本（MC 26.x = Java 25）；`AutomaticJavaDownload` 必须保持 `false`——自动下载走 meta.prismlauncher.org，失败会直接中止启动。
