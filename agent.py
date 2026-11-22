#!/usr/bin/env python3
"""Data agent: pulls from the sources listed in config.json and writes web/data.json.

Standard library only. Each source is a small function registered with @source(...)
that returns a "panel": {"kind": "list" | "stats" | "text", "title": str, "items": [...]}.

Add your own source (LLM, database, scraper...) by writing one function at the bottom
of the "SOURCES" section and referencing its name as {"type": "..."} in config.json.

Usage:
    python3 agent.py            # loop forever, refreshing every `refresh_seconds`
    python3 agent.py --once     # fetch once, write data.json, exit
    python3 agent.py --print    # fetch once and print JSON to stdout
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import logging
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "web" / "data.json"
UA = "livestream-proto/2.0 (+https://github.com/)"

DEFAULT_CONFIG: dict = {
    "title": "Live Dashboard",
    "theme": "midnight",
    "rotate_seconds": 15,
    "refresh_seconds": 60,
    "ticker": True,
    "sources": [{"type": "hackernews", "title": "Hacker News", "limit": 8}],
}

THEMES = ("midnight", "daylight", "neon", "terminal")

log = logging.getLogger("agent")


# --------------------------------------------------------------------------- helpers
def http_get(url: str, timeout: float = 10, headers: dict | None = None) -> bytes:
    """GET a URL (http/https only) and return the body."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {url!r}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})  # noqa: S310 (scheme checked above)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.read(5_000_000)


def http_json(url: str, **kw):
    return json.loads(http_get(url, **kw))


