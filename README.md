# AI 室內設計案例影片工作室

GitHub：[Photos_Auto_to_Video-InteriorDesign](https://github.com/yehzonghan-video/Photos_Auto_to_Video-InteriorDesign)

可操作的 Streamlit 網頁：照片管理、前端即時標籤／拖曳、動畫預覽及 FFmpeg H.264 輸出。第二階段已加入 Google 官方 Gemini SDK、可編輯的 AI 建議清單與批次匯入；沒有金鑰時仍能手動製片。設定、模型查證與測試區分請參閱 [AI 功能說明](docs/AI.md)，輸出限制參閱 [技術可行性](docs/FEASIBILITY.md)。

目前已完成第二階段。基本操作流程：**上傳照片 → 選用 AI 分析 → 確認建議 → 拖曳與編輯標籤 → 預覽 → 輸出 MP4**。

## 目前功能

| 功能 | 已實作內容 |
| --- | --- |
| 照片管理 | JPG／JPEG／PNG／WEBP、多張上傳、縮圖排序、刪除、替換、播放秒數 |
| 完整照片顯示 | 等比例置中、橫式照片上下留黑；也可選擇裁切、縮放及調整構圖 |
| 即時標籤編輯 | 新增、刪除、文字與樣式、滑鼠／觸控拖曳、獨立定位點與連接線 |
| 標籤動畫 | 左／右／上／下滑入、淡入、縮放、無動畫，以及獨立出現與消失時間 |
| AI 裝修辨識 | 官方 Gemini SDK、結構化 JSON、單張／批次分析、人工確認與整批匯入 |
| 草稿同步 | 前端即時操作；套用或輸出前才整批同步，切換照片與一般 rerun 保留編輯 |
| 影片輸出 | FFmpeg H.264 MP4、9:16、1080×1920／30 FPS，另有 720p、360p 選項 |

目前提供「裝修項目介紹」基礎模板；其他模板、背景音樂、LOGO 與品牌結尾尚未實作。沒有資料庫、登入或永久專案儲存。

完整測試紀錄：[AI 與第二階段測試](docs/AI.md)、[編輯器同步測試](docs/EDITOR_SYNC.md)、[第一階段歷史驗證](docs/VALIDATION.md)。

## 本機啟動（Windows PowerShell）

需要 Python 3.12（建議與 Cloud 選用同版）、網路安裝套件。Windows 的 FFmpeg 隨 imageio-ffmpeg 套件提供，中文字型使用系統微軟正黑體。也支援自行安裝的 FFmpeg。

```powershell
Set-Location 'D:\自動影片生成'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

瀏覽器開啟 `http://localhost:8501`。上述命令直接使用虛擬環境內的 Python，不需要另外啟用環境。手動製片不需要登入或 API 金鑰；只有 AI 分析需要 Gemini 金鑰。若 `py` 找不到，安裝 Python 3.12 或將建立虛擬環境的命令改成可用的 Python 完整路徑。

本次開發已建立 `.venv` 時，可直接使用 `start.ps1`。關閉終端或按 Ctrl+C 停止服務。

已安裝舊版專案時，先重新執行 `pip install -r requirements.txt`，再重啟 Streamlit，才能載入新增的 Google SDK。

## Gemini 設定

### 本機 Secrets

在專案內建立 `.streamlit/secrets.toml`，可參考 [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example)：

```toml
GEMINI_API_KEY = "YOUR_API_KEY_HERE"
GEMINI_MODEL = "gemini-3.8-flash"
```

將佔位文字換成自己的金鑰。真實 `secrets.toml` 已被 `.gitignore` 排除，請勿提交至 GitHub；金鑰只由 Python 伺服器使用，不傳給標籤編輯器。修改設定後重啟應用程式。

也可使用伺服器環境變數 `GEMINI_API_KEY` 與 `GEMINI_MODEL`；若同時設定，Secrets 優先。未設定金鑰時，AI 按鈕會停用並說明原因，手動編輯與 MP4 輸出仍可使用。

### 模型與免費方案

預設模型為 **`gemini-3.8-flash`**。2026-10-12 實測中，原先優先測試的 `gemini-2.5-flash` 雖出現在模型清單，實際分析卻回傳 404，指出不再向新使用者開放；3.8 Flash 的照片分析已成功。

程式允許設定 `gemini-3.8-flash`、`gemini-2.5-flash`、`gemini-2.5-flash-lite`。舊帳號若仍能使用 2.5 Flash，可自行指定；分析失敗時**不會自動換模型**。新增型號前需查證免費層並更新 `studio/ai.py` 的允許清單。

查證當日 Google 官方價格頁列有上述模型的免費 Standard 層。請使用未啟用帳務的免費專案金鑰；模型有免費層不代表已啟用帳務的專案一定免費，程式也無法由金鑰查證帳務狀態。實際可用額度請查看 AI Studio。[官方價格](https://ai.google.dev/gemini-api/docs/pricing) · [額度說明](https://ai.google.dev/gemini-api/docs/rate-limits)

AI 分析會把照片副本傳送至 Google。免費方案可能使用輸入及輸出改善產品，並由人工審閱；請勿傳送敏感、機密或個人資訊。介面會在分析前顯示提醒並要求勾選同意。[Google 資料使用政策](https://ai.google.dev/gemini-api/terms)

## 操作方式

1. 上傳 JPG／JPEG／PNG／WEBP，可一次多張；或載入 5 張自行繪製的測試示意圖。
2. 在照片列點選照片，拖曳縮圖排序。觸控或鍵盤可使用前移／後移按鈕。刪除目前照片與單張替換在照片管理區。
3. 設定每張秒數。預設「完整照片（空白處留黑）」等比例置中保留整張照片，橫式照片上下留黑；需要裁切時，可改選「填滿畫面（裁切照片）」再使用縮放及水平／垂直裁切滑桿。
4. 若要使用 AI，展開「AI 分析裝修項目（選用）」，閱讀資料政策後選擇 1～3 張分析。修改名稱與說明、查看建議位置、勾選或刪除項目，再按「全部採用」或「套用所選標籤」。到下方編輯器查看匯入結果；既有人工標籤保留。
5. 按「新增標籤」立即顯示完整標籤，直接修改文字及樣式。拖曳畫面上的標籤；拖曳圓形定位點可單獨移動物件位置。這些操作只更新前端草稿，不觸發 Python 同步。
6. 展開樣式與動畫設定：大小、字色、背景、透明度、圓角、連接線、出現／消失時間與進場時長。停留時間為 `消失時間 - 出現時間 - 進場時長`；標籤可錯開出現。
7. 使用播放／時間軸預覽整部影片。編輯模式固定顯示全部標籤，選中框與定位點操作提示不會輸出到影片。
8. 編輯完成後按時間軸右側「套用變更」。未套用時使用本機字型即時預覽；套用後校準為與影片輸出相同的標籤素材。切換照片與一般 Streamlit rerun 都會保留草稿。
9. 按「瀏覽器 MP4」或下方「輸出 H.264 MP4」都會先確認最新草稿已套用，再開始輸出。瀏覽器錄製需保持頁面前景；FFmpeg 預設 Full HD／30 FPS，也可選 720p 或 360p。完成後播放、下載，清空工作階段可移除照片與影片。

AI 匯入依編輯器當時最新的完整顯示／裁切設定換算座標。物件完全位於裁切外時不匯入；部分可見時修正定位點並標記待確認。匯入後若再次改變裁切，請重新確認標籤與定位點。

標籤、排序與構圖先保留在 JavaScript 本地狀態，並將純文字／座標草稿存入同分頁的 `sessionStorage`（不含照片），元件重建時可恢復。只有「套用變更」及輸出前才整批同步 Python，以事件 ID 與版本號防止重複套用、舊資料覆蓋新編輯。同步失敗保留草稿並顯示錯誤。輸出時只使用已確認的最新設定。

照片上傳至 Streamlit 伺服器並只存在目前工作階段記憶體；FFmpeg 暫存壓縮影片會清除。整頁重新整理、連線斷開或關閉分頁仍可能令伺服器照片工作階段失效，第一版沒有永久專案存檔。瀏覽器不允許 sessionStorage 時，介面提示先套用再離開此頁。未套用草稿時請勿使用先前下載結果代替重新輸出。

## 使用限制與錯誤處理

| 項目 | 目前上限或行為 |
| --- | --- |
| 照片 | 每工作階段最多 12 張；單張 15 MB、總容量 80 MB |
| 影片與標籤 | 每張 1～20 秒、總長最多 120 秒；每張最多 12 個標籤 |
| AI 批次 | 每次最多 3 張；工作階段最多 20 次 API 呼叫 |
| AI 程序共用限流 | 同一金鑰每分鐘 5 次、滾動 24 小時 100 次；程序重啟會重置 |
| 重複照片分析 | 依模型、提示版本與照片內容雜湊使用工作階段快取；可勾選重新分析 |
| AI 失敗 | 單張失敗不阻斷其他照片；不自動重試，仍可手動製片 |
| 匯入標籤過多 | 超過 12 個時拒絕該照片的整批新增，請減少選取後重送 |

這些 AI 限制是應用程式的安全上限，並非 Google 保證的免費額度。429 表示額度不足或呼叫太頻繁；404 表示模型無法使用；金鑰、權限及 JSON 格式錯誤也會顯示說明。沒有模型自動切換或付費備援。

瀏覽器 MP4 依賴瀏覽器的 H.264 支援，且無法保證固定 30 FPS；不支援時按鈕停用，可使用 FFmpeg。免費 Cloud 的 Full HD 渲染效能仍需部署後測試。

## 測試

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\verify_export.py --width 1080
node --check frontend\editor.js
node --test tests/*.test.cjs
.\.venv\Scripts\python.exe -m pip check
```

影片驗證會建立 `artifacts/verification.mp4`、截圖與 JSON 結果（已忽略，不上傳 Git）。使用 5 張自行繪製的室內空間示意，每張 4 秒、中文標籤從左滑入；驗證 H.264、1080×1920、20 秒、600 影格及完整解碼。若電腦較慢可先用 `--width 360`。執行驗證腳本產生的示意圖不代表真實客戶案例或 Gemini 辨識。

真實 Gemini API 測試（會使用額度），請指定自己有權傳送的照片；未設環境變數時，腳本以隱藏提示接收金鑰，不寫檔：

```powershell
.\.venv\Scripts\python.exe scripts\verify_gemini.py 'C:\照片\單張.jpg'
.\.venv\Scripts\python.exe scripts\verify_gemini.py 'C:\照片\第一張.jpg' 'C:\照片\第二張.png'
```

2026-10-12 第二階段驗證：

- 23 項 Python、15 項 Node 測試通過，涵蓋 Schema、座標、快取、確認表單、批次匯入、草稿保存、去重及輸出同步。AI 錯誤與表單測試使用 Mock，前端互動測試使用合成 DOM。
- 真實 Gemini 3.8 Flash：兩張自製室內示意圖批次分析各回傳 3 個項目；單張 WEBP 成功回傳空清單。空清單不會被補成假標籤，示意圖也不能代表真實室內照片準確率。
- 實際生成含確認後 AI 標籤的 1 秒 Full HD H.264／30 FPS MP4，完整解碼並比對標籤區域；AppTest 另驗證 360p 實際輸出。

仍需人工測試真實客戶照片辨識準確率、瀏覽器完整 AI 確認→拖曳→輸出流程、實體觸控、其他瀏覽器、Cloud API 設定與多人負載。以上是功能開發時的驗證紀錄，本次 README 更新未重新呼叫 API 或渲染影片。

## Streamlit Community Cloud

1. 將原始碼推送到自己的 GitHub repository，**不要提交 `.venv`、`.tmp`、`.tools`、`.streamlit/secrets.toml` 或使用者素材**。
2. 在 Community Cloud 建立 app，入口 `app.py`，Python 選 3.12。
3. Cloud 讀取 `requirements.txt`；`packages.txt` 安裝 `ffmpeg`、`fonts-noto-cjk`。應用程式的環境檢查會確認 libx264 與中文字型。
4. 手動流程不用 Secrets。啟用 AI 時，把 `.streamlit/secrets.toml.example` 的 Gemini 設定放到 Cloud 的 Secrets，填入未啟用帳務的免費專案金鑰。預設 `gemini-3.8-flash`：本次真實 API 確認 2.5 Flash 不向新使用者開放；仍可自行設定模型，程式不自動切換。真實金鑰不得放在 repository 或前端。
5. 部署後先跑短片，再跑 20 秒 Full HD。**本專案本機成功不代表已公開部署，也不保證免費 Cloud 的效能**；能力不足時介面顯示錯誤，可改用瀏覽器輸出或本機 Streamlit。

Cloud 安裝依據：[官方依賴文件](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)。免費 Cloud 公開 app 可能被其他人使用，目前有張數、時間、檔案大小、程序同時輸出及 AI 工作階段／程序共用限流；程序重新啟動會重置共用上限。

部署欄位：

| 欄位 | 值 |
| --- | --- |
| Repository | `yehzonghan-video/Photos_Auto_to_Video-InteriorDesign` |
| Branch | `main` |
| Main file path | `app.py` |

Cloud 的 **Settings → Secrets** 使用上方 Gemini TOML 範例，填入真實金鑰後儲存。金鑰只放在 Secrets，不放在 Main file path、README 或原始碼。

## 專案結構

```text
app.py                    Streamlit 流程、上傳、工作階段與下載
studio/models.py          原始照片、標籤、輸入驗證
studio/rendering.py       等比例裁切、共用 PNG 標籤、逐影格合成
studio/animation.py       可重用動畫時間公式
studio/export.py          FFmpeg 能力檢查、負載控制、H.264 輸出
studio/component.py       自訂元件 Python 介面
studio/sync.py            批次同步、版本檢查、事件去重與輸出握手
studio/ai.py              Gemini Structured Output、座標驗證、快取與限流
studio/ai_ui.py           分析進度、結果確認與匯入佇列
frontend/index.html       編輯器版面
frontend/editor.js        拖曳、預覽、照片排序、瀏覽器錄製
frontend/draft-state.js   前端草稿、跨 rerun 恢復與回覆合併
frontend/ai-import.js     依最新構圖換算 AI 座標並批次附加草稿
frontend/label-raster.js  未套用標籤的即時本機繪製
frontend/animation.js     前端動畫公式
templates/items.json      第一版模板設定
scripts/verify_export.py  實際 20 秒影片驗證
scripts/verify_gemini.py  真實 API 驗證（隱藏提示金鑰）
tests/                    重要資料與動畫測試
docs/FEASIBILITY.md        技術決策與已知限制
docs/EDITOR_SYNC.md        同步架構、原因與效能驗證範圍
docs/AI.md                AI 設定、資料政策、座標與實測限制
.streamlit/               主題、Secrets 範例
```

照片、標籤與模板分離。新增模板可加入 JSON 並註冊於 `template_config`；新的轉場或版型仍需要對應渲染策略，尚未實作的前後對比與特色模板不會以空選項出現。

## 後續階段

- 第二階段已實作：Gemini Structured Output、可見內容辨識、定性信心與待確認、人工編輯採用、單張重分析、工作階段快取及配額限制。仍需用真實室內照片人工評估辨識準確率，以及驗證 Cloud 完整操作流程。
- 第三階段：前後對比與案例特色模板、共用標籤及時間軸。
- 第四階段：使用者 LOGO／背景音樂／品牌結尾、效能與操作優化。

參考影片尚未提供；模板 A 的基礎版以 9:16 照片、圓角標籤、定位點與進場動畫為範圍。沒有下載不明授權音樂、LOGO 或圖片。字型可透過 `STUDIO_FONT_PATH` 指定自己的合法字型檔；Cloud 使用系統 Noto CJK。
