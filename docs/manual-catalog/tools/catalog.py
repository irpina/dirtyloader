#!/usr/bin/env python3
"""Manual catalog kit: one tool for every device's pass (see ../README.md).

    python3 catalog.py devices                    the devices, their manuals, where each pass stands
    python3 catalog.py text <dev>|all             manual PDF -> text/<dev>.txt (pdftotext -layout)
    python3 catalog.py toc <dev> [--split N]      numbered headings with line numbers (N: propose N parts)
    python3 catalog.py parts <dev>                check devices.json's parts: sizes, overlaps, lines not read
    python3 catalog.py baseline list              device ids in the release and the mods that carry events
    python3 catalog.py baseline <dev>             the release's READMEs + its event names -> <dev>/baseline/
    python3 catalog.py brief <dev>                each reader's whole prompt -> <dev>/prompts/<part>.md
    python3 catalog.py merge <dev>                <dev>/<part>.md -> <dev>/merged.json, and the rows to fix
    python3 catalog.py stats <dev> [<dev>...]     area x coverage (markdown), <dev>/stats.json, chart rows
    python3 catalog.py compare <dev> <dev>        manual sections both devices have, each side's coverage

text and baseline need WSL (pdftotext, the elekloader tree); the rest is plain Python 3 anywhere.
Standard library only. Paths in generated prompts are Windows paths, for the readers' Read/Write tools.

dirtyloader copy (2026-11-13): taken from the Elekloader manual-catalog kit unchanged except that the
manual text lives in the repo's gitignored manuals/ folder (manuals/<dev>.txt), never committed. The M8
manual has no numbered headings, so its parts give explicit "ranges"; `toc`/`parts` (heading-based) and
`baseline` (Elektron release tree) do not apply to it. `brief`, `merge` and `stats` work as-is.
"""
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
ROOT = KIT.parent.parent
MANUALS = ROOT / "manuals"
CFG = json.loads((KIT / "devices.json").read_text(encoding="utf-8"))
VOCAB = json.loads((KIT / "vocab.json").read_text(encoding="utf-8"))
LAYERS = {l["slug"]: l["label"] for l in VOCAB["layers"]}
ALIAS = VOCAB.get("layer_aliases", {})
COVS = VOCAB["coverage"]          # full, partial, raw-only, none
KINDS = set(VOCAB["kinds"])


def dev(slug):
    if slug not in CFG["devices"]:
        sys.exit(f"unknown device {slug!r}; known: {' '.join(CFG['devices'])}")
    return CFG["devices"][slug]


def ddir(slug):
    d = dev(slug)
    p = (KIT / d["dir"]).resolve() if d.get("dir") else KIT / slug
    p.mkdir(parents=True, exist_ok=True)
    return p


def winpath(p):
    s = str(p)
    m = re.match(r"^/mnt/([a-z])/(.*)$", s)
    return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\") if m else s


def text_path(slug):
    return MANUALS / f"{slug}.txt"   # gitignored: the manufacturer's text stays local


# ---------------------------------------------------------------- devices
def cmd_devices(_):
    for slug, d in CFG["devices"].items():
        parts = d.get("parts") or {}
        dd = (KIT / d["dir"]).resolve() if d.get("dir") else KIT / slug
        done = [p for p in parts if (dd / f"{p}.md").exists()]
        merged = dd / "merged.json"
        n = len(json.loads(merged.read_text(encoding="utf-8"))["rows"]) if merged.exists() else None
        state = (f"{n} targets" if n is not None else
                 f"readers {len(done)}/{len(parts)}" if parts else "no parts yet")
        print(f"{slug:4} {d['name']:18} OS {d['os']:6} text {'yes' if text_path(slug).exists() else 'no ':3} "
              f"{state:16} {d['manual']}")


