# 候選PLC邏輯參考

本目錄保存聊天中由使用者提供或共同修正的完整ST候選碼，目的是讓Claude理解設計與做diff。

## 重要限制

- 這些檔案不等於已匯入ISPSoft，也不等於V101已包含。
- V101是1000筆測試版；任何候選碼合入V101後都要重新編譯與回歸。
- `Noodlebasket PRG`是LD，請直接查看`project_snapshot/1.PLC/MVP_V2_100/Print_Noodlebasket.pdf`與同版本ISPSoft專案。
- 若ST與ISPSoft最新畫面不同，以最新畫面與重新匯出為準。

## 檔案

- `FB_AutoScheduler_user_2026-08-25.st`：使用者提供的完整Scheduler。
- `FB_ActionArbiter_candidate_2026-08-25.st`：修正站2等待煮麵時可裝填其他麵篩，並移除ISPSoft不接受的空白ELSIF。

