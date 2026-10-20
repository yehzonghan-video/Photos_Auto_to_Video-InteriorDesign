# 第五階段：空間導覽

## 操作方式

1. 模板選擇「空間導覽」。原本裝修項目介紹、裝修前後對比仍可使用。
2. 展開「空間導覽：平面圖與MP4素材」，選擇PNG／JPG／JPEG平面圖。也可以先建房間，再上傳主素材。
3. 在編輯器「平面圖與房間」輸入房名，點圖建立位置。要建立下一個房間，按「新增房間（再點圖）」；點選既有房間可改名，再點圖可重新定位。房間清單顯示引用數，選取後列出使用片段。
4. 照片沿用原本上傳區；MP4使用導覽素材區。選檔成功後自動加入來源，編輯器自動追加導覽片段；同次選檔在一般rerun不重複處理。
5. 在既有時間軸選取片段，於右側「所在空間」指定房間。未指定時仍顯示平面圖，但沒有紅點。可以重用同一來源建立多個獨立片段。
6. 照片沿用完整顯示／裁切、縮放、構圖及標籤。影片可調整起訖、構圖、原音靜音與音量，並使用相同文字／PNG與時間軸；PNG可以跨片段。
7. 播放或暫停檢查，再按相鄰的「輸出 H.264 MP4」或「下載 ZIP」。沿用點擊當下快照、自動同步及一鍵ZIP，不需要先套用。

更換平面圖會保留房名與片段關聯，但所有舊位置改成「待定位」。逐一選房間並點新圖確認之前，影片不顯示這些位置點。移除平面圖也保留房間與時間軸。刪除被引用的房間會列出影響、要求確認，繼續後只清除相關片段的房間指定，不刪除片段。

## 與既有架構整合

新增`templates/tour.json`，以同一模板選單進入；沿用`frontend/editor.js`、`timeline-model.js`、`timeline-ui.js`及`studio/export.py`，沒有第二套時間軸或獨立MP4輸出器。導覽片段是現有主素材軌道的新類型，標籤與PNG仍用既有動畫、層級與時間規則。

`tour.clips`為導覽播放順序的唯一來源，片段開始時間由前面片段長度累加，含啟用的0.3秒封面。排序與裁切後後續時間立即更新。每個導覽片段有自己的文字與構圖副本，修改不會改動另外兩套模板。建立照片片段時複製當時照片標籤；之後重新做AI分析不會自動覆寫已編輯的導覽標籤，可手動調整或重用來源新增片段。

平面圖固定在內圈安全區右上方，完整等比例顯示，最高420個設計像素。背景、平面圖及紅點合為一層後再套透明度；此層在正文、LOGO、文字與PNG之上，避免定位被蓋住。封面不顯示平面圖。安全區提示不輸出。

幾何設定共用`frontend/tour-layout.json`，以1080×1920為設計座標；Python與JavaScript使用相同等比例縮放與四捨五入，360p／720p輸出由完整畫面縮小。其他比例未新增。

## 資料結構

```json
{
  "tour": {
    "visible": true, "size": 0.3, "opacity": 1, "dot_size": 12,
    "rooms": [{"id": "room-id", "name": "客廳", "x": 0.25, "y": 0.5, "needs_review": false}],
    "clips": [{
      "id": "clip-id", "type": "tour_clip", "kind": "video", "source": "video-id",
      "name": "客廳.mp4", "room_id": "room-id", "duration": 3,
      "in": 1, "out": 4, "muted": true, "volume": 1,
      "crop": {"fit": "contain", "zoom": 1, "crop_x": 0.5, "crop_y": 0.5}, "labels": []
    }],
    "overlays": [], "seen_sources": [], "plan_id": "plan-id"
  }
}
```

平面圖素材另存`FloorPlan(id,name,original,width,height)`；影片另存`VideoAsset(id,name,data,width,height,duration,has_audio,poster)`，片段只引用來源ID。房間相對座標0～1，所有使用同房間的片段共用該位置；切到下一片段立即換點，不做路徑移動、不沿用上一片段的房間。沒有AI平面圖辨識或自動空間判斷。

## 影片與音訊

