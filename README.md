# ValueCompass

这是一个最小可运行的财报可视化 Demo：

- 前端：Next.js + ECharts
- 后端：Flask + AKShare
- AI 分析：OpenAI-compatible API（从后端发起调用）

## 当前功能

1. 资产负债结构图
2. 营收与市值趋势图
3. 净利润与市值趋势图
4. 市盈率趋势图
5. OpenAI 财报综合分析

## 目录

- [backend/app.py](D:/github/ValueCompass/backend/app.py)
- [backend/requirements.txt](D:/github/ValueCompass/backend/requirements.txt)
- [backend/.env.example](D:/github/ValueCompass/backend/.env.example)
- [frontend/app/page.tsx](D:/github/ValueCompass/frontend/app/page.tsx)
- [frontend/app/globals.css](D:/github/ValueCompass/frontend/app/globals.css)

## 后端启动

```bash
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe -m pip install -r requirements.txt
D:\github\ValueCompass\.venv312\Scripts\python.exe app.py
```

后端默认地址：

```text
http://127.0.0.1:5001
```

## 前端启动

```bash
cd D:\github\ValueCompass\frontend
npm install
npm run dev
```

前端默认地址：

```text
http://127.0.0.1:3000
```

## OpenAI 配置

后端通过环境变量读取 OpenAI 配置。你可以参考：

- [backend/.env.example](D:/github/ValueCompass/backend/.env.example)

需要的变量：

```text
OPENAI_BASE_URL=https://api.openai-proxy.org/v1
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-nano-2026-03-17
OPENAI_TEMPERATURE=0.1
```

说明：

- 我没有把真实 key 写进仓库
- 你贴的 `max-context-chunks` 不是 OpenAI Python SDK 的原生参数，所以没有直接映射到后端配置

## AI 分析接口

```text
POST /api/ai-analysis
```

请求体：

```json
{
  "stock": "600519",
  "period": null,
  "years": 8
}
```

如果没有配置 `OPENAI_API_KEY`，后端会返回清晰错误信息。
