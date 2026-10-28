"""把本机客户端实例的实际改动同步回 pack/（客户端开发的正规入口）。

范围：mods.json / config/ / options.txt。local-assets（材质、光影）用 update_assets.py 对齐，
不走这里。默认预演，只报告不写盘。

用法:
    python3 scripts/sync_client.py                          # 预演
    python3 scripts/sync_client.py --apply                  # 落盘
    python3 scripts/sync_client.py --apply --prune-mods     # 同时删掉本机已移除的模组条目
    python3 scripts/sync_client.py --apply --release 0.2.2  # 落盘 + 改版本 + 提交推送（滚动 Release）

实例路径优先级: --instance > 环境变量 MODPACK_INSTANCE > <repo>/.instance > 内置缺省
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DEFAULT_INSTANCE = r"D:/我的世界/重生之异世界生存/.minecraft/versions/重生之异世界生成1.0v"

# 备份、日志、运行时缓存的排除规则（与历史同步口径保持一致）
EXCL_NAME = re.compile(r"(\.bak|\.log$|\.tmp$|\.db$)", re.I)
EXCL_REL = {
    "resourceful-config-web.json",  # 含 web 配置口令
    "wover/cached.json",            # 运行时缓存
    "rpg_series/tag_cache.json",    # 运行时标签缓存（每次启动重建，进版本库只会一直是旧快照）
    "rpg_series/loot_fallback_report.json",  # 运行时战利品回退报告
}


def instance_path(arg):
    for cand in (arg, os.environ.get("MODPACK_INSTANCE")):
        if cand:
            return cand
    marker = os.path.join(common.ROOT, ".instance")
    if os.path.exists(marker):
        with open(marker, encoding="utf-8") as fh:
            return fh.read().strip()
    return DEFAULT_INSTANCE


def excluded(rel):
    if rel in EXCL_REL:
        return True
    if any(part.endswith("_备份") or "备份_" in part for part in rel.split("/")):
        return True
    return bool(EXCL_NAME.search(os.path.basename(rel)))


def walk(base):
    out = {}
    for root, _, files in os.walk(base):
        for name in files:
            path = os.path.join(root, name)
            out[os.path.relpath(path, base).replace("\\", "/")] = path
    return out


# ---------------- mods ----------------

def local_entry(path):
    """pack/mods-local/ 里的自制 / 付费数据包模组：直接内嵌进仓库。"""
    name = os.path.basename(path)
    target = os.path.join(common.PACK, "mods-local", name)
    if not os.path.exists(target):
        return None
    if common.sha("sha512", target) != common.sha("sha512", path):
        return None
    meta, loader = read_meta(target)
    return {
        "file": name,
        "project": "local",
        "version": meta.get("version", "0"),
        "version_id": "local",
        "loader": loader,
        "sha512": common.sha("sha512", target),
        "url": "",
        "local": f"pack/mods-local/{name}",
        "enabled": True,
        "source_mod": meta.get("id", name),
    }


def read_meta(jar):
    """从 jar 里读 fabric.mod.json / mods.toml 的 id 与版本，判加载器。"""
    import zipfile

    meta = {"id": os.path.basename(jar), "version": "0"}
    try:
        with zipfile.ZipFile(jar) as zf:
            names = zf.namelist()
            if "fabric.mod.json" in names:
                data = json.loads(zf.read("fabric.mod.json").decode("utf-8"))
                run = data.get("depends", {})
                neoforge = any(k in run for k in ("neoforge", "forge"))
                return ({"id": data.get("id", meta["id"]), "version": str(data.get("version", "0"))},
                        "neoforge" if neoforge else "fabric")
            for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if name in names:
                    text = zf.read(name).decode("utf-8", "replace")
                    mod_id = re.search(r'modId\s*=\s*"([^"]+)"', text)
                    ver = re.search(r'version\s*=\s*"([^"]+)"', text)
                    return ({"id": mod_id.group(1) if mod_id else meta["id"],
                             "version": ver.group(1) if ver else "0"}, "neoforge")
    except Exception:
        pass
    return meta, "fabric"


def modrinth_entry(path):
    """按 sha512 反查 Modrinth，返回 mods.json 条目；查不到返回 None。"""
    digest = common.sha("sha512", path)
    try:
        ver = common.fetch_json(
            f"https://api.modrinth.com/v2/version_file/{digest}?algorithm=sha512")
        proj = common.fetch_json(f"https://api.modrinth.com/v2/project/{ver['project_id']}")
    except Exception:
        return None
    file = next((f for f in ver["files"] if f["hashes"]["sha512"] == digest), None)
    if not file:
        return None
    return {
        "file": os.path.basename(path),
        "project": ver["project_id"],
        "version": ver["version_number"],
        "version_id": ver["id"],
        "loader": "fabric" if "fabric" in (ver.get("loaders") or []) else (ver.get("loaders") or [""])[0],
        "sha512": digest,
        "url": file["url"],
        "enabled": True,
        "source_mod": proj.get("slug", ver["project_id"]),
    }


def diff_mods(inst):
    """返回 (新增 jar 路径列表, 本机缺失的条目列表)。"""
    entries = common.load("mods.json")
    known = {e["file"] for e in entries}
    local = {n: p for n, p in walk(os.path.join(inst, "mods")).items()
             if n.lower().endswith(".jar") and "/" not in n}
    added = sorted(set(local) - known)
    gone = sorted(e["file"] for e in entries if e["file"] not in local)
    return entries, local, added, gone


# ---------------- config ----------------

def diff_config(inst):
    src = walk(os.path.join(inst, "config"))
    dst = walk(os.path.join(common.PACK, "config"))
    src = {k: v for k, v in src.items() if not excluded(k)}
    dst = {k: v for k, v in dst.items() if not excluded(k)}
    add = sorted(set(src) - set(dst))
    upd = sorted(k for k in set(src) & set(dst) if common.sha("sha256", src[k]) != common.sha("sha256", dst[k]))
    return src, add, upd, sorted(set(dst) - set(src))


def gson_dumps(arr):
    """按 Minecraft（Gson）的写法序列化字符串数组：转义 & ' < > =，其余保持 UTF-8。"""
    text = json.dumps(arr, ensure_ascii=False, separators=(",", ":"))
    for ch, esc in (("&", "\\u0026"), ("'", "\\u0027"), ("<", "\\u003c"),
                    (">", "\\u003e"), ("=", "\\u003d")):
        text = text.replace(ch, esc)
    return text