def clip(text: str, n: int = 140) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def human(n: float) -> str:
    n = float(n)
    for unit, div in (("M", 1e6), ("k", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}".replace(".0", "")
    return str(int(n))


def load_config(path: str | os.PathLike | None = None) -> dict:
    """Config precedence: explicit path > $CONFIG > config.json > config.example.json > defaults."""
    candidates = [path, os.environ.get("CONFIG"), ROOT / "config.json", ROOT / "config.example.json"]
    cfg = dict(DEFAULT_CONFIG)
    for c in candidates:
        if c and pathlib.Path(c).is_file():
            try:
                cfg.update(json.loads(pathlib.Path(c).read_text(encoding="utf-8")))
                log.info("config: %s", c)
                break
            except (OSError, json.JSONDecodeError) as e:
                log.error("cannot read config %s: %s", c, e)
    return validate_config(cfg)


def validate_config(cfg: dict) -> dict:
    """Fill in defaults and clamp values to sane ranges so a typo can't break the stream."""
    cfg = {**DEFAULT_CONFIG, **cfg}
    cfg["title"] = str(cfg.get("title") or DEFAULT_CONFIG["title"])
    cfg["rotate_seconds"] = max(5, min(int(cfg.get("rotate_seconds", 15) or 15), 600))
    cfg["refresh_seconds"] = max(10, min(int(cfg.get("refresh_seconds", 60) or 60), 3600))
    if cfg.get("theme") not in THEMES:
        cfg["theme"] = "midnight"
    if not isinstance(cfg.get("sources"), list) or not cfg["sources"]:
        cfg["sources"] = DEFAULT_CONFIG["sources"]
    cfg["ticker"] = bool(cfg.get("ticker", True))
    return cfg


# --------------------------------------------------------------------------- sources
SOURCES: dict = {}


def source(name: str):
    def deco(fn):
        SOURCES[name] = fn
        return fn
    return deco


@source("hackernews")
def hackernews(cfg: dict) -> dict:
    base = "https://hacker-news.firebaseio.com/v0"
    limit = int(cfg.get("limit", 8))
    ids = http_json(f"{base}/topstories.json")[:limit]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        stories = list(ex.map(lambda i: http_json(f"{base}/item/{i}.json") or {}, ids))
    items = [
        {"title": clip(s.get("title", "?")),
         "meta": f'{s.get("score", 0)} pts · {s.get("descendants", 0)} comments'}
        for s in stories
    ]
    return {"kind": "list", "title": cfg.get("title", "Hacker News"), "items": items}


def _xml_text(el, *names) -> str:
    for n in names:
        found = el.find(n)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


@source("rss")
def rss(cfg: dict) -> dict:
    """Any RSS 2.0 or Atom feed."""
    root = ET.fromstring(http_get(cfg["url"]))  # noqa: S314 (feeds are the operator's choice)
    limit = int(cfg.get("limit", 8))
    atom = "{http://www.w3.org/2005/Atom}"
    nodes = root.findall(".//item") or root.findall(f".//{atom}entry")
    items = []
    for n in nodes[:limit]:
        title = _xml_text(n, "title", f"{atom}title")
        when = _xml_text(n, "pubDate", f"{atom}updated", f"{atom}published")
        items.append({"title": clip(title or "?"), "meta": clip(when, 22)})
    feed_title = _xml_text(root, "channel/title", f"{atom}title")
    return {"kind": "list", "title": cfg.get("title") or clip(feed_title, 40) or "News", "items": items}


@source("reddit")
def reddit(cfg: dict) -> dict:
    sub = urllib.parse.quote(str(cfg.get("subreddit", "technology")))
    limit = int(cfg.get("limit", 8))
    period = cfg.get("period", "day")
    data = http_json(f"https://www.reddit.com/r/{sub}/top.json?t={period}&limit={limit}")
    items = [
        {"title": clip(c["data"]["title"]),
         "meta": f'{human(c["data"].get("score", 0))} pts · {c["data"].get("num_comments", 0)} comments'}
        for c in data["data"]["children"]
    ]
    return {"kind": "list", "title": cfg.get("title", f"r/{cfg.get('subreddit', 'technology')}"), "items": items}


@source("github")
def github(cfg: dict) -> dict:
    """Fastest-growing new repositories (created within the last `days`)."""
    days = int(cfg.get("days", 7))
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    q = f"created:>{since}"
    if cfg.get("language"):
        q += f" language:{cfg['language']}"
    url = ("https://api.github.com/search/repositories?" +
           urllib.parse.urlencode({"q": q, "sort": "stars", "order": "desc", "per_page": int(cfg.get("limit", 8))}))
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    data = http_json(url, headers=headers)
    items = [
        {"title": clip(f'{r["full_name"]} — {r.get("description") or "no description"}'),
         "meta": f'★ {human(r["stargazers_count"])} · {r.get("language") or "n/a"}'}
        for r in data.get("items", [])
    ]
    return {"kind": "list", "title": cfg.get("title", "New on GitHub"), "items": items}


@source("crypto")
def crypto(cfg: dict) -> dict:
    coins = cfg.get("coins", ["bitcoin", "ethereum"])
    cur = str(cfg.get("currency", "usd")).lower()
    url = ("https://api.coingecko.com/api/v3/simple/price?" +
           urllib.parse.urlencode({"ids": ",".join(coins), "vs_currencies": cur, "include_24hr_change": "true"}))
    data = http_json(url)
    items = []
    for c in coins:
        row = data.get(c)
        if not row:
            continue
        price = row[cur]
        fmt = f"{price:,.2f}" if price < 1000 else f"{price:,.0f}"
        items.append({"title": c.upper(), "meta": f"{fmt} {cur.upper()}", "delta": round(row.get(f"{cur}_24h_change", 0), 2)})
    return {"kind": "stats", "title": cfg.get("title", "Crypto"), "items": items}


WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog", 51: "Light drizzle",
       53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow",
       73: "Snow", 75: "Heavy snow", 80: "Showers", 81: "Showers", 82: "Violent showers", 95: "Thunderstorm",
       96: "Thunderstorm", 99: "Thunderstorm"}


@source("weather")
def weather(cfg: dict) -> dict:
    """Open-Meteo (no API key). places: [{"name": "Dhaka", "lat": 23.81, "lon": 90.41}]"""
    items = []
    for p in cfg.get("places", [{"name": "London", "lat": 51.5, "lon": -0.12}]):
        url = ("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": p["lat"], "longitude": p["lon"], "timezone": "auto",
            "current": "temperature_2m,weather_code,wind_speed_10m"}))
        cur = http_json(url)["current"]
        sky = WMO.get(cur["weather_code"], "—")
        items.append({"title": p["name"],
                      "meta": f'{round(cur["temperature_2m"])}°C · {sky} · {round(cur["wind_speed_10m"])} km/h'})
    return {"kind": "stats", "title": cfg.get("title", "Weather"), "items": items}


