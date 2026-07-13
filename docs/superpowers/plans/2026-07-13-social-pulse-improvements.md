# Social Pulse 報告改良 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove r/taiwan source, unify Discord formatting to single-line, add traditional Chinese translation at output time.

**Architecture:** Single-file modification of `social-pulse.py`. No new files needed. The script already uses `opencc-python-reimplemented` in the environment, so no dependency installation required.

**Tech Stack:** Python 3.14+, opencc-python-reimplemented (already installed), requests (stdlib-ish)

## Global Constraints

- Single-file script: `social-pulse.py` — follow existing patterns, don't refactor unrelated code
- No external LLM API calls for sentiment — sentiment is handled by downstream AI Agent
- Translation only at output time (Discord text), raw JSON preserves original text
- Use `opencc-python-reimplemented` for Simplified→Traditional conversion
-台北時間 dates, UTC+8

---

### Task 1: Remove r/taiwan source

**Files:**
- Modify: `social-pulse.py`

**Interfaces:**
- Consumes: None
- Produces: No more `REDDIT_URL` constant, no r/taiwan fetch block in `run()`

**Steps:**

- [ ] **Step 1: Remove `REDDIT_URL` constant and the r/taiwan fetch block**

In `social-pulse.py`, remove line 39:
```python
REDDIT_URL = "https://old.reddit.com/r/taiwan/hot/"
```

And remove lines 705-716 (the r/taiwan fetch block in `run()`):
```python
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
```

Also remove the `render_source("reddit", "Reddit r/taiwan", ...)` call in `format_discord()` around line 648.

- [ ] **Step 2: Verify the script still runs**

Run: `python social-pulse.py --dry`

Expected: Script runs without `NameError` for `REDDIT_URL`, output contains PTT, business subreddits, AI HOT, AI agent, web sections but NO r/taiwan section.

- [ ] **Step 3: Commit**

```bash
git add social-pulse.py
git commit -m "refactor: remove r/taiwan source from social pulse"
```

---

### Task 2: Unify Discord formatting to single-line

**Files:**
- Modify: `social-pulse.py`

**Interfaces:**
- Consumes: Existing `format_discord()` and `_render_business_reddit()` functions
- Produces: All items display as single line: `#. 標題  —  meta — url`

**Steps:**

- [ ] **Step 1: Replace two-line format with single-line in `format_discord()`**

Replace lines 637-645 in `render_source()` function:
```python
        for idx, it in enumerate(entries[:8], 1):
            title = it["title"]
            meta = it.get("meta", "").strip()
            # Clean up empty meta parts
            if meta:
                lines.append(f"  {idx}. {title}")
                lines.append(f"     {meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")
```

With:
```python
        for idx, it in enumerate(entries[:8], 1):
            title = it["title"]
            meta = it.get("meta", "").strip()
            if meta:
                lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")
```

- [ ] **Step 2: Replace two-line format with single-line in `_render_business_reddit()`**

Replace lines 611-618:
```python
    for idx, it in enumerate(entries[:8], 1):
        title = it["title"]
        meta = it.get("meta", "").strip()
        if meta:
            lines.append(f"  {idx}. {title}")
            lines.append(f"     {meta}  —  {it['url']}")
        else:
            lines.append(f"  {idx}. {title}  —  {it['url']}")
```

With:
```python
    for idx, it in enumerate(entries[:8], 1):
        title = it["title"]
        meta = it.get("meta", "").strip()
        if meta:
            lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
        else:
            lines.append(f"  {idx}. {title}  —  {it['url']}")
```

- [ ] **Step 3: Replace two-line format in AI HOT sections**

Lines 658-662 (aihot_hot section):
```python
        for idx, it in enumerate(hot_entries[:5], 1):
            title = it["title"]
            meta = it.get("meta", "")
            lines.append(f"  {idx}. {title}")
            lines.append(f"     {meta}  —  {it['url']}")
```

With:
```python
        for idx, it in enumerate(hot_entries[:5], 1):
            title = it["title"]
            meta = it.get("meta", "")
            if meta:
                lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")
```

Lines 667-674 (aihot section):
```python
        for idx, it in enumerate(aihot_entries[:10], 1):
            title = it["title"]
            meta = it.get("meta", "")
            summary = it.get("summary", "")
            lines.append(f"  {idx}. {title}")
            if summary and len(summary) > 5:
                lines.append(f"     {summary[:80]}{'...' if len(summary) > 80 else ''}")
            lines.append(f"     {meta}  —  {it['url']}")
```

With:
```python
        for idx, it in enumerate(aihot_entries[:10], 1):
            title = it["title"]
            meta = it.get("meta", "")
            summary = it.get("summary", "")
            if summary and len(summary) > 5:
                meta = f"{summary[:80]}{'...' if len(summary) > 80 else ''} {meta}".strip()
            parts = [title]
            if meta:
                parts.extend(["—", meta])
            parts.extend(["—", it["url"]])
            lines.append(f"  {idx}. {'  '.join(parts)}")
```

