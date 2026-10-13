# 第二階段：Gemini 裝修辨識

## 模型與免費方案查證（2026-10-12）

使用 Google 官方 `google-genai==2.29.0`，搭配 `pydantic==2.13.5`。
優先測試使用者指定的 `gemini-2.5-flash`。官方 API 的 models.list/get 雖仍列出此模型與 generateContent，實際請求回傳 404：

> This model models/gemini-2.5-flash is no longer available to new users.

因此預設改為 `gemini-3.8-flash`，已真實測試結構化照片分析成功。既有可用帳號可自行設定 `gemini-2.5-flash`；程式不在錯誤後自動更換模型。
2026-10-13 更新：介面可選 `gemini-3.8-flash`、`gemini-3.6-flash`、`gemini-3.5-flash-lite`、`gemini-3.1-flash-lite`、`gemini-2.5-flash`、`gemini-2.5-flash-lite`。這些型號的 Standard 免費層已查證；3.8 Flash／3.1 Flash-Lite 已完成真實生成測試，其他型號不保證所有帳號都能使用。新增型號前需更新免費模型清單並重新驗證。

- [Google 官方價格](https://ai.google.dev/gemini-api/docs/pricing)：3.8 Flash Standard 有免費輸入／輸出層。程式使用一般 generateContent，不使用付費 Batch API、Grounding、Files 或影片 API。
- [額度文件](https://ai.google.dev/gemini-api/docs/rate-limits)：可用額度依專案／帳號而異，應在 AI Studio 查看；本程式的上限不是 Google 保證的免費額度。
- [免費方案資料政策](https://ai.google.dev/gemini-api/terms)：輸入與輸出可能用於改善產品，並由人工審閱；不要傳送敏感、機密或個人資訊。分析前須勾選同意。
- [物件座標文件](https://ai.google.dev/gemini-api/docs/image-understanding)：邊界框順序 `[ymin,xmin,ymax,xmax]`，Gemini 使用 0～1000。
- [Structured Output](https://ai.google.dev/gemini-api/docs/structured-output)：Pydantic Schema 轉為 JSON Schema 提供給 SDK，回傳後再次嚴格驗證。

請使用未啟用帳務的免費專案金鑰。具有免費層的模型不等於任何帳務設定的專案都免費；本程式不開通帳務、不自動降級到其他型號，也無法由 API 金鑰查證帳務狀態。

## 金鑰設定與啟動

本機將 `.streamlit/secrets.toml.example` 複製成 `.streamlit/secrets.toml`，填入自己的金鑰；真實檔案已被 Git 忽略。或在伺服器設定 `GEMINI_API_KEY`、`GEMINI_MODEL` 環境變數。Secrets 優先。

```toml
GEMINI_API_KEY = "YOUR_API_KEY_HERE"
GEMINI_MODEL = "gemini-3.8-flash"
```

Community Cloud：入口仍為 `app.py`，在 app 的 Settings → Secrets 貼上上述 TOML。金鑰不放入 GitHub、元件參數或任何前端程式。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

本次測試金鑰透過終端隱藏提示輸入，未保存於專案或 Git；仍需自行完成部署端 Secrets 設定。

## 操作與資料同步

1. 上傳照片後，在「AI 分析裝修項目（分析後直接加入標籤）」閱讀資料政策並勾選同意。
2. 選擇模型與照片，可一次選最多 12 張，按「AI 分析並加入標籤」。收到一張回覆後才送下一張，不同時發出多個請求。
3. 等待時顯示目前照片、各張待分析／等待／完成／失敗狀態、進度及限流倒數；暫時性失敗最多自動補試一次。
4. 成功結果直接整批交付前端，不再有建議採用表單；不需要另按「全部採用」或「套用所選標籤」。既有 Python 標籤此時不變，待原有草稿同步交易處理。
5. 前端以照片 ID／內容雜湊核對來源，依當前本地構圖換算定位點及文字位置，直接附加到現有草稿；不重建編輯器、不逐個送出元件事件、不覆蓋未同步人工修改。
6. 查看編輯器的實際加入數量。照片已替換／刪除、物件完全在裁切外時不匯入；部分可見時將定位點調至可見部分並標記需確認。容量不足時加入仍可容納的項目、顯示超出數量，保留所有既有標籤。
7. 不需要的標籤在原有編輯器直接刪除或修改；自由拖曳、改文字／樣式／動畫，按「套用變更」或輸出前自動整批同步。原有 MP4 渲染核心不變。
8. 按「補查未完成照片」，比對照片 ID、原圖內容雜湊、模型及待處理記錄，只重送尚未收到有效回覆的照片。空 items 算成功，不會無限重送；中途中斷後已成功結果仍保留。

成功結果的交付 ID 存於目前工作階段，匯入批次 ID 存於前端 sessionStorage 草稿，用來防止 rerun／元件重建或再次使用快取時重複附加。使用者刪掉的 AI 標籤不會因普通 rerun 復活；手動重新分析產生新結果可再加入。同步事件帶回已處理批次 ID，後端才清除佇列。尚未同步的草稿保留於原有前端機制。整頁重新整理可能失去伺服器照片工作階段，並非永久專案存檔。

邊界框驗證後除以 1000 成為 0～1；定位點與文字位置直接要求 0～1。影像先校正 EXIF 方向，再將分析副本等比例縮至最長邊 1600；原圖不變。前端共用 `photo-layout.js` 依最新 contain／cover／zoom／crop 換算到 1080×1920。之後若再次改變裁切，既有標籤仍依原編輯器的影片畫面座標保存，需要人工重新確認位置。

說明、類別、定性信心、待確認、來源與項目 ID 隨既有標籤同步保存；影片仍只繪製短標籤，沒有額外說明圖層。

## 快取與額度限制

- 只有按分析、重新分析或補查才呼叫 API，普通 rerun、標籤編輯、匯入和輸出都不觸發 API。
- 工作階段快取鍵為 prompt 版本＋模型＋原照片 SHA256，相同照片不需重複分析；替換內容／換模型會失效。
- 可一次選全部照片（最多 12 張），每工作階段最多 20 次 API 呼叫，包含補試；同一伺服器、同一金鑰每分鐘最多 5 次、滾動 24 小時最多 100 次。每分鐘額度不足時最多等候兩個窗口，每秒顯示剩餘等待時間。程序重啟後共用限流會重置，並非持久化防濫用服務。
- 原先三張上限是本程式的保護設定，不是 Google 固定限制。官方額度按專案及模型計算，不是換金鑰就能解除；本程式的排隊也不能解除 Google 每日額度或帳號限制。
- SDK 本身每次僅嘗試一次、60 秒逾時；應用程式對暫時連線、5xx、格式不符或 429 最多補試一次。429 等待 60 秒後補試，仍失敗會暫停剩餘未發送請求；400／401／403／404 不補試，避免無效消耗。非帳號限制的單張失敗可繼續處理其他照片，不無限重試或自動換模型。
- 快取／AI 結果僅存工作階段記憶體，共用限流只含時間與金鑰雜湊。清空工作階段移除照片及 AI 資料，但不重置程序共用額度。
- 無金鑰、超額或分析失敗皆保留手動製片流程。重新分析失敗時保留先前成功結果，錯誤訊息會顯示。

## 實測與限制

真實 Google API（不是 Mock）：使用提供的測試金鑰，先查詢可用模型；2.5 Flash 的實際呼叫得到上述 404。明確改用 3.8 Flash，批次分析 `artifacts/samples/sample.png`、`sample.jpg`，兩次各自的照片請求都成功，各回傳 3 個建議，通過 Pydantic、邊界框與定位點驗證。素材為自行繪製的室內示意，不能代表真實室內案例辨識準確率。

另以單張 `sample.webp` 呼叫真實 3.8 Flash API，成功回傳合法的空 `items`。沒有將空結果補成假裝修項目；使用者可改用手動標籤。該結果不表示系統已能可靠辨識所有素材。

Mock／合成測試與真實 API 分開：`test_ai.py`、`test_ai_ui.py` 使用 Mock 驗證 Schema、無效／缺漏座標、快取、重分析、單張失敗、缺金鑰、額度限制、自動交付、模型選擇、批次排隊、既有標籤保留及金鑰不進元件資料；前端 Node 執行真正事件處理器及座標模組，驗證批次匯入、草稿保留／切換／重建／去重／最新輸出快照。

2026-10-12 自動測試為 23 項 Python、15 項 Node；2026-10-13 更新後為 28 項 Python、16 項 Node 全部通過，`pip check` 無依賴衝突。Python AppTest 在允許本機 socket 的環境執行，Mock 測試不消耗 Google 額度。

`test_synced_video.py` 真實生成 1080×1920 H.264／30 FPS／1 秒 MP4，含使用者確認後的 AI 標籤資料，完整解碼並比較標籤區域與渲染預期（有損編碼每色平均差 <8）。Streamlit AppTest 也實際輸出 360p 影片。

2026-10-13 使用新測試金鑰的真實驗證：官方模型清單列出上述候選型號；3.1 Flash-Lite 的兩張示意圖各回傳 2 個項目。實際瀏覽器再選 5 張自製示意圖逐張分析，回傳項目數為 2、2、2、3、2，全部直接加入前端草稿；未同步的「保留人工草稿」文字仍保留，切換照片結果正確。修改 AI 文字及淡入動畫後，成功輸出、實際下載並完整解碼 1080×1920／30 FPS／20 秒／600 影格 MP4，渲染耗時 25.8 秒。等待階段實際顯示「等待 Gemini 回覆」、已完成／待分析表格與進度。

新測試金鑰另測 3.8 Flash：模型查詢成功，單張分析在補試一次後仍回報連線／服務忙碌／回覆逾時類錯誤，沒有有效辨識結果，不能宣稱該次生成成功。3.8 Flash 先前成功紀錄是2026-10-12使用當時測試金鑰的結果。介面允許明確選擇本次成功的3.1 Flash-Lite，程式不自動換型號。

12 張完整佇列、限流倒數、中途停止、持續429、部分補查與舊成功結果仍有新失敗等情況使用 Mock／虛擬時間測試，不冒充真實 API 成功或刻意耗盡 Google 額度。

尚需人工測試：真實客戶照片的辨識準確率與框選位置、實體觸控與其他瀏覽器、Cloud 部署端 API 可用地區／專案額度／帳務設定及多人負載，以及12張完整實際API長佇列。未把 Mock 或合成 DOM 測試稱為真實瀏覽器驗證。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/*.test.cjs
.\.venv\Scripts\python.exe -m pip check
# 真實 Google API，提示金鑰（隱藏輸入）；會使用額度，請提供有權送出的照片。
.\.venv\Scripts\python.exe scripts/verify_gemini.py path/to/photo.jpg
.\.venv\Scripts\python.exe scripts/verify_gemini.py path/to/photo1.jpg path/to/photo2.jpg
```
