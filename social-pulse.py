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
from typing import Optional

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
REDDIT_BUSINESS_SUBREDDITS = [
    "Entrepreneur",
    "ecommerce",
    "marketing",
    "productivity",
]
REDDIT_AI_QUERY = "AI agent Taiwan"
REDDIT_AI_LIMIT = 8

# AI HOT API configuration
AIHOT_BASE = "https://aihot.virxact.com"
AIHOT_UA = "social-pulse/1.0"
AIHOT_FINGERPRINT_URL = f"{AIHOT_BASE}/api/public/fingerprint"
AIHOT_ITEMS_URL = f"{AIHOT_BASE}/api/public/items"
AIHOT_HOT_TOPICS_URL = f"{AIHOT_BASE}/api/public/hot-topics"
AIHOT_TIMEOUT = 25

# ── Filters ──────────────────────────────────────────────────────────────────
# PTT boards to exclude (gossiping/moviemade/music are entertainment, not intel)
# SportLottery = sports betting, not useful for intelligence gathering
# LoL/NBA/Baseball/Basketball = sports/esports entertainment
PTT_EXCLUDE_BOARDS = {"gossiping", "movie_made", "music", "job", "love", "gay", "baseball", "basketball", "Joke", "M-Market", "sportlottery", "lol", "nba"}

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

# Patterns to skip live sports broadcasts and similar noise
LIVE_BROADCAST_PATTERNS = [
    re.compile(r'\\?\[LIVE\\?\]', re.IGNORECASE),   # PTT LIVE直播 (escaped or not)
    re.compile(r'LIVE\s+', re.IGNORECASE),           # LIVE at start
]

# Reddit authors that are not real discussion participants
NOISE_AUTHORS = {"AutoModerator", "moderator", "Mod_Support", "stickymod"}

# Reddit title patterns that indicate personal classifieds, not discussion/intel
REDDIT_NOISE_PATTERNS = [
    re.compile(r'^Looking\s+for\b', re.IGNORECASE),      # 個人徵文/尋找
    re.compile(r'^Hiring\b', re.IGNORECASE),              # 招聘（不是產業分析）
    re.compile(r'^Moving\s+to\b', re.IGNORECASE),         # 搬家/移居個人分享
    re.compile(r'^Considering\s+Moving\b', re.IGNORECASE), # 考慮搬遷個人分享
    re.compile(r'^Dating\s+with\b', re.IGNORECASE),       # 約會徵文
    re.compile(r'^Check\s+your\b', re.IGNORECASE),        # 個人通知
    re.compile(r'^Tennis\b', re.IGNORECASE),              # 課程徵文
    re.compile(r'^Wanted\b', re.IGNORECASE),              # 求購
    re.compile(r'^For\s+sale\b', re.IGNORECASE),          # 出售
    re.compile(r'^Need\b', re.IGNORECASE),                # 需求個人
    re.compile(r'^Help\b', re.IGNORECASE),                # 求助個人
    re.compile(r'^lash\s+lift\b', re.IGNORECASE),         # 美容廣告
    re.compile(r'Lessons\s+with\b', re.IGNORECASE),       # 課程廣告
    re.compile(r'Looking\s+for\s+\d', re.IGNORECASE),     # 徵文/找人（含數字）
    re.compile(r'^Guys\s+do\s+you\b', re.IGNORECASE),     # 個人提問
    re.compile(r'^Would\s+any\b', re.IGNORECASE),         # 個人提問
    re.compile(r'^When\s+is\s+it\b', re.IGNORECASE),      # 個人提問
    re.compile(r'^What\s+yall\b', re.IGNORECASE),         # 個人提問
    re.compile(r'^Is\s+there\b', re.IGNORECASE),          # 個人提問
    re.compile(r'^Advice\s+on\b', re.IGNORECASE),         # 個人諮詢建議
    re.compile(r'^\w+\s+for\s+\w+\?$', re.IGNORECASE),    # 短提問如 "Heels for Men?"
    re.compile(r'^How\s+is\s+\w+\??$', re.IGNORECASE),    # 個人提問（How is X?）
    re.compile(r'^Can\s+anyone\s+recommend\b', re.IGNORECASE),  # 個人推薦需求
    re.compile(r'^Has\s+anyone\s+here\b', re.IGNORECASE), # 個人經驗提問
    re.compile(r'^Making\s+friends\b', re.IGNORECASE),    # 交友徵文
    re.compile(r'^Culture\s+Shock\b', re.IGNORECASE),     # 個人文化衝擊分享
    re.compile(r'^Foreigners\s+who\s+visited\b', re.IGNORECASE), # 個人體驗分享
]


def _clean_ptt_title(title: str) -> str:
    """Strip PTT classification tags from title.

    PTT hot page prepends tags like \\[新聞\\], \\[電競\\], \\[發錢\\], \\[推薦\\].
    These are PTT's internal classification, not part of the real title.
    """
    # Remove escaped bracket tags at the start: \\[新聞\\], \\[電競\\], etc.
    cleaned = re.sub(r'^\\?\\[[^\\]]+\\]\\s*', '', title)
    # Also handle unescaped versions
    cleaned = re.sub(r'^\[[^]]+\]\s*', '', cleaned)
    return cleaned.strip()


