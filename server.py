#!/usr/bin/env python3
"""Hacker Radio - local console server.

Serves the console UI and drives a single VLC instance through its built-in
HTTP interface (127.0.0.1:8099).  Standard library only: no pip installs.

    python server.py            # http://127.0.0.1:8799
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))


def _find_vlc() -> str:
    """Locate VLC: HACKER_RADIO_VLC wins, then the usual install paths, then PATH."""
    env = os.environ.get("HACKER_RADIO_VLC") or os.environ.get("VLC_PATH") or ""
    if env and os.path.isfile(env):
        return env
    for candidate in (
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        "/usr/bin/vlc",
        "/usr/local/bin/vlc",
        "/Applications/VLC.app/Contents/MacOS/VLC",
    ):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("vlc") or candidate


VLC = _find_vlc()
VLC_HTTP = "http://127.0.0.1:8099"
VLC_PASS = "hacker"
APP_PORT = 8799
STATE_FILE = os.path.join(ROOT, "state.json")
VLC_PID = os.path.join(ROOT, "vlc.pid")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HackerRadio/1.0"

# --------------------------------------------------------------------------
# Curated catalogue.  Every URL was checked live with VLC's user agent.
# --------------------------------------------------------------------------
STATIONS = [
    # --- hacking / cyberpunk -------------------------------------------
    {"slug": "defcon", "name": "SomaFM DEF CON Radio", "cat": "hacker",
     "desc": "Music for Hacking - the DEF CON year-round channel",
     "url": "https://ice4.somafm.com/defcon-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/defcon/"},
    {"slug": "nightride", "name": "Nightride FM", "cat": "hacker",
     "desc": "Synthwave, cyberpunk and retrowave 24/7",
     "url": "https://stream.nightride.fm/nightride.mp3", "codec": "MP3",
     "site": "https://nightride.fm/"},
    {"slug": "darksynth", "name": "Nightride FM - Darksynth", "cat": "hacker",
     "desc": "Darker end of the synth spectrum",
     "url": "https://stream.nightride.fm/darksynth.mp3", "codec": "MP3",
     "site": "https://nightride.fm/"},
    {"slug": "plaza", "name": "Nightwave Plaza", "cat": "hacker",
     "desc": "Vaporwave and late-night synth",
     "url": "https://radio.plaza.one/mp3", "codec": "MP3",
     "site": "https://plaza.one/"},
    {"slug": "cliqhop", "name": "SomaFM Cliqhop IDM", "cat": "hacker",
     "desc": "Beats and bleeps for the terminal",
     "url": "https://ice4.somafm.com/cliqhop-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/cliqhop/"},
    {"slug": "missioncontrol", "name": "SomaFM Mission Control", "cat": "hacker",
     "desc": "NASA chatter over ambient electronics",
     "url": "https://ice4.somafm.com/missioncontrol-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/missioncontrol/"},

    # --- ambient / deep space ------------------------------------------
    {"slug": "deepspaceone", "name": "SomaFM Deep Space One", "cat": "space",
     "desc": "Ambient space music for deep focus",
     "url": "https://ice4.somafm.com/deepspaceone-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/deepspaceone/"},
    {"slug": "dronezone", "name": "SomaFM Drone Zone", "cat": "space",
     "desc": "Atmospheric drones, no beats",
     "url": "https://ice4.somafm.com/dronezone-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/dronezone/"},
    {"slug": "synphaera", "name": "SomaFM Synphaera", "cat": "space",
     "desc": "Modern space-music label showcase, 256k",
     "url": "https://ice4.somafm.com/synphaera-256-mp3", "codec": "MP3 256k",
     "site": "https://somafm.com/synphaera/"},
    {"slug": "spacestation", "name": "SomaFM Space Station Soma", "cat": "space",
     "desc": "Mid-tempo space lounge",
     "url": "https://ice4.somafm.com/spacestation-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/spacestation/"},
    {"slug": "lush", "name": "SomaFM Lush", "cat": "space",
     "desc": "Sensuous vocals and lush downtempo",
     "url": "https://ice4.somafm.com/lush-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/lush/"},

    # --- chill / focus ---------------------------------------------------
    {"slug": "groovesalad", "name": "SomaFM Groove Salad", "cat": "chill",
     "desc": "Classic ambient downtempo, the work soundtrack",
     "url": "https://ice4.somafm.com/groovesalad-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/groovesalad/"},
    {"slug": "secretagent", "name": "SomaFM Secret Agent", "cat": "chill",
     "desc": "Spy-movie cocktail lounge, cinematic",
     "url": "https://ice4.somafm.com/secretagent-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/secretagent/"},
    {"slug": "fluid", "name": "SomaFM Fluid", "cat": "chill",
     "desc": "Instrumental hip-hop and beats",
     "url": "https://ice4.somafm.com/fluid-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/fluid/"},
    {"slug": "beatblender", "name": "SomaFM Beat Blender", "cat": "chill",
     "desc": "Late-night deep house and downtempo",
     "url": "https://ice4.somafm.com/beatblender-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/beatblender/"},
    {"slug": "radioparadise", "name": "Radio Paradise", "cat": "chill",
     "desc": "Hand-picked eclecticism, listener supported",
     "url": "https://stream.radioparadise.com/aac-128", "codec": "AAC 128k",
     "site": "https://radioparadise.com/"},

    # --- scanners / real radio -------------------------------------------
    {"slug": "scanner", "name": "SomaFM SF Police Scanner", "cat": "radio",
     "desc": "Live San Francisco public-safety radio",
     "url": "https://ice4.somafm.com/scanner-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/scanner/"},
    {"slug": "sf1033", "name": "SomaFM SF 10-33", "cat": "radio",
     "desc": "Ambient emergency-services dispatches",
     "url": "https://ice2.somafm.com/sf1033-128-mp3", "codec": "MP3 128k",
     "site": "https://somafm.com/sf1033/"},
    {"slug": "warsug", "name": "Perth Fire & Rescue", "cat": "radio",
     "desc": "Western Australia emergency scanner",
     "url": "https://stream.warsug.info/WARSUG", "codec": "MP3",
     "site": "https://warsug.info/"},
    {"slug": "anonfm", "name": "Anon.FM", "cat": "radio",
     "desc": "Hacktivist-run electronic radio",
     "url": "https://icecast.anon.fm/radio", "codec": "MP3",
     "site": "https://anon.fm/"},
]

BY_SLUG = {s["slug"]: s for s in STATIONS}
CATS = {
    "hacker": "HACKING / CYBERPUNK",
    "space": "AMBIENT / DEEP SPACE",
    "chill": "CHILL / FOCUS",
    "radio": "SCANNERS / REAL RADIO",
}

LIVE = {"slug": None, "name": None, "url": None, "started": 0}
NP_CACHE = {"key": None, "at": 0.0, "value": None}
LOCK = threading.Lock()


# --------------------------------------------------------------------------
# VLC plumbing
# --------------------------------------------------------------------------
def _vlc_req(params: dict, timeout: float = 6.0) -> str:
    url = f"{VLC_HTTP}/requests/status.xml?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    token = base64.b64encode(f":{VLC_PASS}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def vlc_alive() -> bool:
    try:
        _vlc_req({}, timeout=2.5)
        return True
    except Exception:
        return False


def vlc_command(**params) -> bool:
    try:
        _vlc_req(params)
        return True
    except Exception as exc:
        print(f"[vlc] command failed {params}: {exc}", flush=True)
        return False


def ensure_vlc() -> bool:
    """Make sure exactly one headless VLC is listening on the control port."""
    if vlc_alive():
        return True
    if not os.path.exists(VLC):
        print(f"[vlc] not found at {VLC}", flush=True)
        return False
    args = [
        VLC,
        "--intf", "dummy",              # no window at all
        "--extraintf=http",             # but keep the control API
        "--http-host=127.0.0.1",
        "--http-port=8099",
        "--http-password=" + VLC_PASS,
        "--no-video",
        "--no-osd",
        "--no-media-library",
        "--no-playlist-autostart",
        "--quiet",
    ]
    print("[vlc] starting headless engine (no window)", flush=True)
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        with open(VLC_PID, "w", encoding="utf-8") as fh:
            fh.write(str(proc.pid))
    except OSError:
        pass
    for _ in range(40):
        time.sleep(0.35)
        if vlc_alive():
            return True
    print("[vlc] engine did not come up", flush=True)
    return False


def vlc_state() -> dict:
    try:
        raw = _vlc_req({}, timeout=3.0)
    except Exception:
        return {"ok": False, "state": "offline", "volume": 0}
    root = ET.fromstring(raw)
    def txt(tag, default=""):
        el = root.find(tag)
        return el.text if el is not None and el.text else default
    vol = int(txt("volume", "0") or 0)
    meta = {}
    for info in root.findall("./information/category/info"):
        name = info.get("name")
        if name:
            meta[name.lower()] = info.text or ""
    return {
        "ok": True,
        "state": txt("state", "stopped"),
        "volume": vol,
        "filename": meta.get("filename") or "",
        "title": meta.get("title") or meta.get("filename") or "",
        "artist": meta.get("artist") or "",
        "now_playing": meta.get("now_playing") or "",
    }


# --------------------------------------------------------------------------
# Now playing
# --------------------------------------------------------------------------
SOMAFM_RE = re.compile(r"somafm\.com/([a-z0-9]+)-(\d+)-(mp3|aac)")


def _somafm_channel(url: str) -> str | None:
    m = SOMAFM_RE.search(url or "")
    return m.group(1) if m else None


def _fetch_json(url: str, timeout: float = 6.0):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def now_playing(url: str) -> dict:
    ch = _somafm_channel(url)
    if not ch:
        return {}
    key = f"somafm:{ch}"
    with LOCK:
        if NP_CACHE["key"] == key and time.time() - NP_CACHE["at"] < 15:
            return NP_CACHE["value"] or {}
    value = {}
    try:
        data = _fetch_json(f"https://somafm.com/songs/{ch}.json")
        songs = data.get("songs") or []
        if songs:
            s = songs[0]
            value = {
                "artist": s.get("artist") or "",
                "title": s.get("title") or "",
                "album": s.get("album") or "",
            }
    except Exception:
        value = {}
    with LOCK:
        NP_CACHE.update({"key": key, "at": time.time(), "value": value})
    return value


# --------------------------------------------------------------------------
# Station control
# --------------------------------------------------------------------------
GENERIC_TOKENS = {"mp3", "aac", "ogg", "m4a", "radio", "stream", "live", "audio"}


def _url_token(url: str) -> str:
    """Distinctive last path segment of a stream URL, for matching VLC's filename."""
    seg = urllib.parse.urlparse(url or "").path.rsplit("/", 1)[-1]
    seg = re.sub(r"\.(mp3|m4a|aac|ogg|opus)$", "", seg, flags=re.I).lower()
    return "" if seg in GENERIC_TOKENS else seg