@source("text")
def text(cfg: dict) -> dict:
    """Static slide: {"type": "text", "title": "...", "lines": ["...", "..."]}"""
    lines = cfg.get("lines", [])
    return {"kind": "text", "title": cfg.get("title", ""), "items": [{"title": clip(x, 200), "meta": ""} for x in lines]}


@source("file")
def file_source(cfg: dict) -> dict:
    """Read lines from a local file, so *any* other program can feed the stream.
    Each line is `title` or `title | meta`. Path is relative to the project root."""
    p = (ROOT / cfg["path"]).resolve()
    if ROOT not in p.parents and p != ROOT:
        raise ValueError("file source must live inside the project folder")
    items = []
    for line in p.read_text(encoding="utf-8").splitlines()[: int(cfg.get("limit", 10))]:
        if line.strip():
            title, _, meta = line.partition("|")
            items.append({"title": clip(title, 160), "meta": clip(meta, 40)})
    return {"kind": cfg.get("kind", "list"), "title": cfg.get("title", p.stem), "items": items}


# --------------------------------------------------------------------------- engine
class Agent:
    """Runs every source, keeps the last good result when one fails."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.cache: dict[int, dict] = {}

    def run_source(self, idx: int, sc: dict) -> dict:
        kind = sc.get("type")
        fn = SOURCES.get(kind)
        if not fn:
            raise ValueError(f"unknown source type {kind!r} (known: {', '.join(SOURCES)})")
        panel = fn(sc)
        if not panel.get("items"):
            raise ValueError("source returned no items")
        panel.update(id=f"p{idx}", type=kind, stale=False, fetched=int(time.time()))
        return panel

    def collect(self) -> dict:
        panels, errors = [], []
        with cf.ThreadPoolExecutor(max_workers=min(8, len(self.cfg["sources"]))) as ex:
            futs = {ex.submit(self.run_source, i, sc): (i, sc) for i, sc in enumerate(self.cfg["sources"])}
            results = {}
            for fut in cf.as_completed(futs):
                i, sc = futs[fut]
                try:
                    results[i] = fut.result()
                    self.cache[i] = results[i]
                except Exception as e:  # noqa: BLE001 - one bad source must never stop the stream
                    log.warning("source #%d (%s) failed: %s", i, sc.get("type"), e)
                    errors.append({"source": sc.get("type"), "error": clip(e, 80)})
                    if i in self.cache:
                        results[i] = dict(self.cache[i], stale=True)
        for i in sorted(results):
            panels.append(results[i])
        if not panels:
            panels = [{"id": "p0", "type": "text", "kind": "text", "title": "Reconnecting…", "stale": True,
                       "items": [{"title": "Feed unavailable, retrying…", "meta": ""}]}]
        now = dt.datetime.now()
        return {
            "title": self.cfg["title"], "theme": self.cfg["theme"],
            "rotate_seconds": self.cfg["rotate_seconds"], "ticker": self.cfg["ticker"],
            "panels": panels, "errors": errors,
            "updated": now.strftime("%H:%M:%S"), "updated_ts": int(now.timestamp()),
        }


def write_atomic(path: pathlib.Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true", help="fetch once and exit")
    ap.add_argument("--print", action="store_true", help="print JSON instead of writing data.json")
    ap.add_argument("--config", help="path to a config JSON file")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    agent = Agent(cfg)
    while True:
        data = agent.collect()
        if args.print:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            OUT.parent.mkdir(exist_ok=True)
            write_atomic(OUT, data)
            log.info("wrote %d panel(s), %d error(s)", len(data["panels"]), len(data["errors"]))
        if args.once or args.print:
            return 0
        time.sleep(cfg["refresh_seconds"])


if __name__ == "__main__":
    sys.exit(main())
