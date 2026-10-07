#!/usr/bin/env python3
"""Local static server for previews and the PWA tests.

`python -m http.server` ignores `Range`, which PMTiles needs, so this answers
a single `Range: bytes=...` with 206 Partial Content.

With --allow-override (tests only) the response for a path can be replaced
at run time, e.g. to serve a new or emergency-stop `sw.js`:

    PUT    /__override__/sw.js   body = new content, Content-Type is kept
    DELETE /__override__/sw.js   back to the file on disk
    DELETE /__override__         drop every override

Usage: python3 tools/serve.py [--port 8765] [--root .] [--allow-override]
It listens on 127.0.0.1 only.
"""

import argparse
import email.utils
import http.server
import mimetypes
import os
import posixpath
import re
import threading
import urllib.parse

OVERRIDE_PREFIX = '/__override__'
RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')

mimetypes.add_type('application/manifest+json', '.webmanifest')
mimetypes.add_type('application/octet-stream', '.pmtiles')
mimetypes.add_type('application/x-protobuf', '.pbf')
mimetypes.add_type('application/geo+json', '.geojson')
mimetypes.add_type('text/javascript', '.js')


class Handler(http.server.SimpleHTTPRequestHandler):
    overrides = {}
    overrides_lock = threading.Lock()
    allow_override = False

    def end_headers(self):
        # Always revalidate, so a changed sw.js or index.html is seen at once.
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def log_message(self, fmt, *args):
        if os.environ.get('SERVE_QUIET'):
            return
        super().log_message(fmt, *args)

    # ---------------------------------------------------------- overrides

    def _override_key(self):
        path = urllib.parse.urlsplit(self.path).path
        if not path.startswith(OVERRIDE_PREFIX):
            return None
        return '/' + path[len(OVERRIDE_PREFIX):].lstrip('/')

    def _refuse(self):
        self.send_error(405, 'Overrides are disabled; start with --allow-override')

    def do_PUT(self):
        key = self._override_key()
        if key is None or key == '/':
            self.send_error(404)
            return
        if not self.allow_override:
            self._refuse()
            return
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length)
        with self.overrides_lock:
            self.overrides[key] = body
        self.send_response(204)
        self.end_headers()

    def do_DELETE(self):
        key = self._override_key()
        if key is None:
            self.send_error(404)
            return
        if not self.allow_override:
            self._refuse()
            return
        with self.overrides_lock:
            if key == '/':
                self.overrides.clear()
            else:
                self.overrides.pop(key, None)
        self.send_response(204)
        self.end_headers()

    # ---------------------------------------------------------- GET / HEAD

    def do_GET(self):
        self._serve(head=False)

    def do_HEAD(self):
        self._serve(head=True)

    def _serve(self, head):
        url_path = urllib.parse.urlsplit(self.path).path
        with self.overrides_lock:
            body = self.overrides.get(posixpath.normpath(urllib.parse.unquote(url_path)))
        if body is not None:
            self._send(len(body), lambda start, n: body[start:start + n], self.guess_type(url_path), None, head)
            return

        fs_path = self.translate_path(self.path)
        if os.path.isdir(fs_path):
            if not url_path.endswith('/'):
                self.send_response(301)
                self.send_header('Location', url_path + '/')
                self.end_headers()
                return
            fs_path = os.path.join(fs_path, 'index.html')
        if not os.path.isfile(fs_path):
            self.send_error(404)
            return
        mtime = email.utils.formatdate(os.path.getmtime(fs_path), usegmt=True)
        with open(fs_path, 'rb') as f:
            def read(start, n):
                f.seek(start)
                return f.read(n)
            self._send(os.fstat(f.fileno()).st_size, read, self.guess_type(fs_path), mtime, head)

    def _send(self, size, read, ctype, mtime, head):
        start, end = 0, size - 1
        status = 200
        rng = self.headers.get('Range')
        if rng:
            m = RANGE_RE.match(rng.strip())
            if not m or (not m.group(1) and not m.group(2)):
                self._unsatisfiable(size)
                return
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:
                start = max(size - int(m.group(2)), 0)
            if start >= size or start > end:
                self._unsatisfiable(size)
                return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if mtime:
            self.send_header('Last-Modified', mtime)
        self.end_headers()
        if not head and size:
            self.wfile.write(read(start, end - start + 1))

    def _unsatisfiable(self, size):
        self.send_response(416)
        self.send_header('Content-Range', f'bytes */{size}')
        self.send_header('Content-Length', '0')
        self.end_headers()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--root', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    ap.add_argument('--allow-override', action='store_true', help='enable /__override__ (tests only)')
    args = ap.parse_args()

    Handler.allow_override = args.allow_override
    root = os.path.abspath(args.root)

    def handler(*a, **kw):
        return Handler(*a, directory=root, **kw)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    print(f'Serving {root} at http://localhost:{args.port}/'
          + (' (overrides enabled)' if args.allow_override else ''), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