def current_station() -> dict | None:
    """What VLC is really playing, matched back to the catalogue."""
    fn = (vlc_state().get("filename") or "").lower()
    if not fn:
        return None
    for st in STATIONS:
        tok = _url_token(st["url"])
        if tok and tok in fn:
            return st
    return None


def play_url(url: str, name: str, slug: str | None = None) -> bool:
    """Play a stream and confirm VLC actually switched, retrying once.

    VLC's in_play can silently no-op when the player is still loading the
    previous input, so we watch its filename and re-issue the command.
    """
    if not ensure_vlc():
        return False
    token = _url_token(url)
    if not vlc_command(command="in_play", input=url):
        return False
    with LOCK:
        LIVE.update({"slug": slug, "name": name, "url": url,
                     "started": time.time(), "switching_until": time.time() + 8})

    confirmed = False
    for attempt in (1, 2):
        for _ in range(10):
            time.sleep(0.3)
            fn = (vlc_state().get("filename") or "").lower()
            if not token or (fn and token in fn):
                confirmed = True
                break
        if confirmed:
            break
        print(f"[vlc] switch to {token!r} not confirmed, retrying", flush=True)
        vlc_command(command="in_play", input=url)
    if not confirmed:
        actual = current_station()
        if actual and actual["slug"] != slug:
            print(f"[vlc] drift: requested {slug}, playing {actual['slug']}", flush=True)
    save_state()
    return True


