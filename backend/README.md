# Backend

`backend/` 是当前项目的 Flask API。

已提供接口：

- `GET /api/balance`
- `GET /api/revenue-market-cap`
- `GET /api/profit-market-cap`
- `GET /api/pe-trend`
- `POST /api/ai-analysis`

## 安装

```bash
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

## 启动

```bash
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe app.py
```

默认地址：

```text
http://127.0.0.1:5001
```

## OpenAI 配置

后端读取这些环境变量：

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_TEMPERATURE`

示例见 [backend/.env.example](D:/github/ValueCompass/backend/.env.example)。

推荐本地设置为：

```text
OPENAI_BASE_URL=https://api.openai-proxy.org/v1
OPENAI_MODEL=gpt-5.4-nano-2026-03-17
OPENAI_TEMPERATURE=0.1
```

不要把真实 `OPENAI_API_KEY` 提交进仓库。

## 接口示例

```text
GET  http://127.0.0.1:5001/api/balance?stock=600519
GET  http://127.0.0.1:5001/api/revenue-market-cap?stock=000333&years=8
GET  http://127.0.0.1:5001/api/profit-market-cap?stock=600519&years=8
GET  http://127.0.0.1:5001/api/pe-trend?stock=600519&years=8
POST http://127.0.0.1:5001/api/ai-analysis
```

`/api/ai-analysis` 请求体示例：

```json
{
  "stock": "600519",
  "period": null,
  "years": 8
}
```

## Notes

Start the backend before the frontend if you want to verify the full app flow locally.
