"""
social-pulse.py — 24h 社群情報收集器
用法：
  python social-pulse.py              # 收集 + 格式化，寫入 social-pulse.json
  python social-pulse.py --dry        # 顯示內容，不寫檔

輸出：
  1. social-pulse.json（腳本目錄，供 cron 檢視）
  2. vault 50_Outputs/staging/social-pulse.json（供 content-researcher 取材）
  3. stdout：Discord 格式純文字（供 cron delivery）

每筆 item：
  { "title": "...", "url": "...", "source": "ptt|reddit|reddit_ai|web", "meta": "..." }
"""

import sys
import json
import re
import requests
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "social-pulse.json"

# Obsidian vault staging path (Windows + macOS)
VAULT_STAGING = Path("C:/Users/chimi/iCloudDrive/iCloud~md~obsidian/KM/50_Outputs/staging")
if not VAULT_STAGING.exists():
    VAULT_STAGING = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/KM/50_Outputs/staging"

FIRECRAWL_URL = "http://100.102.220.1:3002/v1/scrape"
FIRECRAWL_TIMEOUT = 25

# ── Sources ───────────────────────────────────────────────────────────────────
PTT_URL = "https://www.pttweb.cc/hot/all/today"
REDDIT_URL = "https://old.reddit.com/r/taiwan/hot/"
REDDIT_AI_QUERY = "AI agent Taiwan"
REDDIT_AI_LIMIT = 8

# ── Filters ──────────────────────────────────────────────────────────────────
# PTT boards to exclude (gossiping/moviemade/music are entertainment, not intel)
PTT_EXCLUDE_BOARDS = {"gossiping", "movie_made", "music", "job", "love", "gay", "baseball", "basketball", "Joke", "M-Market"}

# Title patterns indicating noise (bot/mod posts, UI elements)
NOISE_TITLE_PATTERNS = [
    re.compile(r'^\[公告\]'),           # PTT announcements
    re.compile(r'^\[問板\]'),           # PTT board questions
    re.compile(r'AutoModerator'),       # Reddit auto-mod posts
    re.compile(r'^\d+\s+comments$'),    # Reddit comment count line
    re.compile(r'^submitted'),          # Reddit submitted line
    re.compile(r'^self\.'),            # Reddit self post label
    re.compile(r'^i\.'),                # Reddit image label
    re.compile(r'^www\.'),             # Reddit domain label
]


def _is_noise_title(title: str) -> bool:
    """Return True if the title matches noise patterns."""
    for pat in NOISE_TITLE_PATTERNS:
        if pat.search(title):
            return True
    return False


def _is_non_article_url(url: str) -> bool:
    """Return True if the URL points to a non-article resource (image, gallery, video)."""
    lower = url.lower()
    # Image extensions
    for ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg', '.webp', '.ico'):
        if lower.endswith(ext):
            return True
    # Reddit gallery/self posts
    if '/gallery/' in lower or '/media/' in lower:
        return True
    # Reddit video embeds
    if lower.endswith('.mp4') or 'v.redd.it' in lower:
        return True
    return False


def _is_excluded_board(board_name: str) -> bool:
    """Check if board is in the exclusion list."""
    return board_name.lower() in PTT_EXCLUDE_BOARDS


def ptt_time_to_iso(raw: str) -> str:
    """Convert '5小時前, 2026/07/11 07:22' to 'YYYY-MM-DD HH:MM'."""
    match = re.match(r'(\d+)小時前,\s*(\d{4}/\d{2}/\d{2})\s+(\d{2}:\d{2})', raw)
    if match:
        hrs, date, time = match.groups()
        dt = datetime.strptime(f"{date} {time}", "%Y/%m/%d %H:%M")
        dt -= timedelta(hours=int(hrs))
        return dt.strftime("%Y-%m-%d %H:%M")
    return raw