def save_state() -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump({"slug": LIVE["slug"], "name": LIVE["name"], "url": LIVE["url"]}, fh)
    except Exception:
        pass


def load_state() -> None:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        LIVE.update({k: data.get(k) for k in ("slug", "name", "url")})
    except Exception:
        pass


def status() -> dict:
    st = vlc_state()
    switching = time.time() < (LIVE.get("switching_until") or 0)
    actual = current_station() if (st.get("state") == "playing" and not switching) else None
    if actual:
        # Trust what VLC is actually decoding over what we last asked for.
        if LIVE.get("slug") != actual["slug"]:
            with LOCK:
                LIVE.update({"slug": actual["slug"], "name": actual["name"],
                             "url": actual["url"]})
            save_state()
        slug, name, url = actual["slug"], actual["name"], actual["url"]
    else:
        slug, name, url = LIVE.get("slug"), LIVE.get("name"), LIVE.get("url") or ""

    np_ = now_playing(url) if st.get("state") == "playing" else {}
    if not np_ and st.get("now_playing"):
        raw = st["now_playing"]
        if " - " in raw:
            artist, title = raw.split(" - ", 1)
            np_ = {"artist": artist.strip(), "title": title.strip()}
        else:
            np_ = {"artist": "", "title": raw.strip()}
    return {
        "ok": st.get("ok", False),
        "state": st.get("state", "offline"),
        "volume": st.get("volume", 0),
        "station": {"slug": slug, "name": name, "url": url},
        "nowplaying": np_,
        "uptime": int(time.time() - LIVE["started"]) if LIVE.get("started") else 0,
        "station_count": len(STATIONS),
    }


