# Flask 后端说明

这个目录只保留财报可视化所需的 Flask API。

当前接口：

1. `GET /api/balance`
2. `GET /api/revenue-market-cap`

## 安装依赖

```bash
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

## 启动命令

```bash
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe app.py
```

默认运行地址：

```text
http://127.0.0.1:5001
```

## 接口示例

### 资产负债结构图

```text
http://127.0.0.1:5001/api/balance?stock=600519
```

### 业绩和市值趋势对比图

```text
http://127.0.0.1:5001/api/revenue-market-cap?stock=000333&years=8
```

## 调试说明

如果 AKShare 字段名变化，代码会打印：

- `Balance columns`
- `Profit columns`
- `Valuation columns`
