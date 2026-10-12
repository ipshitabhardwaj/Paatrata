"""Download openly licensed photos of Chandigarh from Wikimedia Commons for the landing page.

Run once on a machine with internet (from the repo root or anywhere):

    python web/scripts/get_photos.py

For each subject below it searches Wikimedia Commons, keeps only landscape JPEGs at least 1600 px
wide under CC0 / public domain / CC BY / CC BY-SA, downloads a 2000 px copy into web/public/photos/,
and records the author, licence and source page in web/public/photos/photos.json. The page shows
that credit under every photo. Open each source link once to confirm you are happy with the pick;
delete a file's entry from photos.json (and the .jpg) to drop it, or set "pin" titles below.

Standard library only. Wikimedia asks API users to send a descriptive User-Agent; set
PAATRATA_CONTACT to your email to include it.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
OUT = Path(__file__).resolve().parents[1] / "public" / "photos"
UA = f"PaatrataHackathon/0.1 (open-source civic project; {os.environ.get('PAATRATA_CONTACT', 'no contact set')})"
ALLOWED = ("cc0", "public domain", "pd", "cc by", "cc-by")

# (slug, search terms, optional pinned File: title to try first, caption for the page)
SUBJECTS = [
    ("capitol", "Palace of Assembly Chandigarh", "File:Palace of Assembly Chandigarh 2006.jpg",
     "Palace of Assembly, Capitol Complex"),
    ("secretariat", "Secretariat Building Chandigarh Le Corbusier", None, "Secretariat, Capitol Complex"),
    ("open-hand", "Open Hand Monument Chandigarh", None, "Open Hand Monument"),
    ("sukhna", "Sukhna Lake Chandigarh", None, "Sukhna Lake"),
    ("rock-garden", "Rock Garden of Chandigarh", None, "Rock Garden"),
    ("sector-17", "Sector 17 Chandigarh plaza", None, "Sector 17"),
]


def api(params: dict) -> dict:
    q = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def plain(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", html or ""))).strip()


def candidates(search: str, pinned: str | None) -> list[dict]:
    common = {"action": "query", "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": "2000"}
    pages = []
    if pinned:
        pages += api({**common, "titles": pinned}).get("query", {}).get("pages", [])
    res = api({**common, "generator": "search", "gsrsearch": search, "gsrnamespace": "6", "gsrlimit": "15"})
    pages += sorted(res.get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))
    return pages


def acceptable(page: dict) -> dict | None:
    info = (page.get("imageinfo") or [None])[0]
    if not info or info.get("mime") != "image/jpeg":
        return None
    w, h = info.get("width", 0), info.get("height", 0)
    if w < 1600 or w <= h:
        return None
    meta = info.get("extmetadata", {})
    lic = plain(meta.get("LicenseShortName", {}).get("value", ""))
    if not lic.lower().startswith(ALLOWED):
        return None
    return {
        "title": page["title"],
        "thumb": info.get("thumburl") or info["url"],
        "author": plain(meta.get("Artist", {}).get("value", "")) or "Unknown author",
        "license": lic,
        "license_url": meta.get("LicenseUrl", {}).get("value", ""),
        "source": info.get("descriptionurl", ""),
        "width": w, "height": h,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for slug, search, pinned, caption in SUBJECTS:
        try:
            pick = next((a for a in map(acceptable, candidates(search, pinned)) if a), None)
        except Exception as e:  # network or API problem: skip this subject
            print(f"  {slug}: search failed ({e})")
            continue
        if not pick:
            print(f"  {slug}: no suitable freely licensed landscape photo found")
            continue
        dest = OUT / f"{slug}.jpg"
        req = urllib.request.Request(pick["thumb"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        manifest.append({"slug": slug, "file": f"/photos/{slug}.jpg", "caption": caption, **pick})
        print(f"  {slug}: {pick['title']}  ({pick['license']}, {pick['author']})")
        time.sleep(1)  # be polite to the API
    (OUT / "photos.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(manifest)} photo(s) and credits to {OUT}. Check each source link before you present.")
    return 0 if manifest else 1


if __name__ == "__main__":
    sys.exit(main())