匯入MP4時由現有FFmpeg套件檢查格式、時長、尺寸與旋轉，再一次正規化為H.264／30 FPS／最高720×1280、AAC立體聲44100 Hz。保持比例、不放大來源，校正旋轉並移除旋轉metadata；可變幀率轉固定幀率。以實際解碼影格數決定裁切上限，避免AAC尾端讓容器時間多出一影格。

這是節省記憶體與ZIP大小的工作副本，**不保留原始大影片**；請另行保留自己的原檔。最終仍可輸出1080×1920／30 FPS，但720p工作副本不會恢復原始4K細節。FFmpeg無法解碼或逾時時顯示明確錯誤，原專案保留；並不保證所有相機的MP4編碼都能匯入。

影片預覽使用HTMLVideo解碼，再依共用構圖畫入現有Canvas；FFmpeg輸出逐片段解碼RGB影格，套用同一構圖與標籤合成。影片裁切對齊30 FPS，可重複引用同一來源。預覽解碼／seek可能短暫等候影格，精確輸出以FFmpeg為準。

原音預設靜音。開啟後依影片起點、終點、片段音量放到全片同一時間基準，照片／封面補靜音；沒有音軌的影片可正常輸出。原音只解碼一次進入混音，不同時重複取音。若有BGM，沿用既有音量、循環與可調淡出，與原音相加並使用0.95峰值限制器；音量不會自動做響度正規化，仍應試聽。

## 限制與Cloud注意事項

| 項目 | 限制 |
| --- | --- |
| 來源照片 | 維持12張與既有工作副本限制 |
| 平面圖 | 1張、8 MB、1200萬畫素、靜態PNG／JPEG |
| MP4來源 | 最多3個，每個20 MB、1～60秒、最多16777216畫素；工作副本合計40 MB |
| 房間／導覽片段 | 30個／40個；片段1～20秒，全片含封面最多120秒 |
| 平面圖或影片入庫 | 專案素材總量需在145 MB內，保留打包空間 |
| ZIP | 維持壓縮前／後160 MB、設定JSON 4 MB，打包前另檢查素材大小 |
| 輸出 | 維持9:16、30 FPS，360／720／1080寬；既有輸出鎖與逾時保護 |

145 MB是新增平面圖／影片時的入庫檢查；後續其他素材仍受各自既有限制及ZIP總量檢查，不代表全站所有上傳入口新增了同一總量攔截。

影片不轉Base64傳到前端。正規化影片使用既有Streamlit static serving，隨機不可猜測的64位十六進位檔名、閒置兩小時清除，暫存總量160 MB；長時間後可按「重新整理素材連結」。**持有連結者可讀取，static網址不受應用程式密碼保護，不應分享。** 磁碟檔案屬短期預覽快取，不寫入Git；工作階段及伺服器重啟仍可能失去未備份草稿。

未提高Cloud的上傳上限、未加入付費服務。已在本機實際轉碼與Full HD輸出，但這不代表Streamlit Cloud資源足夠；部署後先以360p短片驗收，再測實際素材。仍需確認Cloud static路由、長片耗時、尖峰記憶體、暫存容量與不同來源編碼。滿載時應縮短／減少素材，不應略過安全限制。

目前可刪除導覽片段並重用來源；未提供獨立刪除影片來源的介面，3個來源用滿後可使用新工作區。後續可增補有引用保護的來源管理，但本階段未加入專業剪輯功能。

## ZIP與版本安全

沒有導覽資料的原專案繼續輸出版本1。含平面圖、影片或保留的導覽房間／片段等資料時使用版本2；本版讀取版本1及2，舊專案不被強制轉換。舊版程式無法開啟版本2，請先更新工作室。

版本2在同一manifest保留tour資料；`media/plan/image`保存平面圖原始bytes，`media/videos/`每個影片來源只存一份正規化MP4。縮圖與公開預覽網址不入ZIP，讀取時重建；重用片段不重複存影片。照片、PNG、BGM、封面、正文、另外兩模板資料仍保留。匯入先驗證雜湊、大小、格式及引用，再一次替換工作區；不解壓外部路徑、不保存Secrets、不呼叫Gemini。

