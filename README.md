# AI 室內設計案例影片工作室

GitHub：[Photos_Auto_to_Video-InteriorDesign](https://github.com/yehzonghan-video/Photos_Auto_to_Video-InteriorDesign)

第一階段 MVP：Streamlit 網頁、照片管理、手動標籤、真正的滑鼠／觸控拖曳、動畫預覽、瀏覽器 MP4 能力偵測及 FFmpeg H.264 輸出。**此階段尚未接上 Gemini**，沒有模擬 AI 分析或假進度。請參閱 [技術可行性與限制](docs/FEASIBILITY.md)。

本機實測結果、已驗證項目及測試限制記錄於 [VALIDATION.md](docs/VALIDATION.md)。

## 本機啟動（Windows PowerShell）

需要 Python 3.12（建議與 Cloud 選用同版）、網路安裝套件。Windows 的 FFmpeg 隨 imageio-ffmpeg 套件提供，中文字型使用系統微軟正黑體。也支援自行安裝的 FFmpeg。

```powershell
Set-Location 'D:\自動影片生成'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

瀏覽器開啟 `http://localhost:8501`。不需要啟用虛擬環境、不需要登入、不需要 API 金鑰。若 `py` 找不到，安裝 Python 3.12 或將第一行命令改成可用的 Python 完整路徑。

本次開發已建立 `.venv` 時，可直接使用 `start.ps1`。關閉終端或按 Ctrl+C 停止服務。

## 操作方式

1. 上傳 JPG／JPEG／PNG／WEBP，可一次多張；或載入 5 張自行繪製的測試示意圖。
2. 在照片列點選照片，拖曳縮圖排序。觸控或鍵盤可使用前移／後移按鈕。刪除目前照片與單張替換在照片管理區。
3. 設定每張秒數，用縮放及水平／垂直裁切滑桿調整 9:16 構圖。
4. 按「新增標籤」，修改文字。拖曳畫面上的標籤；拖曳圓形定位點可單獨移動物件位置。兩種位置都以最終畫面相對比例儲存。
5. 展開樣式與動畫設定：大小、字色、背景、透明度、圓角、連接線、出現／消失時間與進場時長。停留時間為 `消失時間 - 出現時間 - 進場時長`；標籤可錯開出現。
6. 使用播放／時間軸預覽整部影片。編輯模式固定顯示全部標籤，選中框與定位點操作提示不會輸出到影片。
7. 優先選擇編輯器內「瀏覽器 MP4」：支援時以本機 Canvas 錄製，需保持頁面前景。若不支援 H.264／MP4、背景中斷或錄製失敗，使用下方「輸出 H.264 MP4」；預設 Full HD／30 FPS，也可選 720p 或 360p。
8. 完成後播放結果、下載。修改專案會使舊的伺服器輸出失效，避免誤下載過期影片。清空工作階段可移除照片與影片。

所有編輯自動同步到目前工作階段。重新整理或連線斷開可能遺失內容，第一版沒有永久專案存檔。照片上傳至 Streamlit 伺服器並只存在記憶體；FFmpeg 暫存壓縮影片會清除。

## 測試

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\verify_export.py --width 1080
node --check frontend\editor.js
node --test tests\animation.test.cjs
```

影片驗證會建立 `artifacts/verification.mp4`、截圖與 JSON 結果（已忽略，不上傳 Git）。使用 5 張自行繪製的室內空間示意，每張 4 秒、中文標籤從左滑入；驗證 H.264、1080×1920、20 秒、600 影格及完整解碼。若電腦較慢可先用 `--width 360`。執行驗證腳本產生的示意圖不代表真實客戶案例或 Gemini 辨識。

UI 測試清單：新增與移動標籤、單獨拖定位點、改文字／樣式、切換照片保留標籤、拖縮圖順序、替換照片、刪除、變更秒數、裁切預覽、七種動畫、實際下載與播放 MP4、清空工作階段。

## Streamlit Community Cloud

1. 將原始碼推送到自己的 GitHub repository，**不要提交 `.venv`、`.tmp`、`.tools`、`.streamlit/secrets.toml` 或使用者素材**。
2. 在 Community Cloud 建立 app，入口 `app.py`，Python 選 3.12。
3. Cloud 讀取 `requirements.txt`；`packages.txt` 安裝 `ffmpeg`、`fonts-noto-cjk`。應用程式的環境檢查會確認 libx264 與中文字型。
4. 第一階段不用 Secrets。第二階段才把 `.streamlit/secrets.toml.example` 的 Gemini 設定放到 Cloud 的 Secrets，真實金鑰不得放在 repository 或前端。
5. 部署後先跑短片，再跑 20 秒 Full HD。**本專案本機成功不代表已公開部署，也不保證免費 Cloud 的效能**；能力不足時介面顯示錯誤，可改用瀏覽器輸出或本機 Streamlit。

Cloud 安裝依據：[官方依賴文件](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)。免費 Cloud 公開 app 可能被其他人使用，目前有張數、時間、檔案大小及程序同時輸出的限制；上線 AI 前需額外加入呼叫限流。

## 專案結構

```text
app.py                    Streamlit 流程、上傳、工作階段與下載
studio/models.py          原始照片、標籤、輸入驗證
studio/rendering.py       等比例裁切、共用 PNG 標籤、逐影格合成
studio/animation.py       可重用動畫時間公式
studio/export.py          FFmpeg 能力檢查、負載控制、H.264 輸出
studio/component.py       自訂元件 Python 介面
frontend/index.html       編輯器版面
frontend/editor.js        拖曳、預覽、照片排序、瀏覽器錄製
frontend/animation.js     前端動畫公式
templates/items.json      第一版模板設定
scripts/verify_export.py  實際 20 秒影片驗證
tests/                    重要資料與動畫測試
docs/FEASIBILITY.md        技術決策與已知限制
.streamlit/               主題、Secrets 範例
```

照片、標籤與模板分離。新增模板可加入 JSON 並註冊於 `template_config`；新的轉場或版型仍需要對應渲染策略，尚未實作的前後對比與特色模板不會以空選项出現。

## 後續階段

- 第二階段：Gemini 視覺 JSON、可見內容辨識、定性信心與待確認、單張重試、免費額度錯誤、批次／工作階段／程序配額限制。AI 失敗仍保留手動流程。
- 第三階段：前後對比與案例特色模板、共用標籤及時間軸。
- 第四階段：使用者 LOGO／背景音樂／品牌結尾、效能與操作優化。

參考影片尚未提供；模板 A 的基礎版以 9:16 照片、圓角標籤、定位點與進場動畫為範圍。沒有下載不明授權音樂、LOGO 或圖片。字型可透過 `STUDIO_FONT_PATH` 指定自己的合法字型檔；Cloud 使用系統 Noto CJK。
