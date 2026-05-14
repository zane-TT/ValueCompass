# Backend

`backend/` 是当前项目的 FastAPI API，同时可以托管 `frontend/out` 静态前端。

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

## 生产式单入口启动

FastAPI 可以统一返回前端页面和后端 API。先构建前端静态产物：

```powershell
cd D:\github\ValueCompass\frontend
npm install
npm run build
```

然后启动后端：

```powershell
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe -m pip install -r requirements.txt
D:\github\ValueCompass\.venv312\Scripts\python.exe app.py
```

启动后访问：

```text
http://127.0.0.1:5001
```

路由说明：

```text
/              前端页面
/_next/...     前端静态资源
/api/...       后端 API
/docs          FastAPI 自动接口文档
```

## 开发模式

开发时可以分开启动，前端支持热更新。

后端：

```powershell
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe app.py
```

前端：

```powershell
cd D:\github\ValueCompass\frontend
npm install
npm run dev
```

前端开发地址：

```text
http://127.0.0.1:3000
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

本地开发时仍然可以单独运行 `npm run dev`；生产式运行时建议使用 `npm run build` 产出静态文件，再由 FastAPI 统一托管页面和 `/api/*`。