# --------------------------------------------------------------------------
# Radio Browser (open community station database)
# --------------------------------------------------------------------------
RB_HOSTS = ["de1.api.radio-browser.info", "nl1.api.radio-browser.info",
            "at1.api.radio-browser.info"]


def rb_search(query: str, limit: int = 30) -> list[dict]:
    params = {
        "limit": str(limit),
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true",
    }
    if query:
        params["name"] = query
    last_err = None
    for host in RB_HOSTS:
        try:
            url = f"https://{host}/json/stations/search?{urllib.parse.urlencode(params)}"
            rows = _fetch_json(url, timeout=9.0)
            out = []
            for r in rows or []:
                out.append({
                    "name": (r.get("name") or "").strip()[:90],
                    "url": r.get("url_resolved") or r.get("url") or "",
                    "country": r.get("country") or "",
                    "tags": (r.get("tags") or "")[:70],
                    "codec": r.get("codec") or "",
                    "bitrate": r.get("bitrate") or 0,
                    "homepage": r.get("homepage") or "",
                })
            return [s for s in out if s["url"]]
        except Exception as exc:
            last_err = exc
            continue
    print(f"[radio-browser] {last_err}", flush=True)
    return []


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "HackerRadio/1.0"

    def log_message(self, fmt, *args):  # quieter log
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._serve_index()

        if path == "/favicon.ico":
            fp = os.path.join(ROOT, "hackerradio.ico")
            try:
                with open(fp, "rb") as fh:
                    return self._send(200, fh.read(), "image/x-icon")
            except OSError:
                return self._send(204, b"", "image/x-icon")

        if path == "/api/stations":
            cats = [{"id": k, "label": v} for k, v in CATS.items()]
            return self._json({"stations": STATIONS, "categories": cats})

        if path == "/api/status":
            return self._json(status())

        if path == "/api/play":
            slug = (qs.get("slug") or [""])[0]
            st = BY_SLUG.get(slug)
            if not st:
                return self._json({"ok": False, "error": "unknown station"}, 404)
            ok = play_url(st["url"], st["name"], slug)
            return self._json({"ok": ok, "station": st})

        if path == "/api/playurl":
            url = (qs.get("u") or [""])[0]
            name = (qs.get("name") or ["Custom stream"])[0][:120]
            if not url.lower().startswith(("http://", "https://")):
                return self._json({"ok": False, "error": "bad url"}, 400)
            ok = play_url(url, name, None)
            return self._json({"ok": ok, "name": name})

        if path == "/api/stop":
            ok = vlc_command(command="pl_stop")
            with LOCK:
                LIVE.update({"slug": None, "name": None, "url": None, "started": 0})
            save_state()
            return self._json({"ok": ok})

        if path == "/api/pause":
            return self._json({"ok": vlc_command(command="pl_pause")})

        if path == "/api/volume":
            try:
                pct = max(0, min(100, int((qs.get("v") or ["70"])[0])))
            except ValueError:
                pct = 70
            ok = vlc_command(command="volume", val=str(int(pct * 5.12)))
            return self._json({"ok": ok, "volume": int(pct * 5.12)})

        if path == "/api/search":
            q = (qs.get("q") or [""])[0].strip()
            return self._json({"query": q, "results": rb_search(q)})

        if path == "/api/prev" or path == "/api/next":
            order = [s["slug"] for s in STATIONS]
            cur = LIVE.get("slug") or order[0]
            idx = order.index(cur) if cur in order else 0
            step = -1 if path == "/api/prev" else 1
            nxt = STATIONS[(idx + step) % len(STATIONS)]
            ok = play_url(nxt["url"], nxt["name"], nxt["slug"])
            return self._json({"ok": ok, "station": nxt})

        return self._json({"error": "not found"}, 404)

    def _serve_index(self) -> None:
        path = os.path.join(ROOT, "index.html")
        try:
            with open(path, encoding="utf-8") as fh:
                html = fh.read()
        except OSError:
            return self._send(500, b"index.html missing", "text/plain")
        # Inject the current state so the console paints populated on first frame.
        try:
            boot = {
                "status": status(),
                "stations": STATIONS,
                "categories": [{"id": k, "label": v} for k, v in CATS.items()],
            }
            blob = json.dumps(boot).replace("</", "<\\/")
            html = html.replace("/*__BOOT__*/null", blob, 1)
        except Exception as exc:
            print(f"[boot] injection skipped: {exc}", flush=True)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")


def main() -> None:
    load_state()
    ensure_vlc()
    httpd = ThreadingHTTPServer(("127.0.0.1", APP_PORT), Handler)
    print(f"Hacker Radio console -> http://127.0.0.1:{APP_PORT}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