def parse_ptt_from_markdown(text: str) -> list[dict]:
    """Parse PTT hot from firecrawl markdown."""
    items = []
    seen = set()
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if 'pttweb.cc/bbs/' in line and '\\[' in line and '/M.' in line:
            url_start = line.rfind('(http')
            if url_start > 0:
                url = line[url_start + 1:-1]
                text_left = line[:url_start]
                first_close = text_left.find(']')
                last_close = text_left.rfind(']')
                title = text_left[first_close + 1:last_close].strip()
            else:
                title, url = '', ''

            board_name, user_name, time_raw = '', '', ''
            j = i + 1
            while j < len(lines) and j < i + 8:
                l = lines[j].strip()
                if not l or l == '* * *' or l.startswith('!['):
                    j += 1
                    continue
                if 'pttweb.cc/bbs/' in l and '/M.' not in l:
                    start, end = l.find('('), l.rfind(')')
                    if start > 0 and end > start:
                        board_url = l[start + 1:end]
                        m = re.search(r'/bbs/([^/)]+)', board_url)
                        if m and not board_name:
                            board_name = m.group(1)
                if 'pttweb.cc/user/' in l:
                    start, end = l.find('('), l.rfind(')')
                    if start > 0 and end > start:
                        user_url = l[start + 1:end]
                        m = re.search(r'/user/([^/)]+)', user_url)
                        if m:
                            user_name = m.group(1)
                tm = re.match(r'(\d+小時前,\s*\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})', l)
                if tm:
                    time_raw = tm.group(1)
                j += 1

            # Skip excluded boards (gossiping, etc.)
            if _is_excluded_board(board_name):
                i += 1
                continue

            # Skip noise titles (announcements, mod posts)
            if _is_noise_title(title):
                i += 1
                continue

            # Minimum title length + uniqueness
            if board_name and time_raw and title and len(title) >= 6 and title not in seen:
                seen.add(title)
                meta = f"{board_name} · {user_name} · {ptt_time_to_iso(time_raw)}"
                items.append({"title": title, "url": url, "source": "ptt", "meta": meta})

        i += 1
    return items


def parse_reddit_from_markdown(text: str) -> list[dict]:
    """Parse Reddit hot from firecrawl markdown."""
    items = []
    seen = set()
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r'^([A-Za-z]+)\[(.+)\]\(([^)]+)\)$', line)
        if m:
            category = m.group(1)
            title = m.group(2).strip()
            url = m.group(3)

            # Skip noise titles (AutoModerator, etc.)
            if _is_noise_title(title):
                i += 1
                continue

            author, time_str = '', ''
            for j in range(i + 1, min(i + 5, len(lines))):
                l = lines[j].strip()
                if l.startswith('submitted'):
                    sm = re.search(r'submitted\s+(\d+)\s+hours?\s+ago\s+\*?\s*by\s+(\S+)', l)
                    if sm:
                        time_str = f"{sm.group(1)}h ago"
                        author = sm.group(2)
                    else:
                        sm2 = re.search(r'by\s+(\S+)', l)
                        if sm2:
                            author = sm2.group(1)
                elif l.startswith('self.') or l.startswith('i.') or l.startswith('www.'):
                    pass
                elif re.match(r'^\d+\s+comments', l):
                    pass

            # Skip if title is too short or duplicate
            if title and len(title) >= 5 and title not in seen:
                seen.add(title)
                # Normalize URL
                full_url = url if url.startswith("http") else f"https://reddit.com{url}"
                # Skip non-article URLs (images, galleries, videos)
                if _is_non_article_url(full_url):
                    continue
                meta = f"u/{author} · {time_str}" if author else ""
                items.append({
                    "title": title,
                    "url": full_url,
                    "source": "reddit",
                    "meta": meta
                })
        i += 1
    return items