Actually, let me keep it simpler to match the single-line pattern:
```python
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
```

- [ ] **Step 4: Verify the script still runs**

Run: `python social-pulse.py --dry`

Expected: All items display on a single line with consistent `#. 標題  —  meta — url` format. No two-line entries.

- [ ] **Step 5: Commit**

```bash
git add social-pulse.py
git commit -m "refactor: unify discord formatting to single-line for all sources"
```

---

### Task 3: Add traditional Chinese translation at output time

**Files:**
- Modify: `social-pulse.py`

**Interfaces:**
- Consumes: `opencc` package (already installed: `opencc-python-reimplemented`)
- Produces: `translate_to_zh_tw(text)` function that converts Simplified Chinese to Traditional Chinese

**Steps:**

- [ ] **Step 1: Add translation helper function**

Add after the imports (around line 24), before the constants:

```python
# ── Translation ───────────────────────────────────────────────────────────────
try:
    from opencc import OpenCC
    _cc_t2s = OpenCC("s2t")  # Simplified → Traditional
except ImportError:
    _cc_t2s = None


def translate_to_zh_tw(text: str) -> str:
    """Convert Simplified Chinese to Traditional Chinese.

    Falls back to identity (no-op) if opencc is not available.
    Only translates strings; leaves URLs, numbers, and English text intact.
    """
    if not text or not _cc_t2s:
        return text
    try:
        return _cc_t2s.convert(text)
    except Exception:
        return text
```

- [ ] **Step 2: Apply translation in `format_discord()`**

In the `format_discord()` function, wrap all title and meta strings that go into Discord output with `translate_to_zh_tw()`. Specifically, in `render_source()`:

```python
    def render_source(name: str, label: str, icon: str):
        entries = by_source.get(name, [])
        if not entries:
            return
        lines.append(f"\n{icon} {translate_to_zh_tw(label)}（{len(entries)} 則）")
        for idx, it in enumerate(entries[:8], 1):
            title = translate_to_zh_tw(it["title"])
            meta = translate_to_zh_tw(it.get("meta", "")).strip()
            if meta:
                lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")
```

Similarly in `_render_business_reddit()`:

```python
def _render_business_reddit(lines, by_source, label, icon):
    entries = by_source.get(label, [])
    if not entries:
        return
    lines.append(f"\n{icon} {translate_to_zh_tw(label)}（{len(entries)} 則）")
    for idx, it in enumerate(entries[:8], 1):
        title = translate_to_zh_tw(it["title"])
        meta = translate_to_zh_tw(it.get("meta", "")).strip()
        if meta:
            lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
        else:
            lines.append(f"  {idx}. {title}  —  {it['url']}")
```

And in the AI HOT sections (lines 654-674 area):

```python
    hot_entries = by_source.get("aihot_hot", [])
    if hot_entries:
        lines.append(f"\n\U0001f525 當前 AI 熱點（多源熱度）（{len(hot_entries)} 則）")
        for idx, it in enumerate(hot_entries[:5], 1):
            title = translate_to_zh_tw(it["title"])
            meta = translate_to_zh_tw(it.get("meta", ""))
            if meta:
                lines.append(f"  {idx}. {title}  —  {meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")

    aihot_entries = by_source.get("aihot", [])
    if aihot_entries:
        lines.append(f"\n\U0001f916 AI HOT 精選（過去 24h）（{len(aihot_entries)} 則）")
        for idx, it in enumerate(aihot_entries[:10], 1):
            title = translate_to_zh_tw(it["title"])
            meta = translate_to_zh_tw(it.get("meta", ""))
            summary = translate_to_zh_tw(it.get("summary", ""))
            display_meta = meta
            if summary and len(summary) > 5:
                display_meta = f"{summary[:80]}{'...' if len(summary) > 80 else ''}"
                if meta:
                    display_meta += f" · {meta}"
            if display_meta:
                lines.append(f"  {idx}. {title}  —  {display_meta}  —  {it['url']}")
            else:
                lines.append(f"  {idx}. {title}  —  {it['url']}")
```

- [ ] **Step 3: Verify the script still runs**

Run: `python social-pulse.py --dry`

Expected: Script runs successfully. Any Simplified Chinese titles should now appear in Traditional Chinese. URLs and English text should remain unchanged.

- [ ] **Step 4: Commit**

```bash
git add social-pulse.py
git commit -m "feat: add traditional chinese translation at discord output time"
```

---

## Summary of Changes

| File | Change |
|---|---|
| `social-pulse.py` | Remove `REDDIT_URL` + r/taiwan fetch block + render call |
| `social-pulse.py` | Unify all `format_discord()` single-line format |
| `social-pulse.py` | Add `translate_to_zh_tw()` using opencc, apply at output time |

## Testing

Manual verification via `python social-pulse.py --dry` after each task. No automated tests exist in this project.
