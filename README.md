# 台灣航空氣象監測網站

獨立 Flask 專案，不會改動 Discord Bot。支援 METAR、TAF（預報時段轉台灣時間）、簡易風險提示、規則式中文摘要、Leaflet 台灣機場互動地圖。

## Windows / PyCharm 本機啟動

1. 解壓縮，PyCharm 使用 Open 開啟 `aviation_weather_web` 資料夾。
2. PyCharm Terminal 輸入 `python -m pip install -r requirements.txt`。
3. 輸入 `python app.py`。
4. 瀏覽器開啟 http://127.0.0.1:5000 。

## Render 公開部署（平台免費方案如仍提供）

1. 在 GitHub 建立新 repository（例如 `aviation-weather-web`），上傳解壓後資料夾內的所有檔案（包含 `templates/`、`static/`、`render.yaml`）。**不要上傳任何 API Key、Discord Token 或 `.env`**。
2. 登入 https://dashboard.render.com/ ，連結 GitHub，選擇 **New > Blueprint**，選取該 repository，確認 `render.yaml` 建立 Web Service。若免費方案選項不存在，依平台當時方案選擇或改用其他支援 Python 的主機。
3. 等部署成功，開啟 Render 顯示的 `https://...onrender.com` 網址即可公開存取。
4. 如 Blueprint 不適用，手動 New > Web Service，Build Command 設 `pip install -r requirements.txt`，Start Command 設 `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 app:app`。

## 限制與注意

- 無 OpenAI API 費用；本地摘要為規則式，不是生成式 AI。
- AviationWeather 可能限制請求頻率或暫時無資料；伺服器有每機場 120 秒快取。
- 地圖需要連網，使用 OpenStreetMap 公開圖磚，應遵守其使用政策；流量大時應改用合適圖磚供應商。
- TAF 每個 TEMPO/BECMG 段落僅解析**本段明示**條件，可能繼承前段風、雲、能見度；不可視為完整逐時預報。
- FAA 類別為教學用途，並非台灣法規判斷；能見度以公尺近似英里門檻。
- TAF 跨月處理依報文發布時間（若 API 未提供，依查詢日推算），極端情況應核對原始報文。
- 公開主機可能休眠、額度受限，部署後需測試是否可存取 AviationWeather API。
- 本站不提供航務決策建議。
