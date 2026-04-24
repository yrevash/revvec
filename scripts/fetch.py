"""Fetch corpus assets per data/manifest.yml.

Design goals
------------
- Manifest-driven: users edit data/manifest.yml, not this file.
- Idempotent: every fetched file is cached by URL SHA-256 under
  data/fetch_cache/<hash>.<ext>. Re-running never re-downloads.
- Transparent: every action is logged to data/fetch_log.jsonl so a later
  compliance review can explain "where did this byte come from?"
- Pluggable per source type: add a new handler, register it in HANDLERS.

Run: python scripts/fetch.py
     or: make fetch
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

try:
    import yaml
except ImportError:
    sys.exit("PyYAML not installed. Run: uv pip install pyyaml")

try:
    import httpx
except ImportError:
    sys.exit("httpx not installed. It ships with actian-vectorai but fetch wants it explicitly.")

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "data" / "manifest.yml"
CACHE_DIR = REPO_ROOT / "data" / "fetch_cache"
LOG_PATH = REPO_ROOT / "data" / "fetch_log.jsonl"

NTRS_SEARCH = "https://ntrs.nasa.gov/api/citations/search"
IMAGES_API = "https://images-api.nasa.gov/search"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch")


# ─── data classes ────────────────────────────────────────────────────────────

@dataclass
class FetchedAsset:
    source_type: str            # ntrs | nasa_images | direct_pdf | direct_image | local_dir
    source_name: str            # key in manifest.sources
    target_ingestor: str        # sop | image | sensor
    url_or_path: str            # origin
    cache_path: Path            # local cached file
    content_sha256: str
    bytes_size: int
    metadata: dict[str, Any]    # source-specific (title, query, etc.)


# ─── cache / log helpers ─────────────────────────────────────────────────────

def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def cached_path(url: str, ext: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{url_hash(url)}{ext}"


def content_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download(client: httpx.Client, url: str, dest: Path, max_bytes: int | None = None) -> Path:
    """Idempotent GET with streaming. Returns cache path."""
    if dest.exists():
        log.info("cache hit: %s → %s", url[:80], dest.name)
        return dest
    log.info("GET %s", url[:100])
    with client.stream("GET", url, timeout=60.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        if max_bytes and total and total > max_bytes:
            raise ValueError(f"response too large: {total} bytes > {max_bytes}")
        dest_tmp = dest.with_suffix(dest.suffix + ".part")
        with dest_tmp.open("wb") as f:
            for chunk in resp.iter_bytes(65536):
                f.write(chunk)
        dest_tmp.rename(dest)
    return dest


def log_line(record: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")


# ─── source handlers ─────────────────────────────────────────────────────────

def handle_ntrs(client: httpx.Client, name: str, spec: dict[str, Any]) -> list[FetchedAsset]:
    assets: list[FetchedAsset] = []
    max_size_mb = int(spec.get("max_size_mb", 20))
    max_bytes = max_size_mb * 1024 * 1024
    for q in spec.get("queries", []):
        query = q["query"]
        max_items = int(q.get("max_items", 3))
        log.info("[ntrs] %s  (top %d, ≤ %d MB each)", query, max_items, max_size_mb)
        params = {"q": query, "page": 0, "size": max_items}
        resp = client.get(NTRS_SEARCH, params=params, timeout=30.0)
        if resp.status_code != 200:
            log.warning("[ntrs] search failed: %s", resp.status_code)
            continue
        data = resp.json()
        results = data.get("results", []) or data.get("hits", [])  # API shape has varied
        for r in results[:max_items]:
            doc_id = r.get("id") or r.get("gid") or r.get("doi")
            title = r.get("title", "")
            downloads = r.get("downloads", []) or []
            pdf_url = None
            for d in downloads:
                candidate = None
                if isinstance(d, dict):
                    links = d.get("links", {}) if isinstance(d.get("links"), dict) else {}
                    candidate = links.get("original") or links.get("pdf") or d.get("url")
                elif isinstance(d, str):
                    candidate = d
                if candidate and candidate.lower().endswith(".pdf"):
                    pdf_url = candidate
                    break
            if not pdf_url:
                continue
            if not pdf_url.startswith("http"):
                pdf_url = "https://ntrs.nasa.gov" + pdf_url
            dest = cached_path(pdf_url, ".pdf")
            try:
                download(client, pdf_url, dest, max_bytes=max_bytes)
            except Exception as e:  # noqa: BLE001
                log.warning("[ntrs] skip %s: %s", pdf_url[:80], e)
                continue
            sha = content_sha256(dest)
            asset = FetchedAsset(
                source_type="ntrs",
                source_name=name,
                target_ingestor=spec["target_ingestor"],
                url_or_path=pdf_url,
                cache_path=dest,
                content_sha256=sha,
                bytes_size=dest.stat().st_size,
                metadata={"query": query, "ntrs_id": doc_id, "title": title},
            )
            assets.append(asset)
            log_line({
                "ts": time.time(), "event": "fetched",
                "source_type": "ntrs", "source_name": name,
                "url": pdf_url, "title": title, "sha256": sha,
                "bytes": asset.bytes_size,
            })
            time.sleep(0.3)  # polite
    return assets


def _pick_image_url(urls: list[str], size: str, fallback: str) -> str:
    """NASA Image Library asset manifest returns a list of variant URLs like
    ...~thumb.jpg, ...~small.jpg, ...~medium.jpg, ...~large.jpg, ...~orig.jpg.
    Pick the one matching size, with graceful fallback."""
    markers = {
        "thumb":  ["~thumb.jpg", "~thumb.png"],
        "small":  ["~small.jpg", "~small.png"],
        "medium": ["~medium.jpg", "~medium.png"],
        "large":  ["~large.jpg", "~large.png"],
        "orig":   ["~orig.jpg", "~orig.png"],
    }.get(size, ["~medium.jpg", "~medium.png"])
    for m in markers:
        for u in urls:
            if u.endswith(m):
                return u
    # Descending fallback if the requested size is absent
    order = ["orig", "large", "medium", "small", "thumb"]
    for alt in order[order.index(size):] if size in order else order:
        for m in {
            "thumb":  ["~thumb.jpg"],  "small": ["~small.jpg"],
            "medium": ["~medium.jpg"], "large": ["~large.jpg"],
            "orig":   ["~orig.jpg"],
        }.get(alt, []):
            for u in urls:
                if u.endswith(m):
                    return u
    return fallback


def handle_nasa_images(client: httpx.Client, name: str, spec: dict[str, Any]) -> list[FetchedAsset]:
    assets: list[FetchedAsset] = []
    # image_size: thumb | small | medium | large | orig   (default: medium)
    image_size = str(spec.get("image_size", "medium"))
    # Back-compat: if thumbnail_only was set, override
    if spec.get("thumbnail_only"):
        image_size = "thumb"
    for q in spec.get("queries", []):
        query = q["query"]
        max_items = int(q.get("max_items", 20))
        log.info("[images] %s  (top %d, size=%s)", query, max_items, image_size)
        resp = client.get(
            IMAGES_API,
            params={"q": query, "media_type": "image"},
            timeout=30.0,
        )
        if resp.status_code != 200:
            log.warning("[images] search failed: %s", resp.status_code)
            continue
        data = resp.json()
        items = data.get("collection", {}).get("items", [])[:max_items]
        for item in items:
            links = item.get("links", [])
            preview_url = None
            for lk in links:
                if lk.get("rel") == "preview" and lk.get("render") == "image":
                    preview_url = lk.get("href")
                    break
            if not preview_url:
                continue
            if image_size == "thumb":
                pick_url = preview_url
            else:
                href = item.get("href")
                try:
                    manifest_resp = client.get(href, timeout=15.0)
                    manifest_resp.raise_for_status()
                    urls = manifest_resp.json()
                    pick_url = _pick_image_url(urls, image_size, fallback=preview_url)
                except Exception:  # noqa: BLE001
                    pick_url = preview_url
            ext = os.path.splitext(urlparse(pick_url).path)[1].lower()
            if ext not in {".jpg", ".jpeg", ".png"}:
                ext = ".jpg"
            dest = cached_path(pick_url, ext)
            try:
                download(client, pick_url, dest)
            except Exception as e:  # noqa: BLE001
                log.warning("[images] skip %s: %s", pick_url[:80], e)
                continue
            sha = content_sha256(dest)
            nasa_id = item.get("data", [{}])[0].get("nasa_id", "")
            title = item.get("data", [{}])[0].get("title", "")
            asset = FetchedAsset(
                source_type="nasa_images",
                source_name=name,
                target_ingestor=spec["target_ingestor"],
                url_or_path=pick_url,
                cache_path=dest,
                content_sha256=sha,
                bytes_size=dest.stat().st_size,
                metadata={"query": query, "nasa_id": nasa_id, "title": title, "image_size": image_size},
            )
            assets.append(asset)
            log_line({
                "ts": time.time(), "event": "fetched",
                "source_type": "nasa_images", "source_name": name,
                "url": pick_url, "nasa_id": nasa_id, "title": title,
                "sha256": sha, "bytes": asset.bytes_size,
            })
            time.sleep(0.2)
    return assets


def handle_direct(client: httpx.Client, name: str, spec: dict[str, Any]) -> list[FetchedAsset]:
    """Generic URL-list handler for direct_pdf / direct_image sources."""
    assets: list[FetchedAsset] = []
    urls = spec.get("urls", []) or []
    if not urls:
        log.info("[%s] no URLs configured", name)
        return assets
    ext_map = {"direct_pdf": ".pdf", "direct_image": ".jpg"}
    ext_default = ext_map.get(spec["type"], ".bin")
    for url in urls:
        path_ext = os.path.splitext(urlparse(url).path)[1].lower() or ext_default
        dest = cached_path(url, path_ext)
        try:
            download(client, url, dest)
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] skip %s: %s", name, url[:80], e)
            continue
        sha = content_sha256(dest)
        assets.append(FetchedAsset(
            source_type=spec["type"], source_name=name,
            target_ingestor=spec["target_ingestor"],
            url_or_path=url, cache_path=dest, content_sha256=sha,
            bytes_size=dest.stat().st_size,
            metadata={"via": "direct"},
        ))
        log_line({"ts": time.time(), "event": "fetched",
                  "source_type": spec["type"], "source_name": name,
                  "url": url, "sha256": sha, "bytes": dest.stat().st_size})
    return assets


def handle_local_dir(_client: Any, name: str, spec: dict[str, Any]) -> list[FetchedAsset]:
    """For already-downloaded assets. No network I/O."""
    assets: list[FetchedAsset] = []
    glob = spec.get("glob", "*")
    path = Path(spec.get("path", ".")).resolve()
    if not path.exists():
        log.warning("[%s] missing directory: %s", name, path)
        return assets
    # brace-glob expansion for things like "*.{jpg,jpeg,png}"
    m = re.match(r"^([^{]*)\{([^}]+)\}(.*)$", glob)
    globs = [glob]
    if m:
        pre, alts, post = m.group(1), m.group(2), m.group(3)
        globs = [f"{pre}{alt.strip()}{post}" for alt in alts.split(",")]
    files: list[Path] = []
    for g in globs:
        files.extend(path.glob(g))
    for p in sorted(files):
        sha = content_sha256(p)
        assets.append(FetchedAsset(
            source_type="local_dir", source_name=name,
            target_ingestor=spec["target_ingestor"],
            url_or_path=str(p), cache_path=p, content_sha256=sha,
            bytes_size=p.stat().st_size,
            metadata={"local_path": str(p)},
        ))
    log.info("[%s] picked up %d local files", name, len(assets))
    return assets


def handle_http_zip(client: httpx.Client, name: str, spec: dict[str, Any]) -> list[FetchedAsset]:
    """Download a zip, extract into data/fetch_cache/<url_hash>/, list files."""
    import zipfile
    url = spec.get("url")
    if not url:
        log.warning("[%s] no url configured", name)
        return []
    log.info("[%s] GET %s", name, url)
    zip_dest = cached_path(url, ".zip")
    try:
        download(client, url, zip_dest)
    except Exception as e:  # noqa: BLE001
        log.warning("[%s] download failed: %s", name, e)
        return []

    extract_dir = CACHE_DIR / (_url_hash_safe(url))
    extract_dir.mkdir(parents=True, exist_ok=True)
    if not any(extract_dir.iterdir()):
        with zipfile.ZipFile(zip_dest, "r") as z:
            z.extractall(extract_dir)
        log.info("[%s] extracted %s", name, extract_dir)

    assets: list[FetchedAsset] = []
    for p in sorted(extract_dir.rglob("*")):
        if not p.is_file():
            continue
        sha = content_sha256(p)
        assets.append(FetchedAsset(
            source_type="http_zip", source_name=name,
            target_ingestor=spec["target_ingestor"],
            url_or_path=str(p), cache_path=p, content_sha256=sha,
            bytes_size=p.stat().st_size,
            metadata={"zip_url": url, "description": spec.get("description", "")},
        ))
        log_line({"ts": time.time(), "event": "extracted",
                  "source_type": "http_zip", "source_name": name,
                  "zip_url": url, "path": str(p), "sha256": sha,
                  "bytes": p.stat().st_size})
    log.info("[%s] %d extracted files", name, len(assets))
    return assets


def _url_hash_safe(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


HANDLERS = {
    "ntrs": handle_ntrs,
    "nasa_images": handle_nasa_images,
    "direct_pdf": handle_direct,
    "direct_image": handle_direct,
    "local_dir": handle_local_dir,
    "http_zip": handle_http_zip,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch corpus assets per manifest.yml")
    parser.add_argument("--manifest", default=str(MANIFEST_PATH), help="path to manifest YAML")
    parser.add_argument("--only", default=None, help="comma-separated source names to run (default: all enabled)")
    parser.add_argument("--dry-run", action="store_true", help="print what would be fetched and exit")
    parser.add_argument("--limit", type=int, default=None,
                        help="override max_items per query (useful for a small sanity pull)")
    args = parser.parse_args(argv)

    with open(args.manifest) as f:
        manifest = yaml.safe_load(f)

    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    sources = manifest.get("sources", {})

    # --limit caps max_items across every query / urls list
    if args.limit is not None:
        log.info("applying --limit=%d to every query/url list", args.limit)
        for _name, spec in sources.items():
            if "queries" in spec:
                for q in spec["queries"]:
                    q["max_items"] = min(q.get("max_items", args.limit), args.limit)
            if "urls" in spec:
                spec["urls"] = spec["urls"][: args.limit]
    assets_all: list[FetchedAsset] = []

    with httpx.Client(headers={"User-Agent": "revvec-fetch/0.1"}) as client:
        for name, spec in sources.items():
            if only and name not in only:
                continue
            if not spec.get("enabled", False):
                log.info("[%s] disabled, skipping", name)
                continue
            handler = HANDLERS.get(spec["type"])
            if handler is None:
                log.warning("[%s] unknown source type: %s", name, spec["type"])
                continue
            if args.dry_run:
                log.info("[%s] would run handler %s", name, spec["type"])
                continue
            assets = handler(client, name, spec)
            assets_all.extend(assets)
            log.info("[%s] fetched %d assets", name, len(assets))

    by_ingestor: dict[str, int] = {}
    total_bytes = 0
    for a in assets_all:
        by_ingestor[a.target_ingestor] = by_ingestor.get(a.target_ingestor, 0) + 1
        total_bytes += a.bytes_size

    print("\n=== fetch summary ===")
    for ingestor, count in sorted(by_ingestor.items()):
        print(f"  {ingestor:10s}  {count:4d} assets")
    print(f"  total:      {total_bytes / 1024 / 1024:.1f} MB on disk, {len(assets_all)} assets")
    print(f"  manifest:   {args.manifest}")
    print(f"  cache:      {CACHE_DIR}")
    print(f"  log:        {LOG_PATH}")

    return 0 if assets_all or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
