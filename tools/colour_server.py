#!/usr/bin/env python3
"""colour_server.py -- serves the repo over http for tools/colour_mapper.html, PLUS one write
endpoint so the page's "Save to repo" button can store the mapping.

    python tools/colour_server.py [port]       default port 8010; opens the page in the browser

POST /api/colour_mapping  {version, palettes: {...}}  (only from 127.0.0.1) -> data/colour_mapping.json,
the old file backed up to data/attic/ first. The game picks it up at the next build_hybrid.sh
(tools/mkpalette.py). The page itself works without this server (file://, Export JSON).
"""
import functools, http.server, json, shutil, socketserver, sys, threading, time, webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "colour_mapping.json"
ATTIC = ROOT / "data" / "attic"
NAMES = {"black", "blue", "red", "magenta", "green", "cyan", "yellow", "white"}
LOCK = threading.Lock()


def valid(m):
    pals = m.get("palettes")
    if not isinstance(pals, dict) or set(pals) != {"0", "1", "2", "3"}:
        return "palettes must have keys 0-3"
    for p, e in pals.items():
        if "terrain" not in e:
            return "palette %s has no terrain mapping" % p
        for cls, pens in e.items():
            if not isinstance(pens, list) or len(pens) != 4:
                return "palette %s %s: 4 pens expected" % (p, cls)
            for c in pens:
                cs = c if isinstance(c, list) else [c]
                if not cs or len(cs) > 2 or any(x not in NAMES for x in cs):
                    return "palette %s %s: bad colour %r" % (p, cls, c)
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/colour_mapping" or self.client_address[0] != "127.0.0.1":
            self.send_error(404)
            return
        try:
            m = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            err = valid(m)
            if err:
                out = {"ok": False, "error": err}
            else:
                with LOCK:
                    ATTIC.mkdir(parents=True, exist_ok=True)
                    backup = ""
                    if DEST.exists():
                        backup = str((ATTIC / ("colour_mapping.%s.json" % time.strftime("%Y%m%d-%H%M%S"))).relative_to(ROOT))
                        shutil.copyfile(DEST, ROOT / backup)
                    DEST.write_text(json.dumps(m, indent=2) + "\n", newline="\n")
                out = {"ok": True, "backup": backup}
        except Exception as e:                      # report, never crash the server
            out = {"ok": False, "error": str(e)}
        body = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print("POST /api/colour_mapping:", out)

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
    handler = functools.partial(Handler, directory=str(ROOT))
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        url = "http://127.0.0.1:%d/tools/colour_mapper.html" % port
        print("serving", ROOT, "-", url, "(Ctrl+C to stop)")
        webbrowser.open(url)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
