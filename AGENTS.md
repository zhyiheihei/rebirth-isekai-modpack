# AGENTS.md

给接手这个仓库的 agent。事实在 §3，踩过的坑在 §7。

服务端 GitHub 是 [`zhyiheihei/Zccfwq`](https://github.com/zhyiheihei/Zccfwq)（私有仓库），两端的关系与对齐规则见 §4。本仓库在开发机上 clone 成同级目录（NixOS 机叫 `../Zccfwq`，Windows 机叫 `../MC`），逻辑互认一律以 GitHub 全名为准，目录名随机器不同。

---

## 0. 红线

1. **版本只有一处权威**：`pack/pack.json`。`minecraft = 26.3`、`loader = fabric 0.20.1`、`java major = 25`。
2. **客户端改动必须回灌仓库**：在本机实例里试出来的任何改动，都要经 `scripts/sync_client.py` 落进 `pack/`，由 CI 出 Release。**不允许只留在本机实例**，也不允许手工拼一个包发给玩家。
3. **版本号只能由发布产生**：写进 `pack.json` 的唯一合法途径是 `scripts/set_version.py`，且版本来自提交信息里的 `release: x.y.z`。不要为了"顺手对齐"去改版本号；不发布就不碰。
4. **`main` 上不打 tag**（`rolling` 由工作流创建，永远不要手工建/删/移动）。回退旧版本是禁止动作 —— 出问题就把版本加一位重发。
5. **清单里的哈希不许手改**：`mods.json` 的 `sha512`、`resourcepacks.json` 的 `sha256`、`local-assets.json` 的 `sha256` 均由脚本写入。

## 1. 需要明确授权才能做的动作

- `git commit` / `git push` / 触发或重跑 Actions / 手动 `Run workflow` / 发版。
- 从 `pack/*.json` 里**删**条目（模组、资源包、光影），或把模组移入 `dropped.json`。先贴逐项清单，再等确认。
- 改 `pack.json` 里的 `server.ip`、`memory`、`java`、`launcher`。
- 把任何大二进制（jar / zip / 7z / tar.zst）提交进 git。`local-assets/`、`cache/`、`dist*/` 一律不进 git。
- 改 `.github/workflows/`（会改变发布行为）。

## 2. 汇报与验证的规矩

- 结论要有证据：本机实例的 `latest.log`、CI 日志、`verify_bundle.py` 输出。
- 实机验收只认**真开起来的客户端**（Prism 能进主菜单、能连上服务器），中间产物不算。
- 长任务要边跑边报进度；遇到必须先决断的分叉，停下来给编号选项。
- 发布后报：版本号、`audit_deps.py` 结果、`verify_bundle.py` 失败项、Release 实际文件名。

## 3. 项目事实

### 版本与资源包格式

1. `pack/pack.json` 的 `minecraft` 是唯一事实来源。
2. 26.3 用资源包 format **97.1**（26.1 是 65；数据包 121）：`pack.mcmeta` 的 `min_format` / `max_format` 是顶层字段，`min_format` 不得低于 15；兼容范围起点低于 65 的老包还必须保留 `pack_format` 与 `supported_formats: {min_inclusive, max_inclusive}`，两种范围要一致。format 65 及以上的包**必须删掉**这两个旧字段。构建脚本会规范化上游包，别把 `min_format/max_format` 塞进 `supported_formats`。

### 目录

```
pack/                 清单与配置（唯一事实来源）
  pack.json             整合包元信息（版本、MC、loader、Java、内存、服务器地址）
  mods.json             模组清单（file / project / version_id / sha512 / url / enabled）
  dropped.json          评估过但未采用的模组及原因
  resourcepacks.json    材质清单   shaderpacks.json  光影清单
  local-assets.json     材质/光影原始压缩包的分发信息（release 资产 assets-<版本>）
  runtimes.json         Java 运行时（URL 必须钉到具体 release）
  launcher.json / options.txt / config/ / android.json
  mods-local/           Modrinth 上没有的自制/付费模组（清单里写 project: local）
  resourcepacks-local/  就地改过的材质包修正版（本地包优先于 local-assets 里的原包）
scripts/              fetch.py build.py verify_bundle.py update.py audit_deps.py
                      update_assets.py resources.py release_notes.py set_version.py
                      sync_client.py build_android.py verify_android.py
cache/                下载缓存（可删，不进 git）
dist*/                构建产物（不进 git）
local-assets/         材质与光影原始 zip（约 262MB，不进 git）
```

### 常用命令

```bash
python3 scripts/fetch.py                        # 拉依赖到 cache/，并校验 local-assets/
python3 scripts/build.py --zip                  # 四平台 + 7z
python3 scripts/build.py --fast --target linux  # 只重建实例，改配置时用
python3 scripts/verify_bundle.py                # 产物自检
python3 scripts/audit_deps.py                   # 依赖检查（CI 里阻断）
python3 scripts/sync_client.py                  # 客户端改动进仓库，--apply 落盘
python3 scripts/update_assets.py                # 材质/光影上游版本报告，--apply 落地
```

`scripts/update.py`（模组版本对齐）只在 Actions 的 `update-mods` 工作流里跑，不要本地跑完手工提交。

## 4. 与服务端仓库的关系

服务端 `zhyiheihei/Zccfwq` 是另一个 git 仓库（私有），客户端是公开的（玩家从 Release 下载）。本仓库的 agent 可以直接调服务端的 `tools/check_alignment.py`（本机有同级 clone 时自动用本地目录，否则匿名拉本仓库 raw 清单）；服务端侧对应规则见其 AGENTS.md §4。

| 项 | 客户端（本仓库） | 服务端（`zhyiheihei/Zccfwq`） | 规则 |
|---|---|---|---|
| MC | `pack/pack.json` `minecraft` | `server/mods` 里的 jar 目标版本 | 必须都是 **26.3** |
| Loader | `pack.json` `loader.version` | `fabric/gradle.properties` `loader_version` | 必须都是 **0.20.1** |
| Java | `pack.json` `java.major` | 镜像基座 JDK | 必须都是 **25** |
| 版本号 | `pack.json` `version`（滚动 Release） | `server/VERSION`（镜像 tag） | **各自独立**，不要求相等 |
| 发布 | `main` + 提交信息 `release: x.y.z` + Release `rolling` | `main` + `server/VERSION` + GHCR tag | 互不触发 |

模组集合的对齐规则：

- `pack/mods.json` 是**客户端唯一权威**。服务端的 `server/mods` 必须是它的子集（服务端不需要的那 67 个客户端专属模组不在此列），服务端独有件放在 `server/mods-fabric/`。
- 改模组集 = 三个动作一起做：客户端清单（`sync_client.py` 或 `update-mods`）→ 服务端 `server/mods` → 服务端 `docs/mod-inventory.md`。

**不要把服务端的东西写进本仓库**：RCON 密码、MCSM API key、内网地址、世界路径一律不出现（本仓库是公开的）。

## 5. 客户端开发流程（唯一通道）

本机实例（`MODPACK_INSTANCE`，缺省 `D:/我的世界/重生之异世界生存/.minecraft/versions/重生之异世界生成1.0v`）里试出来的改动，必须回灌仓库、由 CI 出 Release：

1. `sync_client.py` 看差异、`--apply` 落盘；Modrinth 上查不到的 jar 先放进 `pack/mods-local/`，脚本写成 `project: local`。
2. `sync_client.py --apply --release <版本>` = 落盘 + 改版本 + 提交推送，Actions 构建完自动更新滚动 Release。

实机验收：用本机 NixOS 上的 PrismLauncher 实例，**用户明确授权后**才由 agent 启动 Prism 并看该实例的 `latest.log`。默认服务器两个：`server`（正式服 `mc.zhyi.xin`，`auto_join` 自动连接）+ `extra_servers`（测试服 `mc.zhyi.xin:25566`），都预置进 `servers.dat`（`build.py` 的 `write_servers`）；临时连接的地址不要写进 `pack.json`。

## 6. 发布（滚动更新）

只有一个分支 `main`，**不打 tag**，版本不进 git 历史文件：

- 版本号写在**提交信息**里，形如 `release: 0.2.4`（`[release 0.2.4]` 也认）。工作流看到这一句才构建，普通提交直接跳过；手动 `Run workflow` 无条件构建。
- CI 用 `scripts/set_version.py <版本>` 把它写进 `pack/pack.json` 再打包。
- 发布到**同一个滚动 Release**（tag 固定 `rolling`，工作流自动创建）：每次构建先删旧资产再传新的，下载入口固定，内容永远是最新一次构建。
- 测试期策略：`verify_bundle.py` 自检 `continue-on-error`，只报告不阻断，带问题也照发；出问题**禁止回退旧版本**，版本加一位重发。
- `audit_deps.py` 是**阻断式**的：缺依赖的包一启动就崩，这类问题不发版。

## 7. 已知坑（都已处理，改包时别退化）

- **MC 26.x 要 GLFW 3.5 的 `glfwSetPreeditCallback`**。NixOS 系统 GLFW 3.4 没这个符号，`UseNativeGLFW=true` 会在 `InputConstants` 初始化时 NPE 崩掉；便携包的 `prismlauncher.cfg` 必须 `UseNativeGLFW=false`。
- **`options.txt` 的 `key_*` 不能带 `o:CONTROL_OR_COMMAND`** 这类 Forge 修饰符后缀，否则 `InputConstants.getKey` 抛 `NumberFormatException`，**整个 options.txt 加载失败**（材质包启用顺序全丢）。
- **资源包 format 97.1**（26.1 时是 65）：`max_format` 覆盖不到 97 的包会被判不兼容；新包必须删除 `supported_formats`；旧包若仍支持 format <65，`pack_format` 与 `supported_formats: {min_inclusive, max_inclusive}` 必须与顶层 `min_format/max_format` 一致。只用 `supported_formats: {min_format, max_format}` 会让资源包被标为不兼容。
- **`mmc-pack.json` 只由 `build.py` 的 `write_mmc_pack()` 生成**（LWJGL 版本从 `net.minecraft` 元数据的 `requires` 取，26.3 是 3.4.3）；仓库里不再放静态副本。带 `cachedSha256` 且与随包 meta 一致时启动器才不去远程拉元数据（假 IP/断网会拦住启动），MMC 导入包不含 meta 故不写。
- **不要把 MC 直接从仓库目录跑起来**：实例目录与运行日志读写频繁，会把仓库搞脏、也会让 `git status` 一片红。先复制到 `/var/tmp` 之类路径再跑。
- **实例目录名固定 ASCII `RebirthIsekai`**（显示名 `name=` 才是中文）：Windows 上 cmd/PowerShell 传中文参数会因代码页丢字符，`JavaPath` 替换曾经就是这样失效的。
- **Windows 启动逻辑全在 `launch.ps1`**（UTF-8 **带 BOM**，否则 PowerShell 5.1 读中文乱码），`启动游戏.bat` 只用 `-File` 调用；`.bat` 必须 CRLF，写成 CRCRLF 会解析异常。
- **`verify_bundle.py` 的 `check_runnable()`** 按产物自身的标志文件判断平台（`prismlauncher.exe` / `*.app` / `PrismLauncher`），不看宿主机；换启动器文件名时记得同步那里。
- **`xali's Enhanced Vanilla` 上游 zip 条目重叠**（`unzip` 只报 warning，Python `zipfile` 直接抛错），本地是解出后重建的副本，不要用上游原包覆盖。
- **Android 只生成 FCL 可导入的 `.mrpack`**，不生成也不分发自制 APK；`pack/android.json` 维护单独实验配置，基础依赖版本仍来自 `pack/pack.json` / `pack/mods.json`。FCL 声明支持 Fabric + Java 25，只证明格式兼容，**不等同于已在 Android 实机通过**。先关光影，模组排除必须由实际设备日志驱动；实机验收前不要把 Android 包接入滚动 Release。
- **账号机制（别拆）**：`accounts.json` 的占位 MSA 账号 + `prismlauncher.cfg` 的死代理（SOCKS5 127.0.0.1:9）是离线打开即用的前提 —— Prism 11 的 `ownsMinecraft()` 排除 Offline 类型账号，没有占位 MSA 会弹 Demo 确认框/登录向导；死代理让占位账号的静默刷新以网络错误收场（STATE_OFFLINE），不弹重新认证框。启动脚本检测到 `accounts.json` 出现非占位 `refresh_token`（玩家已登录微软正版）时会撤掉死代理、不再传 `--offline`；「启动正版」脚本无条件走这条路。`verify_bundle.py` 对这套机制有回归检查。
- **就地改过的材质包**（如剔除包内 JSON 尾部的作者签名行）必须放进 `pack/resourcepacks-local/`：`local-assets/` 不进 git，CI 靠 actions/cache 或发布资产恢复，缓存里的旧包会盖掉修正版，`check_local_assets()` 会在校验前把仓库内修正版复制回去。只改 `resourcepacks.json` 的 sha256 而不带包，构建会在 fetch 阶段直接报「校验失败」。
- **移出「库」类模组前先查依赖**：0.4.0 按服务端性能方案移出 YUNG 系列时把 `YungsApi` 一起删了，但 `TravelersTitles` 硬依赖 `yungsapi >= 26.1.2-Fabric-6.1.0`；服务端没有 TravelersTitles 所以一直正常，客户端直到 0.4.3 启动才 `Incompatible mods found`。现在清单保留 `YungsApi-26.1.2-Fabric-6.1.3.jar`（纯库，不生成世界）。`scripts/audit_deps.py` 会扫 `cache/mods` 的 `fabric.mod.json`（含内嵌 jar 与 provides）并把缺依赖当构建失败。
- **`pack/runtimes.json` 的 Java URL 必须钉到具体 release**（形如 `.../releases/download/jdk-25.0.5.1%2B2/...`），不能用 `api.adoptium.net/v3/binary/latest/...`：上游一发新构建，同一个 URL 的内容就变，而清单里的 sha256 没变，`fetch.py` 会下载失败，旧流程要等到 `build.py` 的 `extract_runtime` 才崩（0.4.2 就是这样挂的）。升级运行时＝URL、sha256、`release` 字段一起换。
- **`AutomaticJavaSwitch=true`** 是 Java 自动兜底；`AutomaticJavaDownload` 必须保持 `false`（自动下载走 meta.prismlauncher.org，失败会直接中止启动）。
- **`instance.cfg` 的 `OverrideJavaArgs=true` + `JvmArgs=-XX:+UseZGC`**：Prism 默认给的是 G1，原版 26.3 的 `default-user-jvm` 早就换成 ZGC；5G 堆上的 G1 停顿是掉帧尖峰来源（Distant Horizons 会在聊天栏点名）。删掉这行或退回 G1 等于退化。
- **26.3 在 Wayland 下走 XWayland 时 OpenGL 后端会加载失败**：`renderpearl` 的 `GlBackend.loadLibrary` 报 `OpenGL is not supported: Could not retrieve OpenGL functions`——LWJGL 因 `WAYLAND_DISPLAY` 选了 `libEGL.so.1`，而 SDL 用的 x11 驱动走 GLX。JVM 加 `-Dorg.lwjgl.opengl.contextAPI=native` 即可（MC-312230 的官方 workaround），`build.py` 的 `JvmArgs` 里已带。**不要**为了绕这个去强制 `SDL_VIDEO_DRIVER=wayland`：那样 SDL 不再经 XWayland 承接合成器缩放，整机 HiDPI（umbriel `output.eDP-1.scale`）对 MC 失效，窗口和 UI 都按 1:1 物理像素画，在这块 2880x1800 面板上明显偏小。
- **`config/sodium-options.json` 的 `use_no_error_g_l_context` 必须 `false`**：Sodium 默认开无错误 GL 上下文，Iris 在首次渲染世界（translucents 合成阶段）会绑一个不存在的纹理名，Mesa 的 `bind_texture_object` 跳过空指针检查直接 SIGSEGV（只留 `hs_err_pid*.log`，没有 crash-report，堆栈是 `SamplerBinding.updateSampler`）。上游记录在 Iris issue #3367，关掉后退化成无害的 `GL_INVALID_OPERATION`。
- **`alexsmobs` + `codxlib` 自 0.4.1 起两端移除**：`alexsmobs:leafcutter_anthill` 这个 worldgen feature 会在区块生成 worker 线程上 `ant.remove(DISCARDED)`，撞 Arclight 给 Folia `EntityScheduler.retire` 打的 `Bukkit.isPrimaryThread()` 断言，直接崩服（`ReportedException: Feature placement`）。经过与原因见服务端仓库的 `CHANGELOG.md` 0.5.x「迁移」条目与其 AGENTS.md §7。别因为 Modrinth 上有 26.1.2 构建就加回来。
