# Gemini逐張分析：診斷與有限重試

這次只修改`studio/ai.py`、`studio/ai_ui.py`並新增`studio/ai_diagnostics.py`，以及AI測試與文件。時間軸、前端編輯器、影片渲染、模型選單與API金鑰設定不變。

## 查到的程式問題

- 每張建立伺服器端SDK client，SDK重試關閉、HTTP逾時設定60秒；逐張等待後才發下一張，沒有同時送出四張。
- 舊錯誤函式把503、504、網路例外、逾時及未知錯誤合併成同一句話，沒有留下狀態碼、SDK類型或耗時，不能判定使用者此次連續失敗的真實原因。
- 舊補試只有一次、一般固定等2秒，429固定等60秒；没有讀取HTTP `Retry-After`或Google `RetryInfo`，也沒有區分每日額度耗盡。
- 舊「重新分析」忽略所選成功照片的快取；成功結果雖未刪除，但會重送並消耗額度。另修正舊結果尚在快取時，不得把它當成最近失敗請求的新成功結果。

可能原因包括專案RPM／TPM限制、503服務暫時不可用、504伺服器處理逾時，或用戶端網路逾時。逐張不等於不會限流，Google限制包含每分鐘請求／輸入tokens及每日請求，且按專案計算。未取得此次Cloud Logs前，這些只是候選原因。[Google額度文件](https://ai.google.dev/gemini-api/docs/rate-limits)

## 新行為

| 分類 | 處理 |
| --- | --- |
| 429，未確認為每日耗盡 | 有限補試；持續失敗則暫停未送出照片 |
| 429，QuotaFailure明確每日限制或API訊息明確每日耗盡 | 不補試，立即暫停其餘請求；成功結果保留 |
| 503 | 顯示服務暫時不可用，最多補試兩次 |
| 504 | 顯示伺服器處理逾時，最多補試兩次 |
| ReadTimeout／ConnectTimeout等用戶端逾時 | 無HTTP回覆時為空值；顯示用戶端逾時，最多補試兩次 |
| HTTPX連線例外 | 無HTTP回覆時為空值；顯示連線失敗，最多補試兩次 |
| 408／500／502 | 有限補試 |
| JSON Schema／座標錯誤 | 不自動補試，保留手動製片 |
| 400／401／403／404 | 不補試，暫停其餘照片；其他HTTP或未知例外不自動補試 |

每張上限三次（第一次＋兩次補試），每次仍計入工作階段20次與程序共用額度。優先使用`Retry-After`（秒數或HTTP日期），其次使用`google.rpc.RetryInfo.retryDelay`；沒有提示才使用2、4秒加0～1秒jitter，429無提示則60、120秒加jitter並以120秒為上限。這與Google建議的有限指數退避原則一致。[Google重試說明](https://ai.google.dev/gemini-api/docs/troubleshooting)

若伺服器要求等75秒，就等待至少75秒，不再截短成60秒；要求超過120秒則本次停止自動補試及後續送出，提示稍後補查，不會提早呼叫。等待仍使用現有倒數UI。明確每日耗盡不能靠幾秒退避解除。

「重新分析所選未完成照片」只處理所選照片中同模型／內容尚未成功、失敗或未送出的照片。「補查未完成照片」處理目前所有未完成照片。已成功的有效結果（包含空items）保留；不重送、不重複交付標籤；一般rerun也不呼叫API。換模型或替換照片內容視為新的分析來源。

## Cloud Logs查看步驟

1. 登入Community Cloud的管理者帳號，打開部署的app。
2. 右下按 **Manage app**，查看Cloud Logs；需要保存時用下方選單 **Download log**。[Streamlit官方操作](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app#cloud-logs)
3. 在工作室分析一次，展開「上次分析佇列」查看每次HTTP、API狀態、錯誤類型、耗時及診斷代碼。表格的檔名僅供工作階段辨認，不寫入伺服器診斷日誌。
4. 在日誌搜尋 **`GEMINI_DIAGNOSTIC`** 或該筆`request_id`。同一`batch_id`是一批排隊，同一`photo_id`是同張照片，`attempt`是該批第幾次呼叫。時間使用UTC，台灣時間加8小時。
5. 比較第一張成功的`request_end`與後三張失敗的`request_end`，再查看`retry_scheduled`與`batch_pause`，分辨真正呼叫失败和根本未送出的照片。

每行是一個JSON物件，主要欄位：

| 欄位 | 用途 |
| --- | --- |
| `event` | request_start／request_end／retry_scheduled／retry_deferred／batch_pause／request_skipped／local_budget_wait |
| `request_id` | 本程式產生的診斷代碼，對應UI，非Google服務端request ID |
| `batch_id`、`photo_id`、`model`、`attempt` | 批次、匿名照片ID、模型、第幾次嘗試 |
| `http_status` | SDK底層HTTP response實際狀態；未收到回覆時null，不杜撰504 |
| `api_status`、`error_type`、`kind` | Google狀態、SDK／HTTPX例外類型、應用程式分類 |
| `elapsed_seconds` | 用monotonic clock量測generateContent耗時；尚未呼叫時null |
| `phase` | image_preparation／request／response_validation，可分辨圖片處理與回傳格式驗證 |
| `retry_after_seconds`、`retry_source` | API等待提示與來源；retry_scheduled的`wait_seconds`是實際排定等待 |
| `quota_ids` | 經限制字元驗證的QuotaFailure quotaId／quotaMetric，用來辨認每日或每分鐘限制 |

以下**僅為欄位示意，不是本次使用者的實際Cloud紀錄**：

```text
GEMINI_DIAGNOSTIC {"event":"request_end","request_id":"example","http_status":503,"api_status":"UNAVAILABLE","error_type":"ServerError","kind":"unavailable","elapsed_seconds":1.2,"outcome":"failure"}
```

- `http_status=429, kind=daily`且有PerDay相關quotaId：每日額度；不會持續補試。若`kind=rate`，尚不能斷定每日額度耗盡。
- `http_status=503`：服務可用性問題；查看是否兩次補試後仍失敗。
- `http_status=504`：有HTTP回覆的伺服器deadline錯誤。
- `http_status=null, kind=timeout, error_type=ReadTimeout`，耗時接近HTTP逾時設定：用戶端未收到完整回覆，不能等同503或504。
- `http_status=200, kind=validation`：HTTP成功，回傳內容未通過Schema，沒有匯入錯誤資料。
- `http_status=200, kind=timeout`：已收到200標頭，但讀取回覆內容時逾時，保留已知HTTP狀態，不等同有效分析成功。
- 只有`request_start`沒有對應`request_end`：請求仍在進行，或程序被重啟／中斷，不能當成確定503。
- `request_skipped, attempts=0`：前一張導致本批暫停，這張沒有呼叫Google。`local_budget_wait`是本程式限流，沒有Google HTTP錯誤。

日誌不記錄API key、請求URL、原始API訊息、標題／檔名、圖片base64或回覆正文，避免敏感資料進Cloud Logs；也不啟用SDK debug日誌。需要分享紀錄時，可提供對應JSON診斷行，無需提供金鑰或照片。

## 測試範圍

新增測試使用官方SDK搭配HTTPX MockTransport與AppTest，沒有呼叫真實Google API或消耗額度：

- HTTP 200／429／503／504、用戶端ReadTimeout、ConnectTimeout、連線及未知例外分類。
- 真正SDK response hook讀取模擬HTTP回覆狀態、耗時與日誌去除敏感資料。
- Retry-After秒數／日期、Google RetryInfo、提示優先順序、指數退避與最多三次呼叫。
- 75秒提示不截短、180秒提示不提早補試；明確每日耗盡只呼叫一次並保留未送出照片。
- AppTest模擬第一張成功、後三張503各失敗三次；重新分析只呼叫後三張，第一張結果不變、標籤交付不重複、rerun不呼叫API。
- 最近失敗時舊快取保留，但不得充作新成功結果。

完整Python回歸71項通過，包含原有照片、標籤、時間軸、前後對比、登入與實際MP4輸出測試；SDK診斷測試使用模擬HTTP回覆，AppTest使用Mock，不代表已通過Cloud真實API驗證。

Cloud實際失敗原因與真實重試效果仍需部署後按上述步驟確認；本次沒有取得使用者當時的Cloud Logs，沒有宣稱重現真實Google連續失敗。
