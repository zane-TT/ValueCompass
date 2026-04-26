from __future__ import annotations


def lookup_company_industry(ticker: str) -> dict:
    """
    获取公司所属行业。
    """
    industry_map = {
        "600519": "白酒",
        "300999": "工业制造",
        "000858": "白酒",
        "601318": "保险",
        "000333": "家电",
        "600036": "银行",
        "601888": "旅游",
        "600276": "医药",
        "002594": "食品饮料",
        "601012": "光伏",
    }
    
    industry = industry_map.get(ticker, "未知行业")
    
    return {
        "ticker": ticker,
        "industry": industry,
        "source": "ValueCompass Industry Map"
    }


def lookup_industry_peers(ticker: str) -> dict:
    """
    获取某只股票的同行列表。
    """
    peers_map = {
        "600519": ["000858", "000568", "600779", "600809"],  # 白酒行业
        "300999": ["300750", "300454", "300671", "300346"],  # 工业制造
        "000858": ["600519", "000568", "600779", "600809"],  # 白酒行业
        "601318": ["601628", "601336", "601601", "600016"],  # 保险行业
        "000333": ["000651", "600690", "002035", "000921"],  # 家电行业
        "600036": ["601398", "601288", "601988", "601166"],  # 银行行业
    }
    
    peers = peers_map.get(ticker, [])
    industry = lookup_company_industry(ticker).get("industry", "未知行业")
    
    return {
        "ticker": ticker,
        "industry": industry,
        "peers": peers,
        "peer_count": len(peers),
        "source": "ValueCompass Peer Map"
    }


def compare_peer_snapshot(ticker: str) -> dict:
    """
    获取公司的一页式财务和估值快照。
    """
    snapshot_data = {
        "600519": {
            "name": "贵州茅台",
            "industry": "白酒",
            "market_cap": "2.3万亿",
            "pe": 28.5,
            "pb": 11.2,
            "roe": 32.5,
            "revenue_growth": 15.2,
            "net_profit_growth": 18.7,
            "dividend_yield": 1.2,
            "debt_to_equity": 0.15,
            "cash_flow": "优秀"
        },
        "300999": {
            "name": "金龙鱼",
            "industry": "食品饮料",
            "market_cap": "3000亿",
            "pe": 22.3,
            "pb": 3.1,
            "roe": 12.8,
            "revenue_growth": 8.5,
            "net_profit_growth": 12.3,
            "dividend_yield": 0.8,
            "debt_to_equity": 0.45,
            "cash_flow": "良好"
        },
        "000858": {
            "name": "五粮液",
            "industry": "白酒",
            "market_cap": "8000亿",
            "pe": 20.5,
            "pb": 5.8,
            "roe": 25.3,
            "revenue_growth": 12.8,
            "net_profit_growth": 15.2,
            "dividend_yield": 1.5,
            "debt_to_equity": 0.20,
            "cash_flow": "优秀"
        }
    }
    
    data = snapshot_data.get(ticker, {
        "name": f"股票 {ticker}",
        "industry": "未知行业",
        "market_cap": "未知",
        "pe": "未知",
        "pb": "未知",
        "roe": "未知",
        "revenue_growth": "未知",
        "net_profit_growth": "未知",
        "dividend_yield": "未知",
        "debt_to_equity": "未知",
        "cash_flow": "未知"
    })
    
    return {
        "ticker": ticker,
        "company_name": data["name"],
        "industry": data["industry"],
        "market_cap": data["market_cap"],
        "valuation": {
            "pe": data["pe"],
            "pb": data["pb"]
        },
        "growth": {
            "revenue_growth": data["revenue_growth"],
            "net_profit_growth": data["net_profit_growth"]
        },
        "financial_health": {
            "roe": data["roe"],
            "debt_to_equity": data["debt_to_equity"],
            "cash_flow": data["cash_flow"]
        },
        "dividend_yield": data["dividend_yield"],
        "source": "ValueCompass Financial Snapshot"
    }