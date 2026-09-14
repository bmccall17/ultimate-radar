"""
Builds the public GitHub Pages site into docs/.

The site is the viewer running on the synthetic fixture and nothing else. No broadcast
footage, no real tracking output: `data.js` is invented data committed to this repo, and
the real possessions under work/ are gitignored and stay local.

    python -m tools.build_site

GitHub Pages is served from the docs/ folder on the default branch. The design documents
already in docs/ are served alongside it; .nojekyll keeps Pages from trying to process them.
"""
import pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "viewer", ROOT / "docs"

def main():
    html = (SRC / "index.html").read_text(encoding="utf-8")

    # The site ships the fixture only. live-data.js is gitignored, is built from work/,
    # and would 404 here; dropping the tag keeps the console clean and makes the
    # omission deliberate rather than incidental.
    html, n = re.subn(r'[ \t]*<script src="live-data\.js"></script>\n', "", html)
    if n != 1:
        sys.exit(f"expected exactly one live-data.js tag in viewer/index.html, found {n}")

    banner = (
        '<!-- Built by tools/build_site.py from viewer/index.html. Do not edit docs/index.html;\n'
        '     edit the viewer and rebuild. Synthetic fixture only - no broadcast footage. -->\n'
    )
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(banner + html, encoding="utf-8")
    shutil.copy2(SRC / "data.js", OUT / "data.js")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    size = sum((OUT / f).stat().st_size for f in ("index.html", "data.js"))
    print(f"built docs/ - index.html + data.js, {size/1024:.0f} KB")
    print("serve locally:  python -m http.server -d docs 8080")

if __name__ == "__main__":
    main()
