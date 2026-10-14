# BGM與可調淡出

兩套模板共用一首上傳BGM，從全片0秒開始，包含0.3秒封面。預設音量50%、循環播放、結尾1秒線性淡出；只調整BGM，既有文字／PNG動畫不變。

## 使用

1. 加入照片，展開上方「背景音樂 BGM（預設1秒淡出）」。
2. 選擇MP3、WAV、M4A、OGG或FLAC，按「加入／替換BGM」。單檔20 MB，超長音樂只保留前120秒，最低0.1秒。使用自行提供且有權使用的素材；沒有預設下載音樂。
3. 下方編輯器BGM面板可啟用／關閉、改音量、循環及淡出。淡出0～10秒，0為不淡出。設定在JavaScript本地即時修改，不逐次觸發Streamlit。
4. 預覽會播放音樂；暫停、跳轉、回到編輯或換音樂會停止舊音源，再播放依目前全片時間開始。
5. 套用或輸出時整批同步最新音量／淡出等設定。上方「移除BGM」只移除音樂；清空工作階段或登出一併清除。

短音樂預設循環至影片末尾，淡出套在最後1秒。關閉循環時，淡出套在音樂結尾，剩下影片維持靜音。設定的淡出超過實際播放長度時自動縮至播放長度。沒有音樂或關閉BGM時沿用原先無音軌輸出。

## 資料與輸出

- `MusicAsset`保存音樂ID、名稱、工作階段PCM WAV、有效秒數及是否截短。上傳透過FFmpeg限時解碼成44.1kHz立體聲16-bit WAV，供預覽與輸出使用相同音訊。
- 解碼暫存檔完成／失敗後均刪除，沒有永久音樂庫或資料庫。工作階段最多一首BGM；前端音樂只在目前頁面記憶體，sessionStorage草稿只保存設定，不保存音訊／base64。
- `music`設定包含`enabled/source/volume/fade_out/loop`，與標籤及模板分開。上傳／移除更新伺服器來源；較舊回覆不覆蓋未同步音量或淡出。Python批次驗證失敗不部分修改專案。
- FFmpeg沿用原逐影格影片管線，僅加入BGM輸入、音量與`afade`、不足時補靜音、依實際影片影格數裁切及AAC編碼，不另建渲染系統。[FFmpeg音訊濾鏡](https://ffmpeg.org/ffmpeg-filters.html#afade)
- 瀏覽器預覽透過Web Audio排定增益；錄製透過MediaStreamAudioDestinationNode把同一音源加入Canvas錄影串流，要求H.264＋AAC支援。[Web Audio音軌](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamAudioDestinationNode)
- 首次播放解碼後快取音訊，後續播放／跳轉重用；離開頁面、暂停及录製結束會停止音源並斷開節點。

FFmpeg需具備音樂格式解碼器與AAC編碼器，本機已实际驗證。Community Cloud仍沿用`packages.txt`的FFmpeg，不新增套件或付費服務；部署後必須實测編碼能力與負載。120秒PCM音樂約21 MB，預覽傳輸額外占用記憶體與網路；建議先用短片驗證。沒有新增音樂時間軸剪輯、淡入、交叉淡化或多首混音。

## 測試結果

79項Python、44項Node測試通過。新增測試使用自行生成正弦波，不是假音軌或未知授權音樂：

- 真正FFmpeg將WAV／MP3／M4A／OGG／FLAC解碼、損壞檔案與設定範圍處理。
- 真正產生Full HD、30 FPS、H.264＋AAC／44.1kHz立體聲MP4；解碼音訊量測50%音量、短音樂循環及最後1秒線性下降。
- 前後對比與不循環短音樂實際輸出；音樂結束後靜音，影片仍保留完整2秒。
- AppTest驗證最新BGM設定批次輸出、移除與清空；前端合成DOM驗證100次音量／淡出修改沒有Python事件、rerun／重建保存、輸出含最新設定。
- 模擬AudioContext驗證增益排程、循環位置、錄製音軌與停止節點，不等同實體音效裝置測試。
- 桌面瀏覽器實際WAV檔案選擇／上傳、加入BGM、動畫預覽、瀏覽器MP4錄製及頁內播放成功，產生的短片顯示2.312秒且播放readyState為4。測試工具不支援內嵌頁面的Blob下載，未取得該錄製檔進行音軌或淡出量測；這項列為人工待測，沒有把FFmpeg測試冒充瀏覽器音軌驗證。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/*.test.cjs
```

人工待測：使用自己的合法音樂測完整片長、實體喇叭聆聽預覽與暫停／跳轉、在一般Chrome／Edge下載瀏覽器MP4確認有音軌及淡出、其他瀏覽器與Cloud完整操作。不支援瀏覽器音樂預覽或H.264＋AAC時顯示說明，使用FFmpeg成片下載播放；瀏覽器錄製仍無法保證固定30 FPS。

修改檔案：`app.py`、`studio/music.py`、`studio/component.py`、`studio/sync.py`、`studio/export.py`、`frontend/music.js`、`frontend/draft-state.js`、`frontend/editor.js`、`frontend/index.html`及BGM測試／文件。沒有改Gemini核心、模板或文字／PNG動畫預設。

## Cloud舊模組介面修復

若出現`payload() takes from 1 to 8 positional arguments but 10 were given`，代表執行中的payload仍是加入BGM前的8參數版本，而app.py已傳入新版10個參數，並不是照片或音樂格式錯誤。可能是熱更新時保留舊匯入，或部署檔案未同步；新增`studio/bootstrap.py`在登入後核對三個製片模組版本及BGM參數，僅不相容時重新載入編輯器、同步與輸出模組。一般rerun不重載、不清除照片／標籤／音樂設定，既有FFmpeg輸出鎖仍保留。

payload改為具名參數呼叫，避免新增功能依賴十個位置的排列。Cloud Logs可搜尋`APP_RUNTIME_RELOAD`查看哪些模組不相容。若磁碟檔案仍是舊版本，頁面明確提示部署版本不一致，不會忽略BGM或改輸出無聲影片。

更新後重新進入頁面。仍遇舊版介面時，管理者可在右下`Manage app → ⋮ → Reboot app`重新啟動。[Streamlit官方重啟說明](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app)。重啟會清除目前記憶體中的照片／草稿，先下載仍可取得的成果。

修復測試以舊8參數payload／不含BGM的export及舊sync模組重現，验证自動重載、輸出鎖不被替換、一般rerun不重載、部署檔案不完整時明確報錯，以及AppTest既有照片／人工標籤／音樂淡出設定保留。此為本機模擬熱更新驗證，Cloud實際狀態仍需更新後確認。
