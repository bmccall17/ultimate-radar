# viewer

**`index.html` is the product.** Open it directly in a browser — no server, no build step, no
framework, no dependency. Spec: `docs/06-viewer.md`. Results and known limits:
`docs/19-m6-viewer.md`.

```
index.html       the viewer (M6)
data.js          the synthetic fixture. Committed. Loads first.
live-data.js     a real possession. Gitignored. Loads second and wins.
prototype.html   the design reference M6 was built from. Kept for comparison.
```

Both data files are plain scripts assigning `window.POSSESSION`, because a page opened from
`file://` cannot `fetch` a sibling JSON file. A fresh clone has no `live-data.js`, takes a
harmless 404, and renders the fixture. Write one with:

```bash
python -m tools.make_view work/p0001
```

That also carries `issues.json`, `identities.json` and `events.json` across when they exist.
None of them are required; the panes that have nothing say so.

## If you serve it instead of opening it

Use a server that supports **range requests**. Python's `http.server` does not, so the video
loads but `video.seekable` comes back `[0, 0]` and the scrub bar will look broken while the
overlay works perfectly. That is the server, not the page.

## prototype.html

The design reference, kept because `docs/06-viewer.md` was written from it and says "where
this document is silent, copy the prototype". It renders the fixture's synthetic positions
through a simulated pinhole camera; `index.html` puts that behind a `Projector` interface with
a second backend for the real homography, so everything above the projection is written once.

**It is not maintained.** Where the two disagree, `index.html` and `docs/06` are right — with
one exception worth knowing about: the prototype's `frustumPoly()` samples the whole image
border, which is correct for its pinhole camera because its `unproj` clamps above-horizon rays
to a far cap. Doing the same with a homography folds the polygon through infinity and scrims
the entire field. `docs/19` has the detail.