def sanitize_options(raw, manifest):
    """把 options.txt 的 resourcePacks 收敛到随包分发的范围。

    实例里可能启用着玩家自己的私有材质包（不在 pack/resourcepacks.json 里），
    直接同步出去会让别人的 options.txt 引用一个不存在的文件。只保留
    `file/` 前缀且在清单内的条目，其余（vanilla / moonlight:merged_pack 之类的
    模组虚拟包）原样保留。返回 (新文本, 被剔除的条目列表)。
    """
    out, dropped = [], []
    for line in raw.splitlines():
        if not line.startswith("resourcePacks:"):
            out.append(line)
            continue
        key, val = line.split(":", 1)
        try:
            arr = json.loads(val)
        except ValueError:
            out.append(line)
            continue
        kept = []
        for item in arr:
            if item.startswith("file/") and item[5:] not in manifest:
                dropped.append(item[5:])
            else:
                kept.append(item)
        if len(kept) == len(arr):
            out.append(line)          # 没剔除任何东西就保留原文，避免格式漂移
            continue
        out.append(key + ":" + gson_dumps(kept))
    return "\n".join(out) + ("\n" if raw.endswith("\n") else ""), dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", help="客户端实例目录")
    ap.add_argument("--apply", action="store_true", help="真正写盘")
    ap.add_argument("--prune-mods", action="store_true", help="删除本机已不存在的模组条目")
    ap.add_argument("--release", metavar="VERSION", help="落盘后改版本、提交、打 tag 并推送")
    args = ap.parse_args()

    inst = instance_path(args.instance)
    if not os.path.isdir(os.path.join(inst, "config")):
        raise SystemExit(f"实例目录无效: {inst}")

    # ---- mods ----
    entries, local, added, gone = diff_mods(inst)
    print(f"[mods.json] 仓库 {len(entries)} | 本机 {len(local)}")
    print(f"   + 本机新增 {len(added)}: {added or '无'}")
    print(f"   - 本机缺失 {len(gone)}: {gone or '无'}")

    new_entries, unresolved = [], []
    for name in added:
        meta = local_entry(local[name]) or modrinth_entry(local[name])
        (new_entries if meta else unresolved).append(meta or name)
    if new_entries and not args.apply:
        print(f"   已解析 {len(new_entries)} 个新模组元数据（落盘时写入）")
    if unresolved:
        print(f"   ⚠ 以下 jar Modrinth 查不到、pack/mods-local/ 里也没有，需先手工放进 mods-local: {unresolved}")

    # ---- config ----
    src, cfg_add, cfg_upd, cfg_only = diff_config(inst)
    print(f"\n[config] 新增 {len(cfg_add)} | 更新 {len(cfg_upd)} | 仓库独有（保留不删）{len(cfg_only)}")

    # ---- options.txt ----
    src_opt = os.path.join(inst, "options.txt")
    dst_opt = os.path.join(common.PACK, "options.txt")
    opt_text, opt_dropped = "", []
    if os.path.exists(src_opt):
        raw = open(src_opt, encoding="utf-8").read()
        manifest = {e["file"] for e in common.load("resourcepacks.json")}
        opt_text, opt_dropped = sanitize_options(raw, manifest)
    dst_text = open(dst_opt, encoding="utf-8").read() if os.path.exists(dst_opt) else None
    opt_changed = bool(opt_text) and opt_text != dst_text
    print(f"[options.txt] 有变化: {opt_changed}"
          + (f"（剔除私有材质包 {len(opt_dropped)} 个: {opt_dropped}）" if opt_dropped else ""))

    if not args.apply:
        print("\n（预演模式，未写入。加 --apply 执行）")
        return 0
    if unresolved:
        raise SystemExit("\n有新模组缺少元数据，先补齐再落盘（见上方 ⚠）")

    # ---- 写盘 ----
    if new_entries or (args.prune_mods and gone):
        keep = [e for e in entries if e["file"] not in (set(gone) if args.prune_mods else set())]
        keep += new_entries
        keep.sort(key=lambda e: e["file"].lower())
        common.save("mods.json", keep)
        print(f"\nmods.json: {len(entries)} -> {len(keep)}")

    for rel in cfg_add + cfg_upd:
        dest = os.path.join(common.PACK, "config", rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src[rel], dest)
    if opt_changed:
        with open(dst_opt, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(opt_text)
    print(f"config: 写入 {len(cfg_add) + len(cfg_upd)} 个文件" + ("，options.txt 已同步" if opt_changed else ""))

    if args.release:
        return release(args.release)
    return 0


def git(*cmd, check=True):
    proc = subprocess.run(["git", *cmd], cwd=common.ROOT, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(cmd)} 失败:\n{proc.stderr or proc.stdout}")
    return proc


def release(version):
    """写版本到 pack.json → 提交（提交信息带 release: x.y.z）→ 推送。

    本仓库是滚动发布：只有一个滚动 Release（tag 固定 rolling），版本以提交信息为权威，
    由 CI 用 scripts/set_version.py 落地。**不要手工打 tag**。
    """
    pack = common.load("pack.json")
    old = pack["version"]
    subprocess.run([sys.executable, os.path.join(common.ROOT, "scripts", "set_version.py"), version],
                   cwd=common.ROOT, check=True, capture_output=True)
    print(f"\npack.json: {old} -> {version}")

    git("add", "-A")
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        print("没有待提交的改动")
    else:
        git("commit", "-m", f"release: {version} 同步客户端模组与配置")
    git("push", "origin", "HEAD")
    print(f"已推送 master（提交信息含 release: {version}），Actions 构建完成后更新滚动 Release")
    return 0


if __name__ == "__main__":
    sys.exit(main())
