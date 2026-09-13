"""A static server that honours Range requests, for looking at the viewer.

    python -m tools.serve            # http://127.0.0.1:8137/viewer/index.html

The viewer itself needs no server - it opens from `file://` and that is the
path that matters (docs/19, HANDOFF § 4). This exists for the times you want to
drive it from a browser automation harness, which usually cannot load sibling
scripts off `file://`.

Why not `python -m http.server`: `SimpleHTTPRequestHandler` answers every
request with 200 and the whole file, ignoring `Range`. A `<video>` element asks
for byte ranges when you seek, gets the entire stream back from byte zero, and
the scrub bar appears broken - HANDOFF § 4 warns about exactly this. Roughly
thirty lines buys a server that does not lie about what it is sending.

Serves the REPOSITORY ROOT, not `viewer/`, so that `../work/p0001/clip.mp4`
resolves the same way it does from `file://`.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import re
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()
        m = _RANGE.match(rng.strip())
        path = self.translate_path(self.path)
        if not m or os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404)
            return None

        size = os.fstat(f.fileno()).st_size
        first, last = m.group(1), m.group(2)
        if first:
            start = int(first)
            end = int(last) if last else size - 1
        else:
            # A suffix range: the LAST n bytes. Getting this backwards serves
            # the head of the file with a 206 on it, which is a lie the client
            # has no way to detect.
            start, end = max(0, size - int(last or 0)), size - 1
        if start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            f.close()
            return None
        end = min(end, size - 1)

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        f.seek(start)
        return _Slice(f, end - start + 1)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


class _Slice:
    """A file object that stops after n bytes, so copyfile sends just the range."""

    def __init__(self, f, n):
        self.f, self.left = f, n

    def read(self, size=-1):
        if self.left <= 0:
            return b""
        if size is None or size < 0:
            size = self.left
        chunk = self.f.read(min(size, self.left))
        self.left -= len(chunk)
        return chunk

    def close(self):
        self.f.close()


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.serve")
    p.add_argument("--port", type=int, default=8137)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args(argv)

    handler = functools.partial(RangeHandler, directory=str(ROOT))
    with _Server((args.host, args.port), handler) as httpd:
        print(f"[serve] {ROOT} on http://{args.host}:{args.port}/viewer/index.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
