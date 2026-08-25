# Claude 接手入口

最新版知識包：`2026-08-25`

可攜壓縮檔：`MVP_Ramen_AI_Training_Export_2026-08-25.zip`

## 使用方式

1. 將ZIP解壓縮後交給Claude。
2. 要求Claude先閱讀`prompts/CLAUDE_HANDOFF_PROMPT.md`。
3. 再依提示詞順序讀取`session_delta`、完整知識、來源規則與候選ST。
4. 若Claude要修改PLC，必須先確認目標是V100或V101；V101是1000筆耐久測試版。
5. 修改後重新進行ISPSoft編譯與回歸，不可用舊PASS涵蓋新程式。

## 可直接貼給Claude

```text
請接手MVP Ramen自動拉麵機專案。先完整閱讀prompts/CLAUDE_HANDOFF_PROMPT.md，並依其中順序讀取知識包。請使用繁體中文，先確認目標PLC版本，再進行任何分析或修改。MVP_V2_101是後續1000筆耐久測試版；MVP_V2_100是前一版與部分PDF來源，不得混用。所有PLC修改都要附ISPSoft編譯、AS200 Simulator、周邊模擬、回歸與實機驗證步驟。
```