def fetch_firecrawl(url: str) -> str:
    """Fetch markdown via firecrawl."""
    resp = requests.post(
        FIRECRAWL_URL,
        json={"url": url, "formats": ["markdown"]},
        timeout=FIRECRAWL_TIMEOUT,
        headers={"Content-Type": "application/json"}
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success") or not data.get("data"):
        raise RuntimeError(f"Firecrawl failed: {data}")
    return data["data"].get("markdown", "")


def fetch_reddit_ai_query(query: str, limit: int = 8) -> list[dict]:
    """Search Reddit JSON API for keyword (e.g. AI agent).

    Uses type=self to capture discussion posts, plus type=link for external links.
    """
    items = []
    seen = set()
    query_encoded = urllib.parse.quote(query)

    # Try both self posts and link posts
    for search_type in ["self", "link"]:
        url = f"https://old.reddit.com/search.json?q={query_encoded}&type={search_type}&sort=new&limit={limit}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; HermesBot/2.1; +https://woof.energy/hermes)"}

        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for child in data.get("data", {}).get("children", [])[:limit]:
                p = child.get("data")
                if p.get("domain") in ["self.taiwan", "v.redd.it", "i.redd.it"]:
                    continue
                link_url = p.get("url")
                if not link_url:
                    continue
                url_root = link_url.split("?")[0].split("#")[0]
                if url_root in seen:
                    continue
                seen.add(url_root)

                subreddit = p.get("subreddit", "")
                author = p.get("author", "")
                created_utc = p.get("created_utc", "")
                if created_utc:
                    dt = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                    time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
                else:
                    time_str = ""

                meta = f"u/{author} · r/{subreddit} · {time_str}"
                title = f"[AI agent] {p.get('title', '[Untitled]')}"
                items.append({
                    "title": title,
                    "url": link_url,
                    "source": "reddit_ai",
                    "meta": meta
                })
        except Exception:
            pass
    return items