# ---------------------------------------------------------------- text
def cmd_text(args):
    slugs = list(CFG["devices"]) if args[0] == "all" else args
    (KIT / "text").mkdir(exist_ok=True)
    for s in slugs:
        pdf = MANUALS / dev(s)["manual"]
        out = text_path(s)
        subprocess.run(["pdftotext", "-layout", str(pdf), str(out)], check=True)
        print(f"{s}: {sum(1 for _ in out.open(encoding='utf-8', errors='replace'))} lines -> {out}")


# ---------------------------------------------------------------- toc
HEAD = re.compile(r"^\s{0,12}((?:\d{1,2}(?:\.\d{1,2}){0,3}\.?)|(?:APPENDIX [A-Z]:?)|(?:[A-H]\.\d{1,2}(?:\.\d{1,2})?))"
                  r"\s+([A-Z0-9\[<+][A-Z0-9 ,:;&/+\-()\[\]<>’'!.#*]{2,})$")


def headings(slug):
    """-> [(line, number, title)] of the body's numbered headings, each once (page headers repeat them)."""
    out, seen, expect, in_app = [], set(), 1, False
    # split on "\n" only: str.splitlines() also splits on the form feed between pages, and the line numbers
    # must be the ones the Read tool and grep count
    for i, line in enumerate(text_path(slug).read_text(encoding="utf-8", errors="replace").split("\n"), 1):
        if ". . ." in line or "....." in line:
            continue                                   # contents pages
        m = HEAD.match(line.rstrip())
        if not m:
            continue
        num, title = m.group(1).rstrip(".:"), m.group(2).strip()
        if sum(c.isalpha() for c in title) < 3 or title != title.upper():
            continue
        key = (num, title)
        if key in seen:
            continue
        if num.startswith("APPENDIX"):
            in_app = True
        elif "." not in num:                           # a chapter: they come in order, 1, 2, 3...
            if in_app or not expect <= int(num) <= expect + 2:   # drops figure labels ("24 FUNC", "12 V DC");
                continue                                         # a heading the text lost may be skipped
            expect = int(num) + 1
        seen.add(key)
        out.append((i, num, title))
    return out


def cmd_toc(args):
    slug = args[0]
    hs = headings(slug)
    total = n_lines(slug)
    if "--split" not in args:
        for line, num, title in hs:
            depth = 0 if num.startswith("APPENDIX") else num.count(".")
            print(f"{line:6}  {'  ' * depth}{num} {title}")
        print(f"{total:6}  (end)")
        return
    n = int(args[args.index("--split") + 1])
    tops = [(l, num, t) for l, num, t in hs if num.startswith("APPENDIX") or "." not in num]
    chunks = [(l, (tops[i + 1][0] - 1 if i + 1 < len(tops) else total), f"{num} {t}") for i, (l, num, t) in enumerate(tops)]
    body = sum(b - a + 1 for a, b, _ in chunks)
    target, groups, cur, size = body / n, [], [], 0
    for c in chunks:
        if cur and size + (c[1] - c[0] + 1) / 2 > target and len(groups) < n - 1:
            groups.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += c[1] - c[0] + 1
    groups.append(cur)
    print(f"# {slug}: {len(tops)} chapters, {body} body lines, about {round(target)} per part. A starting point only:")
    print("# group by topic (appendices belong with the chapter they detail), then put the ranges in devices.json.")
    for g, name in zip(groups, "ABCDEFGH"):
        print(f"{name}: lines {g[0][0]}-{g[-1][1]} ({sum(b - a + 1 for a, b, _ in g)} lines)")
        for a, b, t in g:
            print(f"     {a:5}-{b:<5} {t}")


def n_lines(slug):
    return text_path(slug).read_text(encoding="utf-8", errors="replace").count("\n") + 1


