# 技術決策與部署限制

## 免費輸出路徑

1. **優先瀏覽器 Canvas + MediaRecorder**：依執行環境使用 `isTypeSupported()` 偵測 `video/mp4;codecs=avc1`。只有可確認 H.264 的 MIME 才啟用。錄製需實際播放長度，視窗必須保持前景；不宣稱所有瀏覽器都能輸出 MP4 或保證恆定 30 FPS。
2. **可靠替代方案 Pillow + FFmpeg/libx264**：從原始圖片依序產生影格，以 pipe 送入編碼器；固定 30 FPS、H.264、yuv420p、MP4 faststart。沒有影片 API 費用。伺服器 CPU／記憶體與渲染時間仍有成本限制。
3. **兩個路徑共用照片、PNG 標籤素材、座標及動畫公式**：避免瀏覽器字型排版與伺服器字型不一致。Canvas 的動畫由 JavaScript 計算，伺服器使用對應 Python 模組；測試比較兩者的姿態公式。瀏覽器錄製受排程影響，若需要固定影格率請使用 FFmpeg。

標籤編輯改採前端草稿與批次套用：未套用時用本機字型即時顯示，套用後回傳共用 PNG 校準預覽。兩個輸出入口都會先確認最新草稿套用完成。詳見 [同步架構與測試](EDITOR_SYNC.md)。

## Streamlit Community Cloud

官方支援 `requirements.txt` Python 依賴與 `packages.txt` 中的 Debian apt 套件。本專案宣告 `ffmpeg`、`fonts-noto-cjk`，啟動時實際檢查 FFmpeg 是否提供 `libx264`、中文字型是否存在。Windows 沒有 FFmpeg 時使用 imageio-ffmpeg 隨套件提供的執行檔。

**本機驗證不能證明 Cloud Full HD 效能。** Cloud 實際部署尚未進行；部署後必須先確認環境檢查成功，再跑 360p／720p 短片與 1080p 20 秒案例。若服務資源不足，可用支援瀏覽器輸出，或在自己電腦執行相同專案輸出。第一版不使用付費主機。

## 隱私與負載界線

- 照片原始或最佳化工作 bytes 僅保留在 `st.session_state`；前端以記憶體 data URL 接收較小預覽圖。不是純瀏覽器本地應用，照片仍會傳至 Streamlit 伺服器。
- FFmpeg 僅將壓縮 MP4 與診斷寫入每次獨立的暫存目錄，正常完成、失敗與逾時均清除；程序突然被終止的清理由主機暫存環境負責。
- 不使用資料庫、照片全域快取、磁碟上傳資料夾或照片記錄；下載影片留在目前工作階段，清空專案可移除參照。
- 每工作階段最多12張、每檔傳輸200 MB、單張1～20秒、總長120秒、單張12標籤。工作照片以單張15 MB／3200萬畫素、合計80 MB／6000萬畫素為自動最佳化門檻，超標時縮小工作副本，不直接拒絕一般照片；原檔優先與預覽分離詳見 [PHOTO_UPLOAD.md](PHOTO_UPLOAD.md)。
- 一個 Python 程序同時僅允許一個 FFmpeg 工作；最長渲染 5 分鐘。公開網址已加入共用密碼入口；渲染限制仍是基本負載控制。密碼與工作階段限制見 [ACCESS.md](ACCESS.md)。第二階段已加入 Gemini 每工作階段及程序共用限流，詳見 [AI.md](AI.md)；程序重新啟動後共用上限會重置。

## 本階段範圍

完成手動標籤、照片管理、裁切、七種進場動畫、預覽與MP4；第二階段加入Gemini，第三階段加入時間軸與透明PNG。第四階段新增裝修前後對比：獨立來源分類／裁切、三種模式與真遮罩，仍使用同一FFmpeg逐影格管線，沒有新增依賴或付費服務。其他特色模板、音樂與品牌結尾留待後續，詳見 [時間軸與PNG](TIMELINE_PNG.md)、[前後對比](COMPARISON.md)。

目前未收到「老屋翻新最低88萬起」參考影片，所以基礎版沒有聲稱複製該影片風格。

## 依據

- [Streamlit Cloud 依賴安裝](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Streamlit 自訂元件](https://docs.streamlit.io/develop/concepts/custom-components/components-v1/intro)
- [MediaRecorder MIME 與相容性](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/mimeType)
- [WebCodecs 支援偵測](https://developer.mozilla.org/en-US/docs/Web/API/VideoEncoder/isConfigSupported_static)
- [FFmpeg 輸入、編碼及 pipe 文件](https://ffmpeg.org/ffmpeg.html)
