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
2. `pack/mods.json` 里 259 个模组的 `version_id` 全部在 Modrinth 上声明支持 `26.1.2`（已逐个用 `/v2/version/{id}` 核对）。文件名里出现 `26.2`、`26.3` 只说明那个 jar 同时兼容更高版本，例如 `advancements_reloaded-0.14.0-fabric-26.2.jar`、`bigger_end_cities-26.1-26.3-1.1.3.jar`。
3. `pack/resourcepacks.json` / `shaderpacks.json` 里的 `upstream.game_versions` 是**上游发布时声明的版本**，不是本项目的目标。带 `note` 字段的条目是名字或上游版本容易引起误读的，逐条看 note。
4. `pack/dropped.json` 里的 `reason: "止于 26.3（无 26.1.2 构建…"` 表示那个模组**没有** 26.1.2 构建、因此被排除。看到这类记录不要反推本项目用了 26.3。
5. 材质包靠 `pack.mcmeta` 的 `supported_formats: {min_format, max_format: 999}` 在 26.1.2 加载；上游停更在 1.20/1.21 的老包也能用，只是新贴图不生效。

结论：**这个仓库是 26.1，不是 26.2，也不是 26.3。**

## 目录

```
pack/            清单与配置（唯一事实来源）：pack.json / mods.json / dropped.json /
                 resourcepacks.json / shaderpacks.json / local-assets.json / config / options.txt
local-assets/    材质与光影原始 zip（约 262MB，不进 git，托管在 release 资产 assets-<版本>）
scripts/         fetch.py（拉依赖）build.py（组装）verify_bundle.py（自检）
                 update_assets.py（对齐材质/光影上游）resources.py / release_notes.py
cache/           下载缓存，可删
dist/            构建产物，可删
```

## 常用命令

```bash
python3 scripts/fetch.py                        # 拉全部依赖到 cache/，并按清单校验 local-assets/
python3 scripts/build.py --zip                  # 组装四平台 + 7z
python3 scripts/build.py --fast --target linux  # 只重建实例，跳过资源复制，改配置时用这个
python3 scripts/verify_bundle.py                # 产物自检（离线可启动、材质/光影齐全等）
python3 scripts/update_assets.py                # 报告材质/光影有哪些上游新版本
python3 scripts/update_assets.py --apply        # 落地：替换 + 补 mcmeta + 同步清单与 options.txt
python3 scripts/package_assets.py               # 重打材质原件 tar.zst，用于发新 assets-<版本>
```

## 发布

Actions 页面点一次 `Run workflow`（`build`）即构建 + 自检 + 发 Release，`release` 输入默认 `true`。
也可以 `git tag v<版本> && git push origin v<版本>`，工作流会校验 tag 与 `pack/pack.json` 的 `version` 一致。

## 已知坑（都已处理，改包时别退化）

- MC 26.x 要 GLFW 3.5 的 `glfwSetPreeditCallback`。NixOS 系统 GLFW 3.4 没有这个符号，`UseNativeGLFW=true` 会在 `InputConstants` 初始化时 NPE 崩掉；便携包的 `prismlauncher.cfg` 必须 `UseNativeGLFW=false`。
- `options.txt` 里 `key_*` 的值不能带 `o:CONTROL_OR_COMMAND` 这类 Forge 修饰符后缀，否则 `InputConstants.getKey` 抛 `NumberFormatException`，**整个 options.txt 加载失败**（材质包启用顺序全丢）。
- 材质包 `pack.mcmeta` 必须是 `supported_formats: {min_format, max_format}`；26.x 里写 `min_inclusive`/`max_inclusive` 会被判为「declares support for version newer than 64, but is missing mandatory fields」而回落。
- `mmc-pack.json` 里带 `cachedSha256` 且与随包 meta 文件一致，启动器才不会去远程拉组件元数据（假 IP/断网环境会直接拦住启动）。MMC 导入包不含 meta，故不写。
- `~/Documents` 是 bindfs（FUSE）挂载，同时只能再打开约 50 个文件。Minecraft 客户端/服务端都不能直接从仓库目录启动，要复制到 `/var/tmp` 之类路径再跑。
- `xali's Enhanced Vanilla` 上游 zip 条目重叠（`unzip` 只报 warning，Python `zipfile` 直接抛错），本地是解出后重建的副本，不要用上游原包覆盖。