def fetch_web_trending(limit: int = 5) -> list[dict]:
    """Use firecrawl to scrape current trending topics via Google search.

    Known limitation: firecrawl headless browser may not render Google results
    correctly, so web trending is currently best-effort and often returns empty.
    """
    items = []
    queries = [
        ("threads.net", "site:threads.net trending Taiwan 2026"),
        ("facebook.com", "site:facebook.com trending Taiwan news 2026"),
        ("instagram.com", "site:instagram.com trending Taiwan 2026"),
    ]
    for domain, query in queries:
        try:
            text = fetch_firecrawl(
                f"https://www.google.com/search?q={requests.utils.quote(query)}&hl=zh-TW"
            )
            links = re.findall(r'https?://(?:www\.)?' + re.escape(domain) + r'[^<>\s"]*', text)
            seen = set()
            for link in links[:3]:
                if link in seen or 'google.com' in link or 'search?' in link:
                    continue
                seen.add(link)
                items.append({
                    "title": f"[{domain}] {link}",
                    "url": link,
                    "source": "web",
                    "meta": f"{domain} 熱搜"
                })
        except Exception:
            pass
    return items


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove near-duplicates by URL and title similarity.

    Uses per-domain URL dedup + title prefix matching. Unlike the previous
    version that compared URL roots globally (causing over-aggressive dedup),
    this version respects that the same title from different sources is
    legitimate coverage.
    """
    seen_urls = set()
    seen_titles = set()
    result = []
    for item in items:
        # URL dedup: normalize the full path (not just domain)
        url_normalized = re.sub(r'https?://(www\.)?', '', item["url"])
        url_key = url_normalized.split('?')[0].split('#')[0].lower()

        # Title dedup: strip non-word chars, compare first 15 chars
        title_clean = re.sub(r'[^\w一-鿿]', '', item["title"])[:15]
        title_key = title_clean.lower()

        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        result.append(item)
    return result


def format_discord(items: list[dict], run_at: str) -> str:
    """Format for Discord as a clean summary with source sections."""
    lines = [
        f"\U0001f4e1 社群情報快報   {run_at[:10]}",
        "─" * 36,
    ]

    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    def render_source(name: str, label: str, icon: str):
        entries = by_source.get(name, [])
        if not entries:
            return
        lines.append(f"\n{icon} {label}（{len(entries)} 則）")
        for idx, it in enumerate(entries[:8], 1):
            title = it["title"]
            meta = it.get("meta", "").strip()
            # Clean up empty meta parts
            if meta:
                lines.append(f"  {idx}. {title}")
                lines.append(f"     {meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")

    render_source("ptt", "PTT 今日熱門（非八卦版）", "\U0001f4f6")
    render_source("reddit", "Reddit r/taiwan", "\U0001f5c0")
    render_source("reddit_ai", "Reddit AI agent 搜尋", "\U0001f916")
    render_source("web", "Threads / FB 熱搜", "\U0001f310")

    lines.append("\n" + "─" * 36)
    lines.append(f"共 {len(items)} 則情報  •  資料來源：PTT / Reddit / AI agent / 社群搜尋")

    return "\n".join(lines)


def run():
    dry = "--dry" in sys.argv
    if not dry:
        print(f"[*] social-pulse.py  ({datetime.now():%Y-%m-%d %H:%M})")

    all_items = []

    # PTT
    if not dry:
        print("[*] Fetching PTT hot...")
    try:
        text = fetch_firecrawl(PTT_URL)
        ptt_items = parse_ptt_from_markdown(text)
        if not dry:
            print(f"    -> {len(ptt_items)} PTT items (filtered)")
        all_items.extend(ptt_items)
    except Exception as e:
        if not dry:
            print(f"    [!] PTT failed: {e}")

    # Reddit r/taiwan
    if not dry:
        print("[*] Fetching Reddit r/taiwan...")
    try:
        text = fetch_firecrawl(REDDIT_URL)
        reddit_items = parse_reddit_from_markdown(text)
        if not dry:
            print(f"    -> {len(reddit_items)} Reddit items (filtered)")
        all_items.extend(reddit_items)
    except Exception as e:
        if not dry:
            print(f"    [!] Reddit failed: {e}")

    # Reddit AI agent keyword search
    if not dry:
        print("[*] Searching Reddit for AI agent...")
    try:
        ai_items = fetch_reddit_ai_query(REDDIT_AI_QUERY, limit=REDDIT_AI_LIMIT)
        if not dry:
            print(f"    -> {len(ai_items)} AI agent items")
        all_items.extend(ai_items)
    except Exception as e:
        if not dry:
            print(f"    [!] Reddit AI agent failed: {e}")

    # Web trending (best-effort, often empty)
    if not dry:
        print("[*] Fetching web trending...")
    try:
        web_items = fetch_web_trending()
        if not dry:
            print(f"    -> {len(web_items)} web items")
        all_items.extend(web_items)
    except Exception as e:
        if not dry:
            print(f"    [!] Web failed: {e}")

    # Deduplicate
    unique = deduplicate(all_items)
    if not dry:
        print(f"[*] After dedup: {len(unique)} items (removed {len(all_items) - len(unique)})")

    run_at = datetime.now().strftime("%Y-%m-%dT%H:%M")

    discord_text = format_discord(unique, run_at)
    output = {
        "run_at": run_at,
        "sources": {
            "ptt": [i for i in unique if i["source"] == "ptt"],
            "reddit": [i for i in unique if i["source"] == "reddit"],
            "reddit_ai": [i for i in unique if i["source"] == "reddit_ai"],
            "web": [i for i in unique if i["source"] == "web"],
        },
        "total": len(unique),
        "discord_message": discord_text,
    }

    # 1. Write JSON to script directory (for debugging)
    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 2. Write JSON to vault staging (for content-researcher to pick up)
    try:
        VAULT_STAGING.mkdir(parents=True, exist_ok=True)
        vault_output = VAULT_STAGING / "social-pulse.json"
        vault_output.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        if not dry:
            print(f"[*] Vault copy → {vault_output}")
    except Exception as e:
        if not dry:
            print(f"[!] Vault write failed: {e}")

    # 3. Print Discord message to stdout for cron delivery
    print(discord_text)

    return output


if __name__ == "__main__":
    run()
