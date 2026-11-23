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


def _kv(s):
    """版本 → (数字段, 预发布串)。构建元数据（+mc26.3）不参与比较，与 Fabric 一致。"""
    s = str(s).strip().split("+")[0].rstrip("-")
    m = re.match(r"^(\d+(?:\.\d+)*)(?:-(.*))?$", s)
    if not m:
        return (0,), ""
    return tuple(int(x) for x in m.group(1).split(".")), m.group(2) or ""


def _cmp(a, b):
    (na, pa), (nb, pb) = _kv(a), _kv(b)
    n = max(len(na), len(nb))
    na, nb = na + (0,) * (n - len(na)), nb + (0,) * (n - len(nb))
    if na != nb:
        return -1 if na < nb else 1
    if pa == pb:
        return 0
    if not pa:  # 正式版 > 预发布
        return 1
    if not pb:
        return -1
    for x, y in zip(re.split(r"[.\-]", pa), re.split(r"[.\-]", pb)):
        if x == y:
            continue
        if x.isdigit() and y.isdigit():
            return -1 if int(x) < int(y) else 1
        if x.isdigit():
            return -1
        if y.isdigit():
            return 1
        return -1 if x < y else 1
    return 0


def _one(version, tok):
    if tok == "*":
        return True
    for op in (">=", "<=", ">", "<", "="):
        if tok.startswith(op):
            c = _cmp(version, tok[len(op):].strip().rstrip("-"))
            return {"<": c < 0, "<=": c <= 0, ">": c > 0, ">=": c >= 0, "=": c == 0}[op]
    if "x" in tok.lower() or "*" in tok:
        parts = re.split(r"[.\-]", tok)
        nums = _kv(version)[0]
        for i, part in enumerate(parts[:3]):
            if part.lower() in ("x", "*"):
                return True
            if part.isdigit() and (i >= len(nums) or nums[i] != int(part)):
                return False
        return True
    return _cmp(version, tok) == 0


def satisfies(version, pred):
    """按 Fabric 的版本谓词判断 version 是否落在 pred 内。

    只覆盖 breaks 里实际出现的写法（>、>=、<、<=、=、x 通配、空格并集）；
    ~ 与 ^ 记为不匹配，宁可漏报也不误报。
    """
    if pred is None or str(pred).strip() in ("", "*"):
        return True
    if isinstance(pred, list):
        return any(satisfies(version, p) for p in pred)
    return all(_one(version, tok) for tok in str(pred).split())


def audit(mods_dir):
    provided, deps, brks = {}, [], []

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
                for dep, rng in (meta.get("breaks") or {}).items():
                    brks.append((f, dep, rng))
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

    # breaks 是硬冲突：命中即 Fabric 解析阶段直接拒绝启动，比缺依赖更致命。
    conflicts = []
    for f, dep, rng in brks:
        have = provided.get(dep)
        if have is None or dep in SKIP:
            continue
        if satisfies(have, rng):
            conflicts.append((dep, rng, have, f))

    print(f"   {len(provided)} 个 mod id，{len(deps)} 条依赖声明，{len(brks)} 条 breaks 声明")
    seen = set()
    for dep, rng, f, why in problems:
        key = (dep, str(rng), why)
        if key in seen:
            continue
        seen.add(key)
        print(f"   {dep}: 需要 {rng} — {why}  ← {f}")
    seen = set()
    for dep, rng, have, f in conflicts:
        key = (dep, str(rng), have)
        if key in seen:
            continue
        seen.add(key)
        print(f"   !! {f} 声明与 {dep} {rng} 不兼容，实际装了 {have}")
    return problems, conflicts


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join("cache", "mods")
    if not os.path.isdir(target):
        print(f"目录不存在: {target}", file=sys.stderr)
        return 1
    print(f"== 依赖检查 {target} ==")
    problems, conflicts = audit(target)
    if problems or conflicts:
        print(
            f"   {len(problems)} 条依赖不满足，{len(conflicts)} 条 breaks 冲突",
            file=sys.stderr,
        )
        return 1
    print("   依赖全部满足，无 breaks 冲突")
    return 0


if __name__ == "__main__":
    sys.exit(main())
