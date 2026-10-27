# 第三階段：ZIP 一鍵下載、MP4 自動同步

本次從 `main` 的 `31bbd94f716065127f468df8c53a7fd7dc3555be` 開始，確認已包含第一階段 `93990c3` 與第二階段操作改善。沿用既有內容版本、資料保護、ZIP格式及FFmpeg渲染器。

後續新增：輸出MP4時可預設同時製作／下載同版本ZIP，分檔去重、失敗保留與原快照ZIP重試；參閱[雙檔輸出說明](DUAL_OUTPUT.md)。以下保留第三階段原始機制與歷史測試紀錄。

第六階段沿用此流程，三套模板的MP4／ZIP依快照內共用影片標題產生同主體檔名；沒有關聯的舊專案取封面文字。已完成檔案保留產生當下的檔名，不會因後續改標題而替舊成果重新命名。新增標題關聯的ZIP使用版本3；舊版1／2仍可匯入。詳見[快速修改標題](QUICK_TITLE_EDIT.md)。

## 操作流程

匯入照片 → 選用AI分析 → 編輯照片／文字／PNG／封面／BGM → 預覽 → 在下方輸出區按「下載 ZIP」或「輸出 H.264 MP4」。兩個主要按鈕相鄰，進度顯示在同一區域。沒有新增側欄下載入口。

- ZIP正常只需按一次：固定點擊當下的版本，自動同步、驗證、打包並請求瀏覽器下載。不必先按套用，也不必再按第二個下載按鈕。
- MP4同樣固定點擊當下的版本，自動同步後在背景呼叫現有FFmpeg，完成後仍用原有播放器及影片下載。
- 處理時可繼續修改文字、PNG、構圖、時間軸與封面。新修改不會混入正在處理的版本；完成的檔案若落後草稿，顯示舊版本。
- 為保護素材引用，處理期間暫停上傳／替換來源照片、切換模板及清空／登出／匯入取代；沒有鎖住整個前端編輯器。
- ZIP產生或開始下載都不代表備份成功。請檢查電腦上的檔案，再按「我已確認此版本ZIP已儲存」。下載A後改成B，再確認A，只會標記A，B仍未備份。

## 實作與版本保護

1. `frontend/actions/` 的相鄰按鈕透過明確的 `StudioOutputBridge` 取得編輯器點擊當下草稿。橋接只查找相同編輯工作階段的元件介面，不查詢Streamlit內部DOM或模擬點擊它的按鈕。
2. `frontend/output-controller.js` 建立request ID、草稿seq、內容SHA-256及輸出寬度，送出一次完整metadata快照。圖片／音訊仍使用既有媒體，不因拖曳重傳或重新編碼。
3. `studio/sync.py` 使用原有交易驗證資料及媒體引用，建立白名單快照。前端收到完全符合request ID、operation ID、seq及內容版本的ACK，才送第二個輕量啟動事件。
4. `studio/output_jobs.py` 只複製製片設定，照片及標籤分離複製；不可變媒體bytes共用，沒有複製Secrets或整份Session State。worker不讀寫Streamlit工作階段，只用固定快照呼叫既有 `build_archive()`／`export_video()`。
5. 背景工作完成後，主執行緒才交換成果。新ZIP或MP4失敗時保留草稿及上一個成功成果；未改內容的同步不增加revision，也不使MP4失效。
6. `frontend/draft-state.js` 在合併前檢查輸出ACK，序號／版本不符就保留新草稿、停止輸出。元件重建可續接精確ACK；取消狀態不會重新啟動工作。
7. 下載收據先存入同分頁草稿，再觸發一次下載，避免rerun／元件重建重複下載。收據與伺服器下載請求記錄都不會自動更新已備份版本。

內容雜湊與先前共用schema維持不變；播放、暫停、seek、選取、下載請求與備份確認均不屬於影片內容。第三階段最初使用ZIP版本1；目前仍相容版本1，含空間導覽資料時使用版本2，詳見[空間導覽](FLOOR_PLAN_TOUR.md)。同步／輸出失敗後可重新按同一個主要按鈕，不會使用不符版本的後端資料繼續輸出。

