from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import akshare as ak


@dataclass
class BulletinItem:
    title: str
    publish_date: str
    url: str
    bulletin_type: str


@dataclass
class FinancialReport:
    ticker: str
    company_name: str
    bulletins: list[BulletinItem]
    fetched_at: str


def _get_stock_name(stock_id: str) -> str:
    try:
        info = ak.stock_individual_info_em(symbol=stock_id)
        name_row = info[info['item'] == '股票简称']
        if not name_row.empty:
            return name_row.iloc[0]['value']
    except Exception:
        pass
    return f"Stock {stock_id}"


async def get_annual_reports(stock_id: str) -> FinancialReport:
    company_name = _get_stock_name(stock_id)
    
    try:
        df = ak.stock_zh_a_annual_report(symbol=stock_id, start_year="2010", end_year="2030")
        
        bulletins = []
        for _, row in df.iterrows():
            if '公布日期' in row.index:
                publish_date = str(row.get('公布日期', ''))
            elif '报告日期' in row.index:
                publish_date = str(row.get('报告日期', ''))
            else:
                publish_date = ''
            
            title = f"{company_name} {row.get('年份', row.get('年度', 'N/A'))}年年度报告"
            
            bulletins.append(BulletinItem(
                title=title,
                publish_date=publish_date,
                url=f"https://www.eastmoney.com",
                bulletin_type="年度报告"
            ))
        
        return FinancialReport(
            ticker=stock_id,
            company_name=company_name,
            bulletins=bulletins,
            fetched_at=datetime.now().isoformat()
        )
    except Exception as e:
        return FinancialReport(
            ticker=stock_id,
            company_name=company_name,
            bulletins=[],
            fetched_at=datetime.now().isoformat()
        )


async def get_quarterly_reports(stock_id: str, quarter: int = 3) -> FinancialReport:
    company_name = _get_stock_name(stock_id)
    
    quarter_map = {1: "1季度报", 2: "2季度报", 3: "3季度报", 4: "4季度报"}
    report_type = quarter_map.get(quarter, "3季度报")
    
    try:
        df = ak.stock_zh_a_quarterly_report(symbol=stock_id, start_year="2010", end_year="2030")
        
        bulletins = []
        for _, row in df.iterrows():
            if '公布日期' in row.index:
                publish_date = str(row.get('公布日期', ''))
            elif '报告日期' in row.index:
                publish_date = str(row.get('报告日期', ''))
            else:
                publish_date = ''
            
            title = f"{company_name} {row.get('年份', row.get('年度', 'N/A'))}年{report_type}"
            
            bulletins.append(BulletinItem(
                title=title,
                publish_date=publish_date,
                url=f"https://www.eastmoney.com",
                bulletin_type=report_type
            ))
        
        return FinancialReport(
            ticker=stock_id,
            company_name=company_name,
            bulletins=bulletins,
            fetched_at=datetime.now().isoformat()
        )
    except Exception as e:
        return FinancialReport(
            ticker=stock_id,
            company_name=company_name,
            bulletins=[],
            fetched_at=datetime.now().isoformat()
        )


async def get_semiannual_reports(stock_id: str) -> FinancialReport:
    company_name = _get_stock_name(stock_id)
    
    try:
        df = ak.stock_zh_a_half_year_report(symbol=stock_id, start_year="2010", end_year="2030")
        
        bulletins = []
        for _, row in df.iterrows():
            if '公布日期' in row.index:
                publish_date = str(row.get('公布日期', ''))
            elif '报告日期' in row.index:
                publish_date = str(row.get('报告日期', ''))
            else:
                publish_date = ''
            
            title = f"{company_name} {row.get('年份', row.get('年度', 'N/A'))}年半年报"
            
            bulletins.append(BulletinItem(
                title=title,
                publish_date=publish_date,
                url=f"https://www.eastmoney.com",
                bulletin_type="半年报"
            ))
        
        return FinancialReport(
            ticker=stock_id,
            company_name=company_name,
            bulletins=bulletins,
            fetched_at=datetime.now().isoformat()
        )
    except Exception as e:
        return FinancialReport(
            ticker=stock_id,
            company_name=company_name,
            bulletins=[],
            fetched_at=datetime.now().isoformat()
        )


def sync_get_annual_reports(stock_id: str) -> FinancialReport:
    import asyncio
    return asyncio.run(get_annual_reports(stock_id))


def sync_get_quarterly_reports(stock_id: str, quarter: int = 3) -> FinancialReport:
    import asyncio
    return asyncio.run(get_quarterly_reports(stock_id, quarter))


def sync_get_semiannual_reports(stock_id: str) -> FinancialReport:
    import asyncio
    return asyncio.run(get_semiannual_reports(stock_id))