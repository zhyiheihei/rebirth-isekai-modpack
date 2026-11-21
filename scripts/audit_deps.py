#!/usr/bin/env python3
"""检查一组 Fabric mod jar 的依赖是否齐全（只读 fabric.mod.json，不启动游戏）。

  python3 scripts/audit_deps.py            # 默认查 cache/mods
  python3 scripts/audit_deps.py <目录>

判定口径：顶层 id、provides、以及 META-INF/jars/ 里的内嵌 jar 都算「已提供」，
同一个 id 有多个提供者时取最高版本（与 Fabric 实际解析一致）。
"""
import io
import json
import os
import re
import sys
import zipfile

SKIP = {"minecraft", "java", "fabricloader", "fabric", "fabric-api"}


def read_meta(zf):
    try:
        raw = zf.read("fabric.mod.json").decode("utf-8", "replace")
    except KeyError:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(re.sub(r"[\x00-\x1f]", " ", raw))


def ver(s):
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", str(s))
    return tuple(int(x) for x in m.groups(default="0")) if m else (0,)


def audit(mods_dir):
    provided, deps = {}, []

    def add(mid, v):
        if mid and (mid not in provided or ver(v) > ver(provided[mid])):
            provided[mid] = str(v)

    for f in sorted(os.listdir(mods_dir)):
        if not f.endswith(".jar"):
            continue
        try:
            zf = zipfile.ZipFile(os.path.join(mods_dir, f))
        except Exception as exc:
            print(f"   读不了 {f}: {exc}", file=sys.stderr)
            continue
        with zf:
            meta = read_meta(zf)
            if meta:
                add(meta.get("id"), meta.get("version"))
                for p in meta.get("provides") or []:
                    add(p, meta.get("version"))
                for dep, rng in (meta.get("depends") or {}).items():
                    deps.append((f, dep, rng))
            for name in zf.namelist():
                if not (name.startswith("META-INF/jars/") and name.endswith(".jar")):
                    continue
                try:
                    inner = zipfile.ZipFile(io.BytesIO(zf.read(name)))
                except Exception:
                    continue
                with inner:
                    im = read_meta(inner)
                    if im:
                        add(im.get("id"), im.get("version"))
                        for p in im.get("provides") or []:
                            add(p, im.get("version"))

    problems = []
    for f, dep, rng in deps:
        if dep in SKIP:
            continue
        if dep not in provided:
            problems.append((dep, rng, f, "缺失"))
            continue
        for r in rng if isinstance(rng, list) else [rng]:
            if not isinstance(r, str):
                continue
            m = re.match(r">=\s*([0-9][^\s]*)", r)
            if m and ver(provided[dep]) < ver(m.group(1)):
                problems.append((dep, r, f, f"版本过低({provided[dep]})"))

    print(f"   {len(provided)} 个 mod id，{len(deps)} 条依赖声明")
    seen = set()
    for dep, rng, f, why in problems:
        key = (dep, str(rng), why)
        if key in seen:
            continue
        seen.add(key)
        print(f"   {dep}: 需要 {rng} — {why}  ← {f}")
    return problems


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join("cache", "mods")
    if not os.path.isdir(target):
        print(f"目录不存在: {target}", file=sys.stderr)
        return 1
    print(f"== 依赖检查 {target} ==")
    problems = audit(target)
    if problems:
        print(f"   {len(problems)} 条依赖不满足", file=sys.stderr)
        return 1
    print("   依赖全部满足")
    return 0


if __name__ == "__main__":
    sys.exit(main())
