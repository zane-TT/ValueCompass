# 财报可视化分析系统

当前仓库收敛为两个图表功能：

1. 资产负债结构图
2. 业绩和市值趋势对比图

前后端结构：

- `backend/`：Flask 后端 API
- `frontend/`：Next.js 前端页面

## 安装依赖

### 后端

```bash
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

### 前端

```bash
cd D:\github\ValueCompass\frontend
npm install
```

## 启动命令

### 启动 Flask 后端

```bash
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe app.py
```

默认地址：

- `http://127.0.0.1:5001`

### 启动 Next 前端

```bash
cd D:\github\ValueCompass\frontend
npm run dev
```

默认地址：

- `http://127.0.0.1:3000`

## 接口

### 1. 资产负债结构图

```text
GET /api/balance?stock=600519&period=20250630
```

### 2. 业绩和市值趋势对比图

```text
GET /api/revenue-market-cap?stock=000333&years=8
```

## 说明

- 前端页面使用 Next.js 实现
- Flask 只负责 API，不再返回 HTML 页面
- 如果 AKShare 字段名变化，后端会打印 `columns` 方便排查
