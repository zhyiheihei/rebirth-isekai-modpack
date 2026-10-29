#!/usr/bin/env python3
"""把 local-assets 里的材质/光影对齐到上游（Modrinth）最新版。

判定不靠名字相似度：候选会真的下载下来，比较 zip 内路径集合重合度。
同一项目的相邻版本通常 >0.9；搜索误配到的别的包只有 0.0~0.4，直接丢弃。

  python3 scripts/update_assets.py            # 只报告
  python3 scripts/update_assets.py --apply    # 替换文件、补 mcmeta、更新清单与 options.txt
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile

import common

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "rebirth-isekai-modpack (asset realign)"
API = "https://api.modrinth.com/v2"
STAGE = os.path.join(ROOT, "cache", "asset-updates")
BACKUP = os.path.join(ROOT, "cache", "asset-old")
KINDS = {"resourcepacks": "resourcepack", "shaderpacks": "shader"}
MIN_OVERLAP = 0.55
TARGET_MC = json.load(open(os.path.join(ROOT, "pack", "pack.json"), encoding="utf-8"))["minecraft"]
TARGET_LINE = ".".join(TARGET_MC.split(".")[:2])          # 26.1.2 -> "26.1"

# 结构重排导致路径重合度偏低、但作者与 pack.mcmeta 能证明是同一上游的
FORCE = {
    "FreshAnimations_v1.9.2.zip": "fresh-animations",
    "Os' Colorful Grasses (Mix).zip": "os-colorful-grasses",
}
# 上游已不再分发合并 zip（改用 EuphoriaPatcher 模组运行期打补丁），这两个合并包没有可更新对象
SKIP = {
    "ComplementaryUnbound_r5.7.1 + EuphoriaPatches_1.8.1.zip": "Euphoria 合并包，上游已改为模组形式",
    "ComplementaryReimagined_r5.7.1 + EuphoriaPatches_1.8.1.zip": "Euphoria 合并包，上游已改为模组形式",
}
# 内容已按 26.x 的要求重建过，不能拿上游原始 zip 覆盖（上游那个是条目重叠的畸形包）
PINNED = {
    "xali's Enhanced Vanilla -1.11.2b-rev.54d51d4.zip": "上游原始 zip 条目重叠，本地是 26.x 可用的重建副本",
}
# 同一项目有多个变体时，只换同名变体
VARIANT = {"Os' Colorful Grasses (Mix).zip": "Mix-26.3"}


def api(path, **params):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def norm(text):
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"\.(zip|jar)$", "", text.lower())
    text = re.sub(r"[_\-\[\](){}§]", " ", text)
    return " ".join(re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text).split())


def clean_query(name):
    base = norm(name)
    ascii_part = " ".join(w for w in base.split() if w.isascii() and len(w) > 1)
    if len(ascii_part.split()) >= 2:
        base = ascii_part
    base = re.sub(r"\b(v|rev|mc|r|d|e)?\s*\d+([ .]\d+)*[a-z]?\b", " ", base)
    noise = {"zip", "edit", "fabric", "forge", "for", "the", "and", "with", "x", "v"}
    return " ".join(w for w in base.split() if w not in noise and len(w) > 1) or base


def search(name, want_type):
    words = clean_query(name).split()
    hits = []
    for cut in range(len(words), 0, -1):
        hits = api("/search", query=" ".join(words[:cut]), limit=10).get("hits") or []
        if hits:
            break
    tokens = set(" ".join(words).split())
    scored = []
    for h in hits:
        pid = h.get("project_id") or h.get("id")
        try:
            proj = api(f"/project/{pid}")
        except Exception:
            continue
        if proj.get("project_type") != want_type:
            continue
        cand = set(norm(proj["slug"]).split()) | set(norm(proj["title"]).split())
        overlap = len(tokens & cand) / max(1, len(tokens))
        if norm(proj["slug"]) in norm(name) or norm(proj["title"]) in norm(name):
            overlap = max(overlap, 0.95)
        scored.append((overlap, proj))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 0.6:
        return None
    return scored[0][1]


def latest_version(project, prefer_variant=None):
    """优先选声明支持目标版本（26.1.2）的最新版；没有才退回 26.1 线，再没有才取最新。

    这样不会因为「上游发了只支持 26.2/26.3 的新版」把整包拽离 26.1。
    """
    versions = api(f"/project/{project['id']}/version")
    if prefer_variant:
        versions = [v for v in versions if v["version_number"] == prefer_variant] or versions
    if not versions:
        return None

    def key(v):
        gv = v.get("game_versions") or []
        return (TARGET_MC in gv, any(g.startswith(TARGET_LINE) for g in gv), v.get("date_published") or "")

    return sorted(versions, key=key, reverse=True)[0]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def zip_paths(path):
    with zipfile.ZipFile(path) as z:
        return {n.lower() for n in z.namelist() if not n.endswith("/")}


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def patch_mcmeta(path):
    """按 26.1 pack format 规范转换版本范围，保留旧版兼容字段的正确格式。"""
    tmp = path + ".tmp"
    changed = common.normalize_resourcepack(path, tmp)
    if changed:
        os.replace(tmp, path)
    else:
        os.remove(tmp)
    return changed


def plan():
    """返回 [(kind, 旧文件, 上游项目, 版本信息, 新文件名)]，只含已验明正身的。"""
    items = []
    for sub, ptype in KINDS.items():
        folder = os.path.join(ROOT, "local-assets", sub)
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".zip"):
                continue
            if fn in SKIP:
                print(f"· {fn}: {SKIP[fn]}，保留")
                continue
            if fn in PINNED:
                print(f"· {fn}: {PINNED[fn]}，保留")
                continue
            old_path = os.path.join(folder, fn)
            forced = fn in FORCE
            proj = api(f"/project/{FORCE[fn]}") if forced else search(fn, ptype)
            if not proj:
                print(f"· {fn}: Modrinth 上没有匹配项目，保持原样")
                continue
            ver = latest_version(proj, VARIANT.get(fn))
            if not ver:
                continue
            f = ([x for x in ver["files"] if x.get("primary")] or ver["files"])[0]
            staged = os.path.join(STAGE, proj["slug"] + "-" + f["filename"])
            if not os.path.exists(staged):
                download(f["url"], staged)
            same = sha256(staged) == sha256(old_path)
            try:
                overlap = len(zip_paths(staged) & zip_paths(old_path)) / max(1, len(zip_paths(staged) | zip_paths(old_path)))
            except Exception as exc:
                print(f"· {fn}: zip 读取失败（{type(exc).__name__}），跳过")
                continue
            if same or overlap >= MIN_OVERLAP or forced:
                flag = "同版本" if same else f"重合 {overlap:.2f}"
                print(f"✔ {fn}\n    -> {f['filename']}  ({proj['slug']} {ver['version_number']}, "
                      f"{(ver.get('date_published') or '')[:10]}, {flag})")
                items.append({"kind": sub, "old": fn, "project": proj["slug"],
                              "version": ver["version_number"], "filename": f["filename"],
                              "published": (ver.get("date_published") or "")[:10],
                              "game_versions": ver.get("game_versions") or [],
                              "staged": staged, "same": same})
            else:
                print(f"✘ {fn}: 候选 {proj['slug']} 重合度只有 {overlap:.2f}，判定为不同项目")
    return items


def apply(items):
    os.makedirs(BACKUP, exist_ok=True)
    mapping = {}
    for it in items:
        if it["same"]:
            continue
        src = os.path.join(ROOT, "local-assets", it["kind"], it["old"])
        dst = os.path.join(ROOT, "local-assets", it["kind"], it["filename"])
        shutil.move(src, os.path.join(BACKUP, it["kind"] + "__" + it["old"]))
        shutil.copy2(it["staged"], dst)
        if it["kind"] == "resourcepacks":
            patch_mcmeta(dst)
            mapping[it["old"]] = it["filename"]
    for sub, name in (("resourcepacks", "resourcepacks.json"), ("shaderpacks", "shaderpacks.json")):
        folder = os.path.join(ROOT, "local-assets", sub)
        rows = [{"file": fn, "sha256": sha256(os.path.join(folder, fn)),
                 "size": os.path.getsize(os.path.join(folder, fn)), "source": "local"}
                for fn in sorted(os.listdir(folder)) if fn.endswith(".zip")]
        with open(os.path.join(ROOT, "pack", name), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
            f.write("\n")
    opts = os.path.join(ROOT, "pack", "options.txt")
    lines = open(opts, encoding="utf-8").read().splitlines()
    out = []
    for ln in lines:
        if ln.startswith("resourcePacks:["):
            for old, new in mapping.items():
                ln = ln.replace(old, new)
        out.append(ln)
    open(opts, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"\n落地 {len([i for i in items if not i['same']])} 个；原件备份在 {BACKUP}")


def main():
    items = plan()
    if "--apply" in sys.argv:
        apply(items)
    else:
        print(f"\n共 {len(items)} 个可对齐（加 --apply 落地）")


if __name__ == "__main__":
    main()
