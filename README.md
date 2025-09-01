# Compiler TA Bot

一個專為九格文 (Nine Grids) 編譯器課程設計的 Discord 助教機器人，能夠協助教師和助教管理課程問題、批改答案並自動化工作流程。

## 功能特色

### 🔐 使用者認證
- 支援九格文平台的登入/登出功能
- 安全的 Session 管理
- 登入狀態檢查與維護

### 📝 問題管理
- 取得指定問題的詳細內容
- 顯示問題的章節、標題、內容和參考答案
- 支援 Markdown 格式的問題顯示

### 📋 答案查看與批改
- 自動取得學生繳交的答案
- 批改介面，支援通過/拒絕操作
- 可添加批改備註
- 批量查看答案（可設定顯示數量）

### ⏰ 自動化任務
- 定期自動取得新的答案繳交
- 可設定檢查間隔時間和執行持續時間
- 支援多個問題的並行監控
- 任務管理與停止功能

### 🌐 網址快速存取
- 快速顯示九格文平台各頁面網址
- 支援首頁、登入、使用者、章節、問題、答案、批改等頁面

## 安裝與設定

### 環境需求
- Python 3.13+
- Discord Bot Token
- 對九格文平台的網路存取

### 1. 使用 Poetry（推薦）

```bash
# 複製專案
git clone <repository-url>
cd compiler_TA_bot

# 安裝依賴
poetry install

# 設定環境變數
cp .env.example .env
# 編輯 .env 檔案，填入您的 DISCORD_TOKEN
```

### 2. 使用 Docker

```bash
# 複製專案
git clone <repository-url>
cd compiler_TA_bot

# 設定環境變數
cp .env.example .env
# 編輯 .env 檔案，填入您的 DISCORD_TOKEN

# 使用 Docker Compose 啟動
docker-compose up -d
```

### 3. 手動安裝

```bash
# 複製專案
git clone <repository-url>
cd compiler_TA_bot

# 安裝依賴
pip install discord.py beautifulsoup4 lxml requests python-dotenv

# 設定環境變數
cp .env.example .env
# 編輯 .env 檔案，填入您的 DISCORD_TOKEN

# 執行機器人
python app.py
```

## Discord 指令

### 認證相關
- `/check_login` - 檢查登入狀態
- `/login <username> <password>` - 登入九格文平台
- `/logout` - 登出九格文平台

### 問題與答案
- `/fetch_problem <number> [disable_md]` - 取得指定問題內容
- `/fetch_answers <number> [limit] [ref] [disable_md]` - 取得問題的繳交答案
- `/show_url [page]` - 顯示九格文平台頁面網址

### 自動化任務
- `/set_task <number> [limit] [ref] [disable_md] [interval] [duration]` - 設定定期取得答案的任務
- `/stop_task [number]` - 停止指定或選擇要停止的任務

### 管理員指令
- `!sync` - 同步 Discord slash 指令（僅機器人擁有者可用）

## 參數說明

- `number`: 問題編號
- `limit`: 顯示答案數量（預設 3）
- `ref`: 是否顯示參考答案（預設 False）
- `disable_md`: 是否禁用 Markdown 格式（預設 False）
- `interval`: 任務執行間隔秒數（預設 150）
- `duration`: 任務持續時間分鐘數（預設 240）

## 技術架構

### 主要依賴
- **discord.py**: Discord API 介面
- **beautifulsoup4 + lxml**: HTML 解析
- **requests**: HTTP 請求處理
- **python-dotenv**: 環境變數管理

### 核心模組
- **認證系統**: 管理使用者登入狀態和 Session
- **UI 元件**: Modal 和 View 組件提供互動介面
- **任務調度**: 基於 discord.ext.tasks 的定期任務系統
- **批改系統**: 自動化的答案批改流程

## 開發資訊

- **作者**: garyellow (gary20011110@gmail.com)
- **版本**: 0.1.0
- **專案類型**: Discord Bot
- **授權**: 請參閱 LICENSE 檔案

## 注意事項

1. **安全性**: 請妥善保管您的 Discord Bot Token，不要將其提交到版本控制系統
2. **網路連接**: 機器人需要能夠存取九格文平台 (140.115.59.182)
3. **權限設定**: 確保機器人在 Discord 伺服器中有適當的權限
4. **資源使用**: 長時間運行的任務可能會消耗較多資源，請適當設定間隔時間

## 故障排除

### 常見問題

1. **登入失敗**: 檢查使用者名稱和密碼是否正確
2. **無法取得答案**: 確認已正確登入且有權限存取該問題
3. **任務不執行**: 檢查網路連接和登入狀態
4. **機器人離線**: 檢查 Discord Token 是否正確設定

### 日誌查看

機器人使用標準的 Python logging 模組，日誌訊息會輸出到控制台。

## 貢獻

歡迎提交 Issue 和 Pull Request 來改善這個專案！