def _is_live_broadcast(title: str) -> bool:
    """Return True if the title looks like a live sports broadcast."""
    for pat in LIVE_BROADCAST_PATTERNS:
        if pat.search(title):
            return True
    return False


def _is_noise_author(author: str) -> bool:
    """Return True if the author is a known noise bot/mod.

    Handles both plain usernames and markdown links like [AutoModerator](...).
    """
    cleaned = re.sub(r'\[', '', author).split(']')[0].strip()
    return cleaned in NOISE_AUTHORS


def _is_reddit_classified(title: str) -> bool:
    """Return True if the title looks like a personal classified/posting."""
    for pat in REDDIT_NOISE_PATTERNS:
        if pat.search(title):
            return True
    return False


def _is_noise_title(title: str) -> bool:
    """Return True if the title matches noise patterns."""
    for pat in NOISE_TITLE_PATTERNS:
        if pat.search(title):
            return True
    return False


def _is_non_article_url(url: str) -> bool:
    """Return True if the URL points to a non-article resource (image, gallery, video, podcast)."""
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
    # External services (podcasts, etc.)
    if 'open.spotify.com' in lower or 'soundcloud.com' in lower:
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

            # Clean PTT classification tags from title
            title = _clean_ptt_title(title)

            # Skip noise titles (announcements, mod posts, live broadcasts)
            if _is_noise_title(title) or _is_live_broadcast(title):
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
            if title and len(title) >= 10 and title not in seen:
                seen.add(title)
                # Normalize URL
                full_url = url if url.startswith("http") else f"https://reddit.com{url}"
                # Skip non-article URLs (images, galleries, videos)
                if _is_non_article_url(full_url):
                    continue
                # Skip AutoModerator and other noise authors
                if _is_noise_author(author):
                    continue
                # Skip personal classifieds (Looking for, hiring, moving, etc.)
                if _is_reddit_classified(title):
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


def fetch_aihot_fingerprint() -> Optional[str]:
    """Fetch lightweight freshness fingerprint for cron monitoring.

    Returns the fingerprint hash, or None on error.
    """
    try:
        resp = requests.get(AIHOT_FINGERPRINT_URL, timeout=AIHOT_TIMEOUT)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    return None


def fetch_aihot_selected(since_hours: int = 24, take: int = 50) -> list[dict]:
    """Fetch AI HOT selected items from the past N hours.

    Mirrors aihot's core approach: public API, no key needed,
    curated/selected items with LLM-generated summaries and scores.
    """
    items = []
    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(hours=since_hours)
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    url = f"{AIHOT_ITEMS_URL}?mode=selected&since={since_iso}&take={take}"
    headers = {"User-Agent": AIHOT_UA}

    try:
        resp = requests.get(url, headers=headers, timeout=AIHOT_TIMEOUT)
        if resp.status_code != 200:
            return items
        data = resp.json()
        for item in data.get("items", []):
            title = item.get("title", "")
            if not title:
                continue
            # Skip noise titles
            if _is_noise_title(title):
                continue

            permalink = item.get("permalink", "")
            url_val = item.get("url", "")
            source = item.get("source", "")
            published_at = item.get("publishedAt", "")
            summary = item.get("summary", "")
            category = item.get("category", "")
            score = item.get("score")

            # Convert publishedAt to Taipei time string
            time_str = ""
            if published_at:
                try:
                    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    dt_taipei = dt.astimezone(timezone(timedelta(hours=8)))
                    time_str = dt_taipei.strftime("%Y-%m-%d %H:%M 台北")
                except Exception:
                    time_str = published_at[:16]

            # Category label mapping
            cat_labels = {
                "ai-models": "模型",
                "ai-products": "產品",
                "industry": "產業",
                "paper": "論文",
                "tip": "技巧",
            }
            cat_label = cat_labels.get(category, category or "")
            meta_parts = []
            if cat_label:
                meta_parts.append(cat_label)
            if score is not None:
                meta_parts.append(f"score:{score}")
            if source:
                meta_parts.append(source)
            meta = " · ".join(meta_parts)

            # Use permalink (Chinese translated reading page) as primary URL
            display_url = permalink or url_val

            items.append({
                "title": title,
                "url": display_url,
                "source": "aihot",
                "meta": meta,
                "summary": summary,
                "category": category,
                "score": score,
            })
    except Exception:
        pass
    return items