def ranges(slug, p):
    """A part's [first line, last line, what] list: its own "ranges", or made from its "chapters"
    (["1-8", "17-18", "D"]: chapter numbers and appendix letters, each to the line before the next chapter)."""
    if p.get("ranges"):
        return p["ranges"]
    tops = [(l, (num.split()[1] if num.startswith("APPENDIX") else int(num)), f"{num} {t}")
            for l, num, t in headings(slug) if num.startswith("APPENDIX") or "." not in num]
    keys = [k for _, k, _ in tops]
    out = []
    for item in p.get("chapters", []):
        a, _, b = item.partition("-")
        a, b = (int(a), int(b or a)) if a.isdigit() else (a, b or a)
        if a not in keys or b not in keys:
            sys.exit(f"{slug}: no heading found for chapter {a if a not in keys else b} (see `toc {slug}`); "
                     f"give that part explicit \"ranges\" instead")
        i, j = keys.index(a), keys.index(b)
        end = tops[j + 1][0] - 1 if j + 1 < len(tops) else n_lines(slug)
        out.append([tops[i][0], end, "; ".join(t.title() for _, _, t in tops[i:j + 1])])
    return out


def cmd_parts(args):
    """Check a device's parts: each one's size, overlaps, and body lines no part reads."""
    slug = args[0]
    d = dev(slug)
    hs = headings(slug)
    total = n_lines(slug)
    spans = sorted((a, b, part) for part, p in d.get("parts", {}).items() for a, b, _ in ranges(slug, p))
    if not spans:
        sys.exit(f"{slug}: no parts with ranges or chapters in devices.json")
    for part, p in d["parts"].items():
        rs = ranges(slug, p)
        print(f"{part}: {sum(b - a + 1 for a, b, _ in rs):5} lines  {p['lens']:9} {p['title']}: "
              + ", ".join(f"{a}-{b}" for a, b, _ in rs))
    last = hs[0][0] - 1
    for a, b, part in spans:
        if a <= last:
            print(f"OVERLAP: {part} starts at {a}, before {last} ends")
        if a - last - 1 >= 15:
            inside = [f"{num} {t}" for l, num, t in hs if last < l < a]
            print(f"not read: lines {last + 1}-{a - 1} ({a - last - 1}): {'; '.join(inside[:6]) or 'no headings'}")
        if b > total:
            print(f"PAST THE END: {part} ends at {b}, the text has {total} lines")
        last = max(last, b)
    if total - last >= 15:
        print(f"not read: lines {last + 1}-{total} ({total - last})")


# ---------------------------------------------------------------- baseline
def git(*a):
    r = CFG["release"]
    return subprocess.run(["git", "-C", r["tree"], *a], capture_output=True, text=True, check=True).stdout


def release_mods():
    tag = CFG["release"]["tag"]
    for name in git("ls-tree", "--name-only", f"{tag}:mods").split():
        try:
            m = json.loads(git("show", f"{tag}:mods/{name}/mod.json"))
        except (subprocess.CalledProcessError, ValueError):
            continue
        yield name, m


def cmd_baseline(args):
    tag = CFG["release"]["tag"]
    if args[0] == "list":
        by = defaultdict(list)
        for name, m in release_mods():
            if m.get("collections"):
                by[m.get("device", "?")].append(f"{name} {m.get('version')} ({len(m['collections'])})")
        for d, mods in sorted(by.items()):
            print(f"{d}:\n   " + "\n   ".join(mods))
        return
    slug = args[0]
    d = dev(slug)
    out = ddir(slug) / "baseline"
    out.mkdir(exist_ok=True)
    lines = [f"# Events and tables in elekloader {tag} for the {d['name']} ({d['device']})", "",
             "Generated by `catalog.py baseline`. Names only: what each one does is in the READMEs beside this file",
             "and, condensed for the readers, in ../baseline.md (written by hand from them).", "",
             "| mod | version | OS (ports) | events and tables other mods use |", "|---|---|---|---|"]
    for name, m in release_mods():
        if m.get("device") != d["device"] or not m.get("collections"):
            continue
        ports = ", ".join((m.get("ports") or {}).keys()) if isinstance(m.get("ports"), dict) else ""
        lines.append(f"| {name} | {m.get('version')} | {m.get('os')}{' (' + ports + ')' if ports else ''} | "
                     f"{' '.join(m['collections'])} |")
        try:
            (out / f"{name}-{m.get('version')}.README.md").write_text(
                git("show", f"{tag}:mods/{name}/README.md"), encoding="utf-8")
        except subprocess.CalledProcessError:
            pass
        print(f"{name} {m.get('version')}: {len(m['collections'])} events/tables")
    (out / "events.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", out)