## 下載技術與部署限制

使用公開的 [Streamlit static serving](https://docs.streamlit.io/develop/concepts/configuration/serving-static-files)，由 `.streamlit/config.toml` 啟用 `server.enableStaticServing=true`。完整ZIP先原子寫入 `static/downloads/`，只將64位隨機十六進位檔名的短效URL及少量metadata交給前端；用自己的 `<a download>` 請求下載。沒有大型ZIP Base64、私人media API或自訂Streamlit內部路由。

- 短效檔約15分鐘過期，30秒掃描清除；新成果替換或經確認的工作區重設也會撤銷舊短效檔。下載中被Windows鎖定的檔案下次再清，不影響工作區。
- 下載目錄總量最多320 MB；專案既有壓縮檔上限160 MB維持不變。背景工作全程序最多2件，已完成但未領取的結果也計入，15分鐘後回收，避免無限制保留大型資料。
- 靜態URL是短效持有者連結，**不經共用密碼驗證**，不要轉傳；URL不含帳密、金鑰或原始檔名。工作室沒有雲端自動儲存，ZIP打包檔只是暫存交付副本。
- 瀏覽器可能靜默阻擋自動下載，網頁無法可靠確認電腦已保存。原按鈕附近有短效「備用下載」，另保留公開 [`st.download_button`](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button) 作為原生備援，直接下載同一份完整快照；不重新打包。靜態服務未啟用、空間不足或URL過期時，可用原生備援，該情況需要額外點一次。
- Cloud更新static設定後可能需要Reboot；重啟會失去工作階段素材，應先確認ZIP已保存。Cloud不保證動態靜態檔持久存在或免費資源足夠；本機成功及推送不代表Cloud已通過驗收。

## 手動同步的用途

主要介面移除「套用變更」及原本獨立的「儲存專案檔」。原同步邏輯保留在「進階／同步恢復 → 同步草稿（疑難排解）」：供錯誤恢復、校準後端標籤素材，以及前端刪除照片後釋放12張來源上限。沒有改成逐字或逐次拖曳同步。

舊元件的同步／輸出協定仍有相容路徑，不重寫渲染核心。一般新操作全部使用上述固定快照握手。瀏覽器錄製仍沿用原流程，錄製時須保持頁面前景。

## 主要修改檔案

| 檔案 | 用途 |
| --- | --- |
| `app.py` | 相鄰輸出入口、背景進度、短效交付與工作區保護銜接 |
| `studio/output_jobs.py`（新增） | 固定快照、限量背景工作、成功交換成果、失敗保留 |
| `studio/downloads.py`（新增） | 短效二進位ZIP發布、過期／容量／安全路徑處理 |
| `studio/output_ui.py`（新增） | 公開自訂元件、fragment進度及過期準備狀態 |
| `studio/sync.py` | 精確版本ACK、啟動／取消／下載收據、冪等保護 |
| `studio/bootstrap.py` | 輸出模組與編輯器介面版本相容檢查 |
| `studio/project_ui.py`、`studio/project_io.py` | 原生備援、備份版本保留、匯入後撤銷短效檔 |
| `studio/versioning.py` | 工作區重設時清除下載請求識別，不改內容雜湊 |
| `studio/photo_intake.py` | 名額不足提示指向進階同步，不要求一般輸出先套用 |
| `frontend/output-controller.js`（新增）、`frontend/actions/`（新增） | 一次點擊、精確ACK、下載去重及相鄰操作區 |
| `frontend/editor.js`、`frontend/draft-state.js`、`frontend/index.html` | 草稿快照、橋接、舊回應保護、同步恢復與簡潔狀態 |
| `.streamlit/config.toml`、`.gitignore`、`static/.gitkeep` | 啟用公開靜態交付，排除實際暫存ZIP |
| `tests/test_output_flow.py`、`tests/output-controller.test.cjs`（新增） | 快照、工作／下載冪等、失敗恢復與版本保護 |
| `tests/editor-events.test.cjs`、`tests/app_helpers.py` 與既有App／AI／對比／BGM／ZIP測試 | 真編輯器合成DOM事件、新入口及舊協定回歸 |
| `README.md`、`docs/PROJECT_FILES.md`、本文件 | 最新操作與部署／測試限制；較早階段文件保留歷史紀錄 |

## 自動化測試

完整 **150項Python、80項Node全部通過**。本階段新增10項Python、7項Node測試；既有第一、第二階段測試全部保留並回歸。

| 驗收情境 | 驗證方式 |
| --- | --- |
| 不套用直接ZIP、文字正確、舊ZIP匯入 | 真 `build_archive()`／`load_archive()`、AppTest新握手、既有版本1往返 |
| ZIP A打包後改B、B不混入A | 快照測試及真AppTest，字／照片／音樂隔離 |
| 新照片不套用輸出、MP4固定A | 真背景FFmpeg 360×640／30 FPS，A綠圖、B藍圖，解碼影格像素確認A |
| 渲染中繼續編輯、不刪舊成果、失敗保留 | 受控worker Mock驗證並行；既有真渲染回歸 |
| 舊／錯ACK、連點、下載去重、重建續接、取消不重啟 | Node控制器及載入真editor.js的合成DOM測試 |
| 備份A不是B、無變更不加revision | Python／AppTest與既有版本保護測試 |
| 靜態ZIP完整才公開、TTL、容量、路徑 | 暫存目錄內真二進位檔案測試 |
| Full HD、PNG、封面、BGM、前後對比 | 既有真FFmpeg輸出／解碼回歸；兩套模板匯入前後影音一致性 |
| AI與快取 | 既有Mock回歸，沒有呼叫真Gemini或使用真實金鑰 |

執行（PowerShell）：

```powershell
Set-Location 'D:\自動影片生成'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.cjs
git diff --check
```

AppTest與合成DOM不是瀏覽器下載測試。這次另啟動loopback本機Streamlit測試站，使用測試密碼、五張自製示意圖，於Codex內建瀏覽器實測：

1. 文字改成「一鍵ZIP快照A」，沒有先同步，點一次相鄰「下載 ZIP」；實際取得下載事件及電腦上的ZIP，重新讀入確認五張照片、文字A正確。
2. 再將文字改成「一鍵ZIP後續草稿B」，確認ZIP舊版、B尚未備份。
3. 確認A已保存，觀察rerun沒有第二次下載；B仍未備份。
4. 按清空出現未備份提醒，取消後B文字完整保留。
5. 截圖確認MP4／ZIP按鈕相鄰，備援下載及版本確認位於其下。

## 尚需人工驗收

目前可用工具只實測內建瀏覽器，**沒有宣稱Chrome、Edge或正式Cloud已通過**。以下也未以實體瀏覽器完成：接近160 MB的大ZIP、瀏覽器政策阻擋下載的原生備援、背景MP4渲染全程連續拖曳。相應錯誤／並行邏輯已自動測試，仍需人工驗收：

1. 在Chrome、Edge各修改文字後直接點ZIP；檢查只有一份下載、匯入文字正確。
2. 阻擋自動下載，改用備援；等待15分鐘短效URL過期後，原生備援仍下載同一份ZIP。
3. 用接近上限的合法專案測試下載、記憶體及Cloud負荷；超限應明確錯誤並保留原成果。
4. 開始Full HD MP4，繼續改文字、拖PNG及時間軸；完成影片仍為點擊時A，草稿B保留並顯示需重新輸出。
5. 使用兩套模板、封面、透明PNG與BGM，下載後重新匯入，確認圖片、文字、時間與聲音；無變更再同步MP4仍有效。
6. Cloud更新後驗證static serving；未啟用時應顯示原生備援。測試前先備份，不用重啟測試取代保存。

## 下一階段

固定內容版本、精確ACK、背景工作與交付收據已可供後續流程利用。完成跨瀏覽器與Cloud驗收後，可以進入前後對比操作自動化；應繼續沿用照片ID及同一時間軸，不必重建輸出系統。本階段沒有新增AI配對、修改Gemini提示詞、登入或渲染核心。
