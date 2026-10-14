# 共用密碼入口

工作室使用一組共用密碼，沒有資料庫、個別帳號或永久登入。`app.py`在初始化照片、接收編輯器同步、顯示AI面板和輸出控制之前執行密碼驗證。未設定密碼、保留範例密碼或驗證失敗，都不開放製片功能。

## 設定

本機：在已被Git忽略的`.streamlit/secrets.toml`新增以下設定，把範例換成自己的密碼；保留原有Gemini設定。

```toml
APP_PASSWORD = "YOUR_PASSWORD_HERE"
```

Community Cloud：在現有App的**Settings → Secrets**加入相同設定。儲存後重新執行App。入口仍是`app.py`，不需要新增套件。也可由伺服器設定`APP_PASSWORD`環境變數；Secrets有設定時優先使用Secrets。空值、非文字、`YOUR_PASSWORD_HERE`及`CHANGE_ME`都會視為尚未設定。

密碼只在伺服器讀取與驗證，不會加入編輯器元件參數、照片資料、AI請求或Git。Session State只保存程序加鹽的驗證摘要；送出密碼後立即移除輸入值。不要將真實密碼貼在README、JavaScript或GitHub。

## 操作與限制

- 進入頁面後輸入共用密碼，再按「進入工作室」。正常rerun與清空作品不會要求重複輸入。
- 側邊「登出」會清除本工作階段的照片、AI結果、影片、草稿同步資料及驗證摘要；請先下載成果。
- 更新設定中的密碼後，下次執行會要求重新驗證。重啟伺服器或失去瀏覽器工作階段也需要重新登入。
- 同一工作階段連續錯誤5次會暫停60秒，可按「重新檢查等待時間」更新狀態。沒有阻塞睡眠或自動重試；這項限制以工作階段為範圍，重新建立工作階段會重新計算，並非全站封鎖。
- 這是工作室入口的共用密碼，不提供帳號管理、權限角色、密碼找回或跨裝置作品保存。原有張數、AI限流及渲染限制仍保留。

## 驗證

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_access -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/*.test.cjs
```

密碼測試透過真實Streamlit AppTest表單送出，不繞過認證：缺漏／錯誤設定、錯誤密碼、輸入清除、登入與rerun、清空作品、登出、密碼輪替、冷卻與環境變數優先順序。原有AppTest製片回歸也先經同一登入表單，再測照片、AI Mock與真實MP4輸出；測試用密碼僅用於測試，不能拿來部署。

本次57項Python、35項Node測試通過；登入後實際產生與解碼H.264 MP4，包含原有1080×1920對比、文字淡化、PNG及同步測試。AI驗證仍為Mock，沒有額外使用真實Google呼叫。

Community Cloud實際Secrets設定、實體瀏覽器的登入／登出，以及不同瀏覽器與多人工作階段仍需部署後人工確認。本次沒有替使用者設定雲端實際密碼。