# ---------------------------------------------------------------- brief
def cmd_brief(args):
    slug = args[0]
    d = dev(slug)
    out = ddir(slug)
    (out / "prompts").mkdir(exist_ok=True)
    tpl = (KIT / "BRIEF.md").read_text(encoding="utf-8")
    tpl = tpl.split("<!-- TEMPLATE -->", 1)[1]
    total = n_lines(slug)
    layers = "\n".join(f"  - `{l['slug']}`: {l['what']}" for l in VOCAB["layers"]
                       if not l.get("devices") or slug in l["devices"])
    for part, p in d["parts"].items():
        p = dict(p, ranges=ranges(slug, p))
        range_text = "\n".join(f"- lines {a}-{b}: {what}" for a, b, what in p["ranges"])
        others = "; ".join(f"{k} = {v['title']}" for k, v in d["parts"].items() if k != part)
        lens = VOCAB["lenses"][p["lens"]] + (" " + p["focus"] if p.get("focus") else "")
        txt = tpl
        for k, v in {"device_name": d["name"], "os": d["os"], "part": part, "part_title": p["title"],
                     "covers": p["covers"], "text_path": winpath(text_path(slug)), "n_lines": str(total),
                     "ranges": range_text, "others": others, "lens": lens, "layers": layers,
                     "baseline_path": winpath(out / "baseline.md"), "out_path": winpath(out / f"{part}.md"),
                     "release": CFG["release"]["tag"], "device_notes": d.get("notes", "")}.items():
            txt = txt.replace("{" + k + "}", v)
        f = out / "prompts" / f"{part}.md"
        f.write_text(txt.strip() + "\n", encoding="utf-8")
        print(f"{part}: {sum(b - a + 1 for a, b, _ in p['ranges'])} manual lines -> {winpath(f)}")


# ---------------------------------------------------------------- merge
def cov_class(text):
    t = text.strip().lower().lstrip("*_` ")
    for k in ("raw-only", "raw only", "full", "partial", "none"):
        if t.startswith(k):
            return k.replace(" ", "-")
    if "raw-only" in t or "raw only" in t:
        return "raw-only"
    if t.startswith("n/a") or t.startswith("—") or t.startswith("-"):
        return "none"
    return "partial" if "partial" in t else ("none" if "none" in t else "other")


def layer_slug(raw):
    """The first layer a reader named, as a vocabulary slug ('' if it is not one)."""
    raw = raw.strip().strip("*`").lower()
    known = set(LAYERS) | set(ALIAS)
    first = re.split(r"[ /,;(]+(?=[a-z])", raw.replace(" / ", ";"))[0].split(";")[0].strip()
    if first not in known:
        first = raw.split(";")[0].split(" / ")[0].strip()
    if first not in known:
        first = first.split("/")[0]
    first = ALIAS.get(first, first)
    return first if first in LAYERS else ""


