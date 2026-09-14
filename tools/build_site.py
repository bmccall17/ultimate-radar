"""
Builds the public GitHub Pages site into docs/.

    python -m tools.build_site

Three pages, one per possession, each a self-contained folder:

    docs/              p0001 - real tracking, real clip          (the landing page)
    docs/p0003/        p0003 - real tracking, real clip
    docs/fixture/      the synthetic fixture, invented throughout

Each folder holds index.html, possession.js and - for the real ones - clip.mp4.
The viewer normally loads data.js then live-data.js; here both tags are replaced
by one pointing at possession.js, so a folder has exactly the data it needs and
nothing 404s.

THIS PUBLISHES BROADCAST FOOTAGE. work/ is gitignored precisely because the clips
are excerpts of someone else's broadcast (docs/10-getting-the-footage.md), and
copying them under docs/ deliberately overrides that for the two possessions named
below. .gitignore carries a matching exception. Removing a possession from SITE
here, rebuilding, and deleting its folder is all it takes to unpublish one.
"""
import json, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "viewer", ROOT / "docs"
sys.path.insert(0, str(ROOT))
from tools.make_view import build as build_data

# (sub-path under docs/, work dir or None for the fixture, label)
SITE = [
    ("",        "work/p0001", "p0001 - real"),
    ("p0003",   "work/p0003", "p0003 - real"),
    ("fixture", None,         "synthetic fixture"),
]

def page(html, t0):
    """One script tag, and a sensible opening frame."""
    html, n = re.subn(r'[ \t]*<script src="(?:data|live-data)\.js"></script>\n',
                      "", html)
    if n != 2:
        sys.exit(f"expected 2 script tags in viewer/index.html, found {n}")
    shim = (
        '<script>/* Built by tools/build_site.py - do not edit docs/, edit viewer/\n'
        '   and rebuild. Opens mid-possession: frame 0 is often before the tracker\n'
        '   has seen anyone, which reads as broken rather than as honest. */\n'
        f'if(!/[#&]t=/.test(location.hash))'
        f'{{try{{history.replaceState(null,"","#t={t0:.1f}")}}catch(e){{}}}}\n'
        '</script>\n'
        '<script src="possession.js"></script>\n'
    )
    return html.replace("<script>", shim + "<script>", 1)

def opening_frame(js_path):
    """First frame where most of the roster is observed, else 0."""
    txt = js_path.read_text(encoding="utf-8")
    # make_view writes "window.POSSESSION = {", viewer/data.js writes it unspaced.
    m = re.search(r"window\.POSSESSION\s*=\s*", txt)
    if not m:
        return 0.0
    doc, _ = json.JSONDecoder().raw_decode(txt[m.end():])
    pl, fps = doc["players"], doc["possession"]["fps"]
    n = len(pl[0]["state"])
    anchored = {"observed", "confirmed"}
    for f in range(n):
        if sum(1 for p in pl if p["state"][f] in anchored) >= 0.6 * len(pl):
            return f / fps
    return 0.0

def main():
    html = (SRC / "index.html").read_text(encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    total = 0
    for sub, work, label in SITE:
        d = OUT / sub if sub else OUT
        d.mkdir(parents=True, exist_ok=True)
        if work is None:
            shutil.copy2(SRC / "data.js", d / "possession.js")
        else:
            w = ROOT / work
            if not (w / "possession.json").exists():
                sys.exit(f"{work}/possession.json missing - run the pipeline first")
            build_data(w, d / "possession.js", video="clip.mp4")
            shutil.copy2(w / "clip.mp4", d / "clip.mp4")
        (d / "index.html").write_text(page(html, opening_frame(d / "possession.js")),
                                      encoding="utf-8")
        size = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
        total += size
        print(f"  docs/{sub + '/' if sub else '':10s} {label:22s} {size/1e6:6.1f} MB")
    print(f"built docs/ - {total/1e6:.1f} MB total")
    print("check locally:  python -m http.server -d docs 8080")

if __name__ == "__main__":
    main()
