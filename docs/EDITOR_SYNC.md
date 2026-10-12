# 標籤編輯效能與批次同步

修改的程式檔：`app.py`、`studio/component.py`、`studio/sync.py`、`frontend/editor.js`、`frontend/index.html`、`frontend/draft-state.js`、`frontend/label-raster.js`。測試檔：`tests/test_app.py`、`tests/test_sync.py`、`tests/test_synced_video.py`、`tests/draft-state.test.cjs`、`tests/editor-events.test.cjs`。另更新 README、可行性文件與驗證記錄。

## 原本的原因

- `pointermove` 原本只有改座標與重畫，**沒有每次移動就呼叫 Python**；但 `pointerup`／`pointercancel` 會呼叫 `save()`。
- 新增、刪除、鍵盤移動、照片排序及欄位 change 都直接呼叫 `save()`。文字及滑桿 input 另用 350 ms 的 `queueSave()`，因此一次輸入可能因 input debounce 與 change 產生相近的多次同步。
- `save()` 透過 `streamlit:setComponentValue` 送出整個 metadata 清單，Streamlit 因 widget value 改變而 rerun。後端處理完事件還呼叫 `st.rerun()`，形成額外一次執行。
- `invalidate()` 清除整個 `project_payload`，下次 `payload()` 重新編碼所有原始圖片，並用 Pillow 重新產生所有標籤 PNG。新標籤原本只先顯示簡易文字塊，完整樣式依賴伺服器回覆。
- 拖曳每次 move 都直接重畫 Full HD Canvas。大量 pointer events 可造成同一個螢幕更新週期內重複繪製。

## 新流程

1. 新增、刪除、位置、定位點、文字、樣式、動畫、構圖、排序都在前端直接處理。取消 input debounce 自動同步與所有編輯事件的直接 Python 同步。
2. `label-raster.js` 立即產生有字色、背景、透明度、圓角與換行的本地 Canvas 標籤。只在樣式指紋改變時重畫素材。拖曳由 requestAnimationFrame 合併繪製。
3. `draft-state.js` 保存完整草稿與序號；切換照片不替換整份草稿。sessionStorage 只存 metadata，不存原始圖片、影片或 PNG 字型素材。同一 Streamlit 工作階段中的元件重建可恢復。
4. 按「套用變更」才傳一個批次事件，包含 session、nonce、base_revision、seq 與全部照片 metadata。後端以原有 `update_project()` 驗證，整批替換標籤，沒有 append 行為。
5. `studio/sync.py` 用 session／revision 拒絕跨工作階段或過期提交，並記錄最近 100 個 nonce 去重。錯誤回覆不破壞草稿；修改發生在已送出快照之後時，不用回覆覆蓋較新的編輯。
6. 後端在建立自訂元件前讀取 `st.session_state['studio_editor']` 新值並完成交易，同次 rerun 即回傳確認，不再為每次套用額外 rerun。
7. `studio/component.py` 僅在目前工作階段快取原始圖片 data URL 及 PNG 標籤素材。純座標／動畫變更不重畫 PNG，刪除的照片及標籤會移除快取。

## 輸出屏障

- FFmpeg 按鈕先建立唯一輸出請求，元件收到後把最新本地草稿以 `export` 批次送回。Python 確認同一 request、完成驗證與套用後，才呼叫既有 `export_video()`。錯誤或過期請求不啟動渲染。
- 瀏覽器 MP4 同樣先等候套用成功與共用 PNG 素材載入，才建立 MediaRecorder。準備與輸出期間鎖定編輯器，結束後恢復。
- 未套用時使用電腦本機字型，字形與排版可能與伺服器略有差異；套用後使用原有 Python 標籤 PNG 校準，最終預覽與 MP4 使用相同素材與動畫公式。
- 未修改 `studio/rendering.py`、`studio/export.py`、`studio/models.py`、`studio/animation.py`，1080×1920、30 FPS、照片顯示模式與模板不變。

## 已執行自動測試

- Node：11 項通過。合成 DOM 執行真正的 `editor.js`，連續新增 10 個標籤、5 個標籤共 500 次合成 pointer move、修改文字／字型大小／背景／透明度／動畫、刪除與切換照片時，`setComponentValue` 數量為 **0**；一次套用送出 **1** 批。
- 草稿狀態測試：sessionStorage 快照復原、同步期間再次修改、不重複附加標籤、忽略較舊 revision、照片新增／替換／排序／刪除合併、失敗保留草稿及隔離新工作階段。
- Python：15 項通過。Streamlit AppTest 驗證事件讀取、10 個標籤套用、rerun 後仍有 10 個且 revision 不重複增加；輸出按鈕未收到最新快照前不產生影片，收到後才使用新文字及樣式輸出。無效草稿會取消等待中的輸出請求，以免輸出按鈕一直停用。
- 真實影片測試：同步 10 個標籤後輸出 1080×1920 H.264 MP4，完整解碼成功。回傳前端的每個 PNG 與原渲染器產生的素材完全相同；解碼影格的各標籤區域與預期合成影格平均色差每通道小於 8（容許 H.264 壓縮）。
- 素材快取測試：只移動標籤時 PNG 不重新產生；改文字才產生新素材。

## 人工測試範圍

已用本機 Chromium 瀏覽器實際連續點選新增 10 次（原有 1 個，清單增加至 11 個），修改文字為「案例特色 A」、字型大小 96、縮放動畫；切換照片返回、變更輸出解析度引發一般 rerun 後仍保留草稿。刪除 1 個後剩 10 個，連續拖動其中兩個標籤，位置立即更新且維持未套用狀態。未先手動套用，直接由正式按鈕輸出 20 秒 Full HD，介面確認套用成功，播放器回報 1080×1920、20 秒，下載成功。首次輸出約 19.6 秒。

上述瀏覽器操作沒有量測 FPS。合成 DOM 測試也不能代表實體滑鼠／觸控的主觀流暢度。仍需在目標裝置與已部署 Cloud 人工操作：長時間快速拖多標籤、大量長中文字與不同字型、觸控 pointer cancel、網路延遲／斷線、iframe 重建／瀏覽器容量限制、多張高解析照片、Safari／Firefox 的錄製與下載相容性。

整頁重新整理可能重建 Streamlit 工作階段，伺服器照片不保證保留；草稿恢復的保證範圍是**同一工作階段**內的 rerun／元件重建。沒有加入永久照片儲存。