def cells(line):
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") else s
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def parse(slug):
    d = dev(slug)
    src = ddir(slug)
    strict = not d.get("legacy")
    rows, prims, problems = [], {}, []
    for part in d["parts"]:
        p = src / f"{part}.md"
        if not p.exists():
            problems.append(f"{part}.md: missing")
            continue
        section, in_prims, header, n = "", False, None, 0
        for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            h = re.match(r"^(#{1,4})\s+(.*)", line)
            if h:
                title = h.group(2).strip()
                in_prims = "cross-cutting" in title.lower() or "primitive" in title.lower()
                if not in_prims:
                    section = title
                header = None
                continue
            if in_prims:
                prims.setdefault(part, []).append(line)
                continue
            if not line.strip().startswith("|"):
                continue
            c = cells(line)
            if all(re.fullmatch(r":?-{2,}:?", x or "--") for x in c):
                continue
            if header is None or (c and c[0].lower().startswith("hook target")):
                header = [x.lower() for x in c]
                continue
            where = f"{part}.md:{ln}"
            if len(c) != 5 and strict:
                problems.append(f"{where}: {len(c)} cells (an unescaped | ?)")
            c += [""] * (5 - len(c))
            target = re.sub(r"^[A-H]\d{3}\s+", "", c[0])
            lay, cov = layer_slug(c[2]), cov_class(c[3])
            if not lay:
                problems.append(f"{where}: layer {c[2]!r} is not in vocab.json")
            elif strict and c[2].strip().strip("`*").lower() != lay:
                problems.append(f"{where}: layer cell {c[2]!r} should be exactly `{lay}`")
            if cov == "other" or (strict and not c[3].strip().lower().startswith(tuple(COVS))):
                problems.append(f"{where}: coverage {c[3][:40]!r} does not start with full/partial/raw-only/none")
            if strict:
                bad = [k for k in re.split(r"\s*/\s*", c[1].lower()) if k and k not in KINDS]
                if bad:
                    problems.append(f"{where}: kind {', '.join(bad)!r} is not in vocab.json")
            n += 1
            rows.append({"id": f"{part}{n:03d}", "part": part, "section": section, "target": target,
                         "kind": c[1], "layer": LAYERS.get(lay, "Other"), "layer_slug": lay or "other",
                         "layer_raw": c[2], "coverage": c[3], "cov": cov if cov != "other" else "none",
                         "examples": " | ".join(c[4:]).strip(" |")})
    return rows, prims, problems


