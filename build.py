#!/usr/bin/env python3
"""Scrape devfestka.de (schedule + talks + speaker photos) and render index.html from template.html.

Run locally or from the GitHub Action. Rewrites index.html only when the data or the template changed,
and exits non-zero if the scrape looks broken, so a bad scrape never replaces a good page.
"""
import hashlib, html, io, json, os, re, sys, urllib.request
from datetime import datetime, timezone

SITE = "https://devfestka.de"
ROOT = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "devfestka-2026-schedule-sync"}

def get(path, binary=False):
    with urllib.request.urlopen(urllib.request.Request(SITE + path, headers=UA), timeout=30) as r:
        b = r.read()
    return b if binary else b.decode("utf8")

def clean(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r' _ng(?:content|host)-[a-z0-9-]+=""', "", s)
    return re.sub(r' class="([^"]*)"', lambda m: ' class="' + " ".join(c for c in m.group(1).split() if not c.startswith("ng-")) + '"', s)

txt = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
key = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())[:18]

def hm(chunk, which):
    m = re.search(r'class="%s"><span class="hours">(\d+)</span><span class="minutes">(\d+)</span>' % which, chunk)
    return f"{int(m[1]):02d}:{m[2]}" if m else None

def parse_schedule(page):
    grid = clean(page).split('<div class="schedule-grid">', 1)[1]
    sessions = []
    for chunk in grid.split('<div class="time">')[1:]:
        s, e = hm(chunk, "start"), hm(chunk, "end")
        parts = re.split(r'<div class="session((?: [a-z ]+)?)">', chunk)
        for cls, sess in zip(parts[1::2], parts[2::2]):
            title = txt(re.search(r'class="session-title">(.*?)</h3>', sess, re.S)[1])
            lang = "EN" if 'class="language">EN<' in sess else "DE"
            foot = sess.split('class="session-footer"', 1)[1] if 'class="session-footer"' in sess else ""
            room = re.search(r'class="session-meta"><span class="">(.*?)</span>', foot)
            room = txt(room[1]) if room else ""
            tags = [txt(t) for t in re.findall(r'class="tag"[^>]*>(.*?)</span>', sess)]
            who = [(txt(n), txt(co), src) for _alt, src, n, co in re.findall(
                r'alt="([^"]*)"[^>]*src="(/assets/speakers/[^"]+)".*?class="speaker-name">(.*?)</div><div class="speaker-title">(.*?)</div>', sess, re.S)]
            icon = re.search(r'data-mat-icon-type="font"[^>]*>([a-z_]+)<', sess)
            sessions.append(dict(s=s, e=e, title=title, lang=lang, room=room, tags=tags, who=who,
                                 full="fullwidth" in cls, icon=icon[1] if icon else ""))
    return sessions

def parse_talks(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", clean(page), flags=re.S)
    t = re.sub(r"<(br|/p|/h\d|/div|/li)[^>]*>", "\n", t)
    lines = [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "", t)).split("\n")]
    idx = [i for i, l in enumerate(lines) if l.endswith("expand_more")]
    out = {}
    for n, i in enumerate(idx):
        end = idx[n + 1] - 1 if n + 1 < len(idx) else len(lines)
        desc = "\n".join(x for x in lines[i + 2:end] if x)
        desc = re.split(r"\n?GDG Karlsruhe\s*\n?Impressum", desc)[0].strip()
        out[key(lines[i - 1])] = desc
    return out

def photo(src):
    """Local 160px copy of a speaker photo; downloads only photos we don't have yet."""
    name = os.path.basename(src)
    dst = os.path.join(ROOT, "speakers", name)
    if not os.path.exists(dst):
        raw = get(src, binary=True)
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(raw)).convert("RGB"); w, h = im.size; s = min(w, h)
            im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((160, 160), Image.LANCZOS)
            os.makedirs(os.path.dirname(dst), exist_ok=True); im.save(dst, "WEBP", quality=80)
        except ImportError:  # ponytail: no Pillow -> keep the full-size original
            open(dst, "wb").write(raw)
    return "speakers/" + name

def build():
    sessions = parse_schedule(get("/schedule"))
    descs = parse_talks(get("/talks"))
    if len(sessions) < 10 or sum(1 for s in sessions if not s["full"]) < 6:
        sys.exit(f"scrape looks broken: {len(sessions)} sessions")  # keep the last good page

    rooms = []
    for s in sessions:
        if not s["full"] and s["room"] not in rooms: rooms.append(s["room"])
    rooms.sort(key=lambda r: (r != "Audimax", r))

    talks, ids = [], set()
    for s in sessions:
        title = re.sub(r"^Keynote:\s*", "", s["title"])
        title = re.sub(r"\s*\(EN\)$", "", title)
        if s["full"]:
            kind = "key" if s["who"] else ("brk" if s["room"] == "Foyer" else "plen")
        else:
            kind = "talk"
        end = s["e"]
        if not end:  # open end (networking): show an hour
            h, m = map(int, s["s"].split(":")); end = f"{h + 1:02d}:{m:02d}"
        ev = {"s": s["s"], "e": end, "c": -1 if s["full"] else rooms.index(s["room"]), "t": title, "k": kind}
        if kind in ("talk", "key"):
            # stable id from the speakers' photo names, so a pick follows the talk if its time or room changes
            tid = "_".join(os.path.splitext(os.path.basename(src))[0] for _, _, src in s["who"]) or key(title)
            while tid in ids: tid += "x"
            ids.add(tid)
            ev |= {"id": tid, "l": s["lang"], "g": ", ".join(s["tags"]), "d": descs.get(key(title), ""),
                   "who": [[n, co, photo(src)] for n, co, src in s["who"]]}
        else:
            ev["sp"] = s["room"] + ("" if s["e"] else " · open end")
        talks.append(ev)

    tpl = open(os.path.join(ROOT, "template.html"), encoding="utf8").read()
    digest = hashlib.sha256((json.dumps(talks, ensure_ascii=False) + tpl).encode()).hexdigest()[:12]
    out_path = os.path.join(ROOT, "index.html")
    if os.path.exists(out_path) and f'"hash": "{digest}"' in open(out_path, encoding="utf8").read():
        print("unchanged", digest); return
    meta = {"hash": digest, "rooms": rooms, "synced": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    page = tpl.replace("__DATA__", json.dumps(talks, ensure_ascii=False)).replace("__META__", json.dumps(meta))
    open(out_path, "w", encoding="utf8").write(page)
    print("updated", digest, len(talks), "items")

if __name__ == "__main__":
    build()
