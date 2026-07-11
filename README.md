# social-pulse

```
hermes scripts/cron → vault 50_Outputs/staging/ → content-researcher 取材
                   ↘ Discord Home 頻道（每日快報）
```

**運作方式：**
- 每日 07:00 台北時間由 hermes cron 執行 social-pulse.py
- 抓取 PTT 熱門、Reddit r/taiwan、Reddit AI agent 關鍵字
- 去重後輸出三份：Discord 快報、script 目錄 JSON、vault staging JSON

**歸屬：** 獨立 repo，不屬於 llm-zettel-wiki-km

**consumers：**
- Discord 頻道（直接送純文字快報）
- content-researcher skill（從 vault staging 讀取 JSON 做選題參考）

**資料流程：**
1. PTT (firecrawl pttweb.cc) → markdown parse
2. Reddit r/taiwan (firecrawl old.reddit.com) → markdown parse
3. Reddit AI agent keyword (Reddit JSON API search)
4. Web trending (firecrawl Google search, best-effort)
5. 去重 (URL root + title prefix)
6. → stdout (Discord delivery) + JSON (vault staging)

**平台相容：** Windows + macOS（vault 路徑自動 fallback）

**相依：** firecrawl (Betelgeuse 192.168.1.11:3002)
