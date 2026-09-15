"""
Builds the public GitHub Pages site into docs/.

    python -m tools.build_site

Three pages, one per possession, each a self-contained folder:

    docs/              p0001 - real tracking, real clip          (the landing page)
    docs/p0002/        p0002 - real tracking, real clip
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

# (sub-path under docs/, work dir or None for the fixture, label, nav name)
#
# `nav` is what the switcher in the header shows. Every page carries links to
# every other one: the pages were built as separate folders from the first
# version and nothing ever linked them, so the only way to reach p0002 or the
# fixture was to know the URL and type it. A published page nobody can navigate
# to is not published.
SITE = [
    ("",        "work/p0001", "p0001 - real",      "p0001"),
    # p0002 was published here and has been removed: it ran from an out-of-bounds
    # pull to the brick mark with no play in it. Deleting a row is how a
    # possession is unpublished - delete the row, rebuild, and remove its folder.
    ("p0003",   "work/p0003", "p0003 - real",      "p0003"),
    ("p0004",   "work/p0004", "p0004 - real",      "p0004"),
    ("p0005",   "work/p0005", "p0005 - real",      "p0005"),
    ("p0009",   "work/p0009", "p0009 - real",      "p0009"),
    ("p0015",   "work/p0015", "p0015 - real",      "p0015"),
    # p0006, p0007, p0008 and p0010 were cut, calibrated, detected and tracked,
    # and are not here. All pass M1 acceptance, and all pass it on a quarter to
    # a half of their frames, because the camera spends the rest of each
    # possession where the halfway line is out of shot. The mosaic recovers some
    # of that and not enough: median roster coverage is still 0 of 14 in all
    # four. Publishing a page that is blank for half its scrub bar is not
    # publishing a possession. See docs/29-scouting-possessions.md.
    # The synthetic fixture was published here too and has been removed. It still
    # exists and still matters - `fixtures/possession_demo.json` is the only
    # ground truth in the project and viewer/data.js renders it standalone - but
    # it is a development target, not something a coach should be offered
    # alongside real footage. Keeping it in the switcher invited exactly that
    # confusion.
]

def nav_html(current_sub: str) -> str:
    """Links to every published page, relative so it works from any depth.

    Kept out of viewer/index.html deliberately: the viewer has to open from
    file:// against a single possession.json with no siblings (AD-9), and it
    cannot know what else a site happens to publish. The site does, so the site
    injects it.
    """
    depth = 1 if current_sub else 0
    items = []
    for sub, _, _, name in SITE:
        href = ("../" * depth + f"{sub}/") if sub else ("../" if depth else "./")
        if sub == current_sub:
            items.append(f'<span class="navhere" aria-current="page">{name}</span>')
        else:
            items.append(f'<a class="navlink" href="{href}">{name}</a>')
    return ('<nav class="switch" aria-label="possession">'
            + '<span class="navlabel">possession</span>' + "".join(items)
            + "</nav>")


NAV_CSS = """
.switch{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap}
.navlabel{color:var(--dim);font-size:11px;text-transform:uppercase;
  letter-spacing:.06em;margin-right:2px}
.navlink,.navhere{font:inherit;font-size:13px;border-radius:6px;padding:4px 9px;
  border:1px solid var(--line);text-decoration:none;color:var(--ink)}
.navlink:hover{border-color:var(--dim)}
.navhere{background:var(--chill-fill);border-color:var(--chill);cursor:default}
"""


def page(html, t0, current_sub=""):
    """One script tag, a sensible opening frame, and the possession switcher."""
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
    html = html.replace("</style>", NAV_CSS + "</style>", 1)
    html = html.replace('<div class="spacer"></div>',
                        nav_html(current_sub) + '<div class="spacer"></div>', 1)
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
    anchored = {"observed", "confirmed", "provisional", "weak"}
    for f in range(n):
        if sum(1 for p in pl if p["state"][f] in anchored) >= 0.6 * len(pl):
            return f / fps
    return 0.0

def main():
    html = (SRC / "index.html").read_text(encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    total = 0
    for sub, work, label, _name in SITE:
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
        (d / "index.html").write_text(
            page(html, opening_frame(d / "possession.js"), current_sub=sub),
            encoding="utf-8")
        size = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
        total += size
        print(f"  docs/{sub + '/' if sub else '':10s} {label:22s} {size/1e6:6.1f} MB")
    print(f"built docs/ - {total/1e6:.1f} MB total")
    print("check locally:  python -m http.server -d docs 8080")

if __name__ == "__main__":
    main()
