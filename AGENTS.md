# AGENTS.md

给接手这个仓库的 agent。动手前读 §0–§2，事实在 §3，踩过的坑在 §7；§8 是收尾清单。

服务端 GitHub 是 [`zhyiheihei/Zccfwq`](https://github.com/zhyiheihei/Zccfwq)（私有仓库），两端的关系与对齐规则见 §4。本仓库在开发机上 clone 成同级目录（NixOS 机叫 `../Zccfwq`，Windows 机叫 `../MC`），逻辑互认一律以 GitHub 全名为准，目录名随机器不同。

---

## 0. 红线

1. **版本只有一处权威**：`pack/pack.json`。`minecraft = 26.1.2`、`loader = fabric 0.20.1`、`java major = 25`。文档、上游元数据、jar 文件名里的 `26.2` / `26.3` / `1.21.x` 都不是本项目的目标，不要据此改版本。
2. **客户端改动必须回灌仓库**：在本机实例里试出来的任何改动，都要经 `scripts/sync_client.py` 落进 `pack/`，由 CI 出 Release。**不允许只留在本机实例**，也不允许手工拼一个包发给玩家。
3. **版本号只能由发布产生**：写进 `pack.json` 的唯一合法途径是 `scripts/set_version.py`，且版本来自提交信息里的 `release: x.y.z`。不要为了"顺手对齐"去改版本号；不发布就不碰。
4. **`main` 上不打 tag**（`rolling` 由工作流创建，永远不要手工建/删/移动）。回退旧版本是禁止动作 —— 出问题就把版本加一位重发。
5. **清单里的哈希不许手改**：`mods.json` 的 `sha512`、`resourcepacks.json` 的 `sha256`、`local-assets.json` 的 `sha256` 都由下载/校验脚本写。手改等于让 `fetch.py` 在 CI 上直接失败。

## 1. 需要明确授权才能做的动作

- `git commit` / `git push` / 触发或重跑 Actions / 手动 `Run workflow` / 发版。
- 从 `pack/*.json` 里**删**条目（模组、资源包、光影），或把模组移入 `dropped.json`。先贴逐项清单，再等确认。
- 改 `pack.json` 里的 `server.ip`、`memory`、`java`、`launcher`。
- 把任何大二进制（jar / zip / 7z / tar.zst）提交进 git。`local-assets/`、`cache/`、`dist*/` 一律不进 git。
- 改 `.github/workflows/`（会改变发布行为）。

## 2. 汇报与验证的规矩

- 结论要有证据：本机实例的 `latest.log`、CI 日志、`verify_bundle.py` 输出。不要用"应该能启动"代替实测。
- 实机验收只认**真开起来的客户端**：Prism 实例能进到主菜单、能连上服务器。中间产物（jar 齐全、清单校验通过）不能替代。
- 发布前后要报：构建版本号、`audit_deps.py` 结果、`verify_bundle.py` 的失败项、Release 里实际传上去的文件名。
- 长任务（`fetch.py` 拉几百 MB、`build.py` 打 7z、CI 构建）要边跑边报进度：当前在做什么、卡在哪、已完成的量。不要静默等。
- 遇到必须先决断的分叉（要不要移出某模组、要不要改内存/版本），停下来给编号选项，不要替用户选。

## 3. 项目事实

### 版本判定，按顺序

1. `pack/pack.json` 的 `minecraft` 是唯一事实来源。
2. `pack/mods.json` 里每条的目标版本也只看 `pack.json`；文件名带 `26.2`、`26.3` 只说明那个 jar 同时兼容更高版本，例如 `advancements_reloaded-0.14.0-fabric-26.2.jar`、`bigger_end_cities-26.1-26.3-1.1.3.jar`。
3. `pack/resourcepacks.json` / `shaderpacks.json` 的 `upstream.game_versions` 是**材质/光影作者发布时声明的版本**，不是本项目目标。带 `note` 的条目是容易误读的，逐条看。
4. `pack/dropped.json` 里 `reason` 写着「止于 26.3（无 26.1.2 构建…」表示那个模组**没有** 26.1.2 构建才被排除。看到这类记录不要反推本项目用了 26.3。
5. 26.1 用资源包 format 65：`pack.mcmeta` 的 `min_format` / `max_format` 是顶层字段，`min_format` 不得低于 15；兼容范围起点低于 65 的老包还必须保留 `pack_format` 与 `supported_formats: {min_inclusive, max_inclusive}`，两种范围要一致。format 65 及以上的包**必须删掉**这两个旧字段。构建脚本会规范化上游包，别把 `min_format/max_format` 塞进 `supported_formats`。

结论：**这个仓库是 26.1，不是 26.2，也不是 26.3。**

### 目录

```
pack/                 清单与配置（唯一事实来源）
  pack.json             整合包元信息（版本、MC、loader、Java、内存、服务器地址）
  mods.json             模组清单（file / project / version_id / sha512 / url / enabled）
  dropped.json          评估过但未采用的模组及原因
  resourcepacks.json    材质清单（45 条）  shaderpacks.json  光影清单（9 条）
  local-assets.json     材质/光影原始压缩包的分发信息（release 资产 assets-<版本>）
  runtimes.json         Java 运行时（URL 必须钉到具体 release）
  launcher.json / mmc-pack.json / options.txt / config/ / android.json
  mods-local/           Modrinth 上没有的自制/付费模组（4 个 jar，清单里写 project: local）
  resourcepacks-local/  就地改过的材质包修正版（本地包优先于 local-assets 里的原包）
scripts/              fetch.py build.py verify_bundle.py update.py audit_deps.py
                      update_assets.py resources.py release_notes.py set_version.py
                      sync_client.py build_android.py verify_android.py
cache/                下载缓存（可删，不进 git）
dist*/                构建产物（不进 git）
local-assets/         材质与光影原始 zip（约 262MB，不进 git）
```

清单条数与本地模组的存在性用命令查，别抄数字（数字会过期）：

```bash
python3 - <<'PY'
import json, os
m = json.load(open('pack/mods.json', encoding='utf-8'))
print('模组', len(m), '本地', sum(1 for x in m if x['project'] == 'local'))
print('本地 jar 缺文件:', [x['file'] for x in m if x['project'] == 'local'
                          and not os.path.exists('pack/mods-local/' + x['file'])])
PY
```

### 常用命令

```bash
python3 scripts/fetch.py                        # 拉全部依赖到 cache/，并按清单校验 local-assets/
python3 scripts/build.py --zip                  # 组装四平台 + 7z
python3 scripts/build.py --fast --target linux  # 只重建实例，跳过资源复制，改配置时用
python3 scripts/verify_bundle.py                # 产物自检（离线可启动、材质/光影齐全等）
python3 scripts/audit_deps.py                   # 依赖检查（缺依赖=构建失败，CI 里是阻断式的）
MODPACK_DIST=/var/tmp/android-dist python3 scripts/build_android.py
MODPACK_DIST=/var/tmp/android-dist python3 scripts/verify_android.py  # FCL Android 实验包（非 APK）
python3 scripts/update_assets.py                # 报告材质/光影有哪些上游新版本
python3 scripts/update_assets.py --apply        # 落地：替换 + 补 mcmeta + 同步清单与 options.txt
python3 scripts/package_assets.py               # 重打材质原件 tar.zst，用于发新 assets-<版本>
python3 scripts/sync_client.py                  # 客户端改动进仓库：预演差异（mods/config/options）
python3 scripts/sync_client.py --apply          # 落盘
python3 scripts/sync_client.py --apply --release 0.2.2   # 落盘 + 改版本 + 提交推送
python3 scripts/set_version.py 0.2.4            # 只改 pack.json 版本（CI 自动做，本地一般不用）
```

`scripts/update.py`（模组版本对齐）**只在 Actions 的 `update-mods` 工作流里跑**，不要在本地跑完手工提交：
它写回 `mods.json` 后会自己提交并 `workflow_dispatch` 触发构建。

## 4. 与服务端仓库的关系

服务端 `zhyiheihei/Zccfwq` 是另一个 git 仓库（私有），客户端是公开的（玩家从 Release 下载）。本仓库的 agent 可以直接调服务端的 `tools/check_alignment.py`（本机有同级 clone 时自动用本地目录，否则匿名拉本仓库 raw 清单）；服务端侧对应规则见其 AGENTS.md §4。

| 项 | 客户端（本仓库） | 服务端（`zhyiheihei/Zccfwq`） | 规则 |
|---|---|---|---|
| MC | `pack/pack.json` `minecraft` | `server/mods` 里的 jar 目标版本 | 必须都是 **26.1.2** |
| Loader | `pack.json` `loader.version` | `fabric/gradle.properties` `loader_version` | 必须都是 **0.20.1** |
| Java | `pack.json` `java.major` | 镜像基座 JDK | 必须都是 **25** |
| 版本号 | `pack.json` `version`（滚动 Release） | `server/VERSION`（镜像 tag） | **各自独立**，不要求相等 |
| 发布 | `main` + 提交信息 `release: x.y.z` + Release `rolling` | `main` + `server/VERSION` + GHCR tag | 互不触发 |

模组集合的对齐规则：

- `pack/mods.json` 是**客户端唯一权威**。服务端的 `server/mods` 必须是它的子集（服务端不需要的那 67 个客户端专属模组不在此列），服务端独有件放在 `server/mods-fabric/`。
- 改模组集 = 三个动作一起做：客户端清单（`sync_client.py` 或 `update-mods`）→ 服务端 `server/mods` → 服务端 `docs/mod-inventory.md`。只改一端等于制造"客户端能进、服务端崩"或反之。
- `server/mods_client_only/` 是**过时的部分镜像**（17 个 jar，与清单已经漂移：jei 111 vs 清单 110、moreculling 1.7.3 vs 1.7.4、SubtleEffects 1.15.1 vs 1.15.3）。不要往里加东西，也不要拿它当客户端模组集。
- 比较两端不要只看文件名：`ResourcefulLib-4.0.1.jar`（服务端）与 `ResourcefulLib-fabric-4.0.2.jar`（客户端）是同一模组的两个版本。`trinkets` 两端现在是同一个上游 jar（`trinkets-4.0.1+26.1.jar`，sha512 一致），服务端不再有 `-arclight` 补丁版。

查两端差集：

```bash
python3 - <<'PY'
import json, os
# 探测同级的服务端 clone（目录名随机器：NixOS 机叫 Zccfwq，Windows 机叫 MC）
srv_repo = next(p for p in ('../Zccfwq', '../MC') if os.path.isdir(p + '/server/mods'))
srv = {f for f in os.listdir(srv_repo + '/server/mods') if f.endswith('.jar')}
cli = {x['file'] for x in json.load(open('pack/mods.json', encoding='utf-8'))}
print('服务端有、客户端没有:', sorted(srv - cli))   # 预期只剩 c2me / darkmobs / ResourcefulLib 旧版
PY
```

**不要把服务端的东西写进本仓库**：RCON 密码、MCSM API key、内网地址、世界路径一律不出现（本仓库是公开的）。

## 5. 客户端开发流程（唯一通道）

本机实例（`MODPACK_INSTANCE`，缺省 `D:/我的世界/重生之异世界生存/.minecraft/versions/重生之异世界生成1.0v`）里试出来的改动，必须回灌仓库、由 CI 出 Release：

1. `python3 scripts/sync_client.py` 看差异，`--apply` 落盘。模组按 sha512 反查 Modrinth 自动补元数据；查不到的（付费、自制数据包）先把 jar 放进 `pack/mods-local/` 再跑，脚本会写成 `project: local`，CI 直接从仓库取。
2. `python3 scripts/fetch.py && python3 scripts/build.py --fast --target linux` 本地抽检（可选，CI 会做全量）。
3. `python3 scripts/sync_client.py --apply --release <新版本>` → 改 `pack.json` version、提交（信息带 `release: <新版本>`）、推送 `main`，Actions 构建完自动更新滚动 Release。

实机验收：用本机 NixOS 上的 PrismLauncher 实例，**用户明确授权后**才由 agent 启动 Prism 并看该实例的 `latest.log`。默认服务器两个：`server`（正式服 `mc.zhyi.xin`，`auto_join` 自动连接）+ `extra_servers`（测试服 `mc.zhyi.xin:25566`），都预置进 `servers.dat`（`build.py` 的 `write_servers`）；临时连接的地址不要写进 `pack.json`。

## 6. 发布（滚动更新）

只有一个分支 `main`，**不打 tag**，版本不进 git 历史文件：

- 版本号写在**提交信息**里，形如 `release: 0.2.4`（`[release 0.2.4]` 也认）。工作流看到这一句才构建，普通提交直接跳过；手动 `Run workflow` 无条件构建。
- CI 用 `scripts/set_version.py <版本>` 把它写进 `pack/pack.json` 再打包。
- 发布到**同一个滚动 Release**（tag 固定 `rolling`，工作流自动创建）：每次构建先删旧资产再传新的，下载入口固定，内容永远是最新一次构建。
- 测试期策略：`verify_bundle.py` 自检 `continue-on-error`，只报告不阻断，带问题也照发；出问题**禁止回退旧版本**，版本加一位重发。
- `audit_deps.py` 是**阻断式**的：缺依赖的包一启动就崩，这类问题不发版。

```bash
python3 scripts/set_version.py 0.2.4      # 本地同步版本号（CI 会自动做）
git commit -m "release: 0.2.4 简述改动"    # 提交信息带版本即触发工作流
git push origin main
```

## 7. 已知坑（都已处理，改包时别退化）

- **MC 26.x 要 GLFW 3.5 的 `glfwSetPreeditCallback`**。NixOS 系统 GLFW 3.4 没这个符号，`UseNativeGLFW=true` 会在 `InputConstants` 初始化时 NPE 崩掉；便携包的 `prismlauncher.cfg` 必须 `UseNativeGLFW=false`。
- **`options.txt` 的 `key_*` 不能带 `o:CONTROL_OR_COMMAND`** 这类 Forge 修饰符后缀，否则 `InputConstants.getKey` 抛 `NumberFormatException`，**整个 options.txt 加载失败**（材质包启用顺序全丢）。
- **资源包 format 65**：新包必须删除 `supported_formats`；旧包若仍支持 format <65，`pack_format` 与 `supported_formats: {min_inclusive, max_inclusive}` 必须与顶层 `min_format/max_format` 一致。只用 `supported_formats: {min_format, max_format}` 会让资源包被标为不兼容。
- **`mmc-pack.json` 带 `cachedSha256`** 且与随包 meta 文件一致时，启动器才不去远程拉组件元数据（假 IP/断网环境会直接拦住启动）。MMC 导入包不含 meta，故不写。
- **不要把 MC 直接从仓库目录跑起来**：实例目录与运行日志读写频繁，会把仓库搞脏、也会让 `git status` 一片红。先复制到 `/var/tmp` 之类路径再跑。（这仓库早先位于 bindfs 挂载上，有约 50 个并发文件上限；2026-11-21 在 NixOS 主机上核查已是 btrfs 普通目录 —— 换机器时用 `stat -f -c %T ~/Documents` 确认后再决定要不要多绕这一层。）
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
- **`alexsmobs` + `codxlib` 自 0.4.1 起两端移除**：`alexsmobs:leafcutter_anthill` 这个 worldgen feature 会在区块生成 worker 线程上 `ant.remove(DISCARDED)`，撞 Arclight 给 Folia `EntityScheduler.retire` 打的 `Bukkit.isPrimaryThread()` 断言，直接崩服（`ReportedException: Feature placement`）。经过与原因见服务端仓库的 `CHANGELOG.md` 0.5.x「迁移」条目与其 AGENTS.md §7。别因为 Modrinth 上有 26.1.2 构建就加回来。

## 8. 收尾清单（每个任务结束前过一遍）

- [ ] `pack/pack.json` 的版本是我应该改的吗？没有 `release:` 意图就还原。
- [ ] 清单里的哈希/大小是从脚本写的，不是我手填的。
- [ ] 改过 `pack/` 就跑过 `python3 scripts/audit_deps.py`；改过 `scripts/` 就跑过对应入口的最小用例。
- [ ] 模组有增减时，服务端 `../Zccfwq/server/mods` 与 `docs/mod-inventory.md` 同步了吗？
- [ ] 有没有把服务端私密信息（RCON / API key / 内网地址）写进这个公开仓库？
- [ ] 提交信息是否带 `release: x.y.z`（要发布）或不带（只攒改动）—— 二选一，不要含糊。
- [ ] 汇报里给出：改了什么、证据（日志/命令输出）、还差什么。