def cmd_merge(args):
    slug = args[0]
    d = dev(slug)
    rows, prims, problems = parse(slug)
    out = ddir(slug) / ("merged.json" if not d.get("legacy") else "merged.kit.json")
    out.write_text(json.dumps({"device": slug, "name": d["name"], "os": d["os"],
                               "rated": d.get("rated"), "parts": {k: v["title"] for k, v in d["parts"].items()},
                               "rows": rows, "primitives": {k: "\n".join(v).strip() for k, v in prims.items()}},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{slug}: {len(rows)} rows -> {out}")
    print("by part    ", dict(Counter(r["part"] for r in rows)))
    print("by coverage", dict(Counter(r["cov"] for r in rows)))
    if problems:
        print(f"\n{len(problems)} problems (fix the reader files, then merge again):")
        for p in problems[:200]:
            print("  ", p)
    return rows


# ---------------------------------------------------------------- stats
def table(rows):
    by = defaultdict(Counter)
    for r in rows:
        by[r["layer"]][r["cov"]] += 1
    order = [l["label"] for l in VOCAB["layers"]] + ["Other"]
    return [(lab, sum(by[lab].values()), *[by[lab][c] for c in COVS]) for lab in order if by.get(lab)]


def cmd_stats(args):
    chart = "--chart" in args
    all_t = {}
    for slug in [a for a in args if not a.startswith("--")]:
        d = dev(slug)
        rows, _, _ = parse(slug)
        t = table(rows)
        all_t[slug] = t
        tot = Counter(r["cov"] for r in rows)
        n = len(rows) or 1
        print(f"\n## {d['name']} (manual OS {d['os']}; rated against {(d.get('rated') or {}).get('against', '?')})\n")
        print(f"{len(rows)} targets: " + ", ".join(f"{c} {tot[c]} ({round(100 * tot[c] / n)}%)" for c in COVS) + "\n")
        print("| area | targets | " + " | ".join(COVS) + " |\n|---|---|" + "---|" * len(COVS))
        for lab, total, *cs in t:
            print(f"| {lab} | {total} | " + " | ".join(str(c) for c in cs) + " |")
        json.dump({"device": slug, "total": len(rows), "cov": dict(tot),
                   "layers": {lab: dict(zip(COVS, cs)) for lab, _, *cs in t}},
                  open(ddir(slug) / "stats.json", "w", encoding="utf-8"), indent=1)
        if chart:
            names = {"full": "Full", "partial": "Partial", "raw-only": "Raw-only", "none": "No hook"}
            print("\nchart rows (long format):")
            print(json.dumps([{"area": lab, "cov": names[c], "n": v} for lab, _, *cs in t for c, v in zip(COVS, cs)],
                             ensure_ascii=False))
    if len(all_t) > 1:
        slugs = list(all_t)
        print("\n## Side by side (targets, and the share with no hook)\n")
        print("| area | " + " | ".join(f"{s} targets | {s} no hook" for s in slugs) + " |")
        print("|---|" + "---|---|" * len(slugs))
        for lab in [l["label"] for l in VOCAB["layers"]]:
            cs = [next((r for r in all_t[s] if r[0] == lab), None) for s in slugs]
            if any(cs):
                print(f"| {lab} | " + " | ".join(
                    (f"{c[1]} | {round(100 * c[5] / c[1])}%" if c else "- | -") for c in cs) + " |")


# ---------------------------------------------------------------- compare
def sec_key(title, names):
    t = re.sub(r"^\s*(appendix\s+[a-h]:?|[a-h]\.\d+(\.\d+)*|\d+(\.\d+)*\.?)\s*", "", title.strip(), flags=re.I)
    t = t.upper()
    for n in names:
        t = t.replace(n.upper(), "DEVICE")
    return re.sub(r"[^A-Z0-9]+", " ", t).strip()


def cmd_compare(args):
    a, b = args[:2]
    names = sorted({w for s in (a, b) for w in dev(s)["name"].replace(" mk1", "").replace(" MKII", "").split()
                    if len(w) > 3}, key=len, reverse=True)
    sides = {}
    for s in (a, b):
        by = defaultdict(list)
        for r in parse(s)[0]:
            by[sec_key(r["section"], names)].append(r)
        sides[s] = by
    shared = sorted(set(sides[a]) & set(sides[b]))

    def cnt(rows):
        c = Counter(r["cov"] for r in rows)
        return f"{len(rows)} ({c['full']}/{c['partial']}/{c['raw-only']}/{c['none']})"
    print(f"Sections matched by title (numbering and the device's name ignored): {len(shared)} shared, "
          f"{len(sides[a]) - len(shared)} only {a}, {len(sides[b]) - len(shared)} only {b}.")
    for s in (a, b):
        rows = [r for k in shared for r in sides[s][k]]
        print(f"  {s} in shared sections: {cnt(rows)} of {sum(len(v) for v in sides[s].values())} targets "
              f"(targets (full/partial/raw-only/none))")
    print(f"\n| section | {a} | {b} |\n|---|---|---|")
    for k in shared:
        print(f"| {k.title()} | {cnt(sides[a][k])} | {cnt(sides[b][k])} |")
    for s in (a, b):
        only = sorted(set(sides[s]) - set(shared), key=lambda k: -len(sides[s][k]))
        print(f"\nOnly {s} ({sum(len(sides[s][k]) for k in only)} targets): " +
              "; ".join(f"{k.title()} {len(sides[s][k])}" for k in only))


if __name__ == "__main__":
    cmds = {"devices": cmd_devices, "text": cmd_text, "toc": cmd_toc, "parts": cmd_parts, "baseline": cmd_baseline,
            "brief": cmd_brief, "merge": cmd_merge, "stats": cmd_stats, "compare": cmd_compare}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])