def fetch_aihot_hot_topics(take: int = 10) -> list[dict]:
    """Fetch current hot topics sorted by multi-source heat count.

    Complements selected items — these are what's trending RIGHT NOW
    across multiple independent sources, not just newest publications.
    """
    items = []
    headers = {"User-Agent": AIHOT_UA}

    try:
        resp = requests.get(AIHOT_HOT_TOPICS_URL, headers=headers, timeout=AIHOT_TIMEOUT)
        if resp.status_code != 200:
            return items
        data = resp.json()
        for item in data.get("items", [])[:take]:
            title = item.get("title", "")
            if not title or _is_noise_title(title):
                continue

            permalink = item.get("permalink", "")
            url_val = item.get("url", "")
            source = item.get("source", "")
            source_count = item.get("sourceCount", 0)
            published_at = item.get("publishedAt", "")

            # Convert time
            time_str = ""
            if published_at:
                try:
                    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    dt_taipei = dt.astimezone(timezone(timedelta(hours=8)))
                    time_str = dt_taipei.strftime("%Y-%m-%d %H:%M 台北")
                except Exception:
                    time_str = published_at[:16]

            meta = f"熱度:{source_count} 來源"
            if source:
                meta += f" · {source}"

            display_url = permalink or url_val
            items.append({
                "title": title,
                "url": display_url,
                "source": "aihot_hot",
                "meta": meta,
                "summary": item.get("summary", ""),
                "category": item.get("category", ""),
                "score": item.get("score"),
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
            links = re.findall(r'https?://(?:www\.)?' + re.escape(domain) + r'[^<>\s"&]*', text)
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


def _render_business_reddit(lines, by_source, label, icon):
    """Render Reddit business subreddits section."""
    entries = by_source.get(label, [])
    if not entries:
        return
    lines.append(f"\n{icon} {label}（{len(entries)} 則）")
    for idx, it in enumerate(entries[:8], 1):
        title = it["title"]
        meta = it.get("meta", "").strip()
        if meta:
            lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
        else:
            lines.append(f"  {idx}. {title}  —  {it['url']}")


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
            if meta:
                lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")

    render_source("ptt", "PTT 今日熱門（非八卦版）", "\U0001f4f6")

    # Business subreddits
    for sub in REDDIT_BUSINESS_SUBREDDITS:
        _render_business_reddit(lines, by_source, sub, "\U0001f4bc")

    # AI HOT — hot topics first (trending now), then selected items
    hot_entries = by_source.get("aihot_hot", [])
    if hot_entries:
        lines.append(f"\n\U0001f525 當前 AI 熱點（多源熱度）（{len(hot_entries)} 則）")
        for idx, it in enumerate(hot_entries[:5], 1):
            title = it["title"]
            meta = it.get("meta", "")
            if meta:
                lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")

    aihot_entries = by_source.get("aihot", [])
    if aihot_entries:
        lines.append(f"\n\U0001f916 AI HOT 精選（過去 24h）（{len(aihot_entries)} 則）")
        for idx, it in enumerate(aihot_entries[:10], 1):
            title = it["title"]
            meta = it.get("meta", "")
            summary = it.get("summary", "")
            display_meta = meta
            if summary and len(summary) > 5:
                display_meta = f"{summary[:80]}{'...' if len(summary) > 80 else ''}"
                if meta:
                    display_meta += f" · {meta}"
            if display_meta:
                lines.append(f"  {idx}. {title}  —  {display_meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")

    render_source("reddit_ai", "Reddit AI agent 搜尋", "\U0001f916")
    render_source("web", "Threads / FB 熱搜", "\U0001f310")

    lines.append("\n" + "─" * 36)
    lines.append(f"共 {len(items)} 則情報  •  資料來源：PTT / Reddit / AI HOT / AI agent / 社群搜尋")

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

    # Reddit business subreddits (Entrepreneur, ecommerce, marketing, productivity)
    for sub in REDDIT_BUSINESS_SUBREDDITS:
        if not dry:
            print(f"[*] Fetching r/{sub}...")
        try:
            url = f"https://old.reddit.com/r/{sub}/hot/"
            text = fetch_firecrawl(url)
            sub_items = parse_reddit_from_markdown(text)
            # Tag with subreddit name in meta
            for item in sub_items:
                item["meta"] = f"r/{sub} · {item['meta']}"
            if not dry:
                print(f"    -> {len(sub_items)} r/{sub} items (filtered)")
            all_items.extend(sub_items)
        except Exception as e:
            if not dry:
                print(f"    [!] r/{sub} failed: {e}")

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

    # AI HOT — curated AI news with LLM summaries and scores
    if not dry:
        print("[*] Fetching AI HOT selected...")
    try:
        aihot_items = fetch_aihot_selected(since_hours=24, take=50)
        if not dry:
            print(f"    -> {len(aihot_items)} AI HOT items")
        all_items.extend(aihot_items)
    except Exception as e:
        if not dry:
            print(f"    [!] AI HOT selected failed: {e}")

    # AI HOT hot topics — multi-source trending right now
    if not dry:
        print("[*] Fetching AI HOT hot topics...")
    try:
        hot_items = fetch_aihot_hot_topics(take=10)
        if not dry:
            print(f"    -> {len(hot_items)} AI HOT hot topics")
        all_items.extend(hot_items)
    except Exception as e:
        if not dry:
            print(f"    [!] AI HOT hot topics failed: {e}")

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
            **{sub: [i for i in unique if i["meta"].startswith(f"r/{sub}")] for sub in REDDIT_BUSINESS_SUBREDDITS},
            "aihot": [i for i in unique if i["source"] == "aihot"],
            "aihot_hot": [i for i in unique if i["source"] == "aihot_hot"],
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
