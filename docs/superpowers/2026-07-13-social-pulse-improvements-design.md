---
title: Social Pulse 報告改良設計
date: 2026-07-13
status: approved
---

# Social Pulse 報告改良設計

## 背景

早上報告出現 5 個問題需要修復：
1. r/taiwan 來源要移除
2. Discord 排版縮進不一致
3. 繁簡轉換問題
4. Sentiment 分析應該由下游 AI Agent 處理，不在 Python 端呼叫

## 改動清單

### 1. 移除 r/taiwan 來源
- 刪除 `REDDIT_URL` 常數
- 刪除 `run()` 中 r/taiwan 的抓取區塊
- 保留 business subreddits 和 AI agent 搜尋

### 2. Discord 排版統一一行
- 所有來源統一格式：`#. 標題  —  meta — url`
- 移除兩行顯示的邏輯（meta 和 url 擠在同一行）

### 3. 繁簡轉換（輸出時）
- 使用 `opencc` 套件（`opencc-python-reimplemented`）
- 只在 `format_discord()` 輸出前翻譯標題和 meta
- 原始 JSON 保持原文

### 4. JSON 結構優化
- 確保每個 item 有 title、url、source、meta
- 格式一致，方便下游 AI Agent 讀取做 sentiment 分析
- Sentiment 由 AI Agent 自行處理（不在此脚本呼叫 LLM API）

## 架構

```
fetch all sources → dedup → format discord (with translation) → output JSON + discord text
                                                        ↓
                                              AI Agent receives JSON
                                              → does sentiment analysis
                                              → picks top 5+/top 5-
```

## 依賴

- `opencc` — 繁簡轉換（pip install opencc-python-reimplemented）
- 無其他新依賴

## 成功標準

- [ ] r/taiwan 不再出現在報告中
- [ ] Discord 輸出每項一行，排版一致
- [ ] 繁體中文環境下顯示正體中文
- [ ] JSON 輸出結構清晰，AI Agent 可讀取