新增內容納入現有前後端內容雜湊：平面圖／影片bytes摘要、房間與片段、顯示設定、裁切、音量及動畫。UI選取、播放、seek、面板開關、來源去重記錄不屬內容版本。維持草稿sequence／舊回應保護、輸出快照隔離、舊MP4保留與ZIP備份確認。匯入與清空會更新新上傳欄位epoch，避免舊選檔重新覆蓋專案。

## 測試與驗收

2026-10-20最終完整回歸：**171項Python、94項JavaScript全部通過**，包含第一至第四階段原有測試；`compileall`及`git diff --check`亦通過。第五階段新增14項Python、3項前端事件測試，並擴充既有替換照片／舊回應保護測試。測試未呼叫Gemini。

本階段新增`tests/test_tour.py`及既有編輯器事件測試，覆蓋模板註冊、平面圖各比例、Python／JS幾何一致、房間增刪改與使用中刪除確認、重新定位、未指定點、混合時間軸、影片裁切、無音軌／靜音、24／60 FPS、VFR、實際旋轉metadata、大小／引用錯誤、逾時、ZIP往返及固定版本快照。

真實FFmpeg測試使用自行建立素材，輸出**1080×1920／30 FPS、3秒90影格**混合照片→影片→照片，完整解碼成功；抽影格檢查裁切內容、客廳→廚房→無點切換，音訊RMS驗證原音與BGM混合。另測影片單獨輸出、版本2媒體去重、舊版本1匯入，以及不先套用的protocol 3 ZIP／MP4真實背景工作。不是以Mock冒充實際影音輸出。

本機內建瀏覽器已實際驗證：登入、三個模板入口、沒有主素材時先上傳平面圖、點圖建立房間、MP4選檔自動追加、選取房間、播放影片及右上平面圖紅點。房間刪除／重定位、長串快速拖曳與音訊主觀試聽尚未在真實瀏覽器逐項驗收；對應部分有合成DOM／AppTest及FFmpeg測試，不能等同所有瀏覽器已通過。

執行回歸（Windows PowerShell）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.test.cjs
.\.venv\Scripts\python.exe -m compileall -q app.py studio tests
git diff --check
```

部署後人工驗收：

1. Chrome／Edge及手機各上傳橫／直平面圖，建立三個房間，兩個片段共用一房間；改名、改點、刪除使用中房間並取消／確認。
2. 更換平面圖，確認房名／時間軸保留、未確認位置不輸出；重新點圖後恢復紅點。
3. 加照片與有音／無音MP4、重用影片，調起訖／排序／構圖、跨片段PNG與文字，快速seek／拖曳後重新執行，檢查草稿與版本。
4. 分別預覽靜音、原音、BGM混音並試聽；測實際手機旋轉／可變幀率／HEVC來源與不支援編碼提示。
5. 不按套用直接下載ZIP，確認檔案保存，再匯入、繼續修改並輸出；輸出期間另改房間，確認本次成品維持點擊時版本。
6. Cloud先360p後1080p輸出，檢查完整播放、紅點及文字位置、音訊、逾時提示及失敗後舊MP4保留。確認網址過期後重新整理素材連結可恢復。

## 主要檔案

新增：`templates/tour.json`、`frontend/tour-layout.json`、`frontend/tour-model.js`、`frontend/tour-editor.js`、`studio/tour.py`、`studio/tour_video.py`、`studio/tour_ui.py`、`tests/test_tour.py`、本文件。

整合：`app.py`、`studio/bootstrap.py`、`studio/component.py`、`studio/rendering.py`、`studio/export.py`、`studio/output_jobs.py`、`studio/sync.py`、`studio/versioning.py`、`studio/project_io.py`、`studio/photo_intake.py`、`frontend/index.html`、`frontend/editor.js`、`frontend/timeline-model.js`、`frontend/timeline-ui.js`、`frontend/photo-history.js`、`frontend/draft-state.js`、`frontend/content-version.js`、`frontend/content-schema.json`、`tests/editor-events.test.cjs`、`tests/pairing-history.test.cjs`、`.gitignore`、`README.md`及`docs/PROJECT_FILES.md`。
