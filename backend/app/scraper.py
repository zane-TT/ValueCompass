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


@dataclass
class YearlyFinancialData:
    year: str
    revenue: float | None
    net_profit: float | None
    total_assets: float | None
    pe_ratio: float | None
    pb_ratio: float | None


@dataclass
class FinancialHistoryResult:
    ticker: str
    company_name: str
    yearly_data: list[YearlyFinancialData]
    fetched_at: str


async def get_financial_history(stock_id: str, start_year: str = "2010", end_year: str = "2025") -> FinancialHistoryResult:
    company_name = _get_stock_name(stock_id)
    yearly_data = []
    
    try:
        df = ak.stock_zh_a_annual_report(symbol=stock_id, start_year=start_year, end_year=end_year)
        
        for _, row in df.iterrows():
            year = str(row.get('年份', row.get('年度', '')))
            
            revenue = None
            if '营业总收入' in row.index:
                revenue = row.get('营业总收入')
            elif '营业收入' in row.index:
                revenue = row.get('营业收入')
            
            net_profit = None
            if '净利润' in row.index:
                net_profit = row.get('净利润')
            
            total_assets = None
            if '资产总计' in row.index:
                total_assets = row.get('资产总计')
            
            yearly_data.append(YearlyFinancialData(
                year=year,
                revenue=float(revenue) if revenue is not None and revenue != '' else None,
                net_profit=float(net_profit) if net_profit is not None and net_profit != '' else None,
                total_assets=float(total_assets) if total_assets is not None and total_assets != '' else None,
                pe_ratio=None,
                pb_ratio=None
            ))
        
        yearly_data.sort(key=lambda x: x.year, reverse=True)
        
    except Exception as e:
        pass
    
    try:
        indicator_df = ak.stock_financial_indicator(symbol=stock_id, start_year=start_year, end_year=end_year)
        
        pe_dict = {}
        pb_dict = {}
        
        for _, row in indicator_df.iterrows():
            year = str(row.get('年份', ''))
            
            if '市盈率TTM' in row.index and row.get('市盈率TTM') not in [None, '', '-']:
                try:
                    pe_val = float(row.get('市盈率TTM', 0))
                    if pe_val > 0:
                        pe_dict[year] = pe_val
                except (ValueError, TypeError):
                    pass
            
            if '市净率' in row.index and row.get('市净率') not in [None, '', '-']:
                try:
                    pb_val = float(row.get('市净率', 0))
                    if pb_val > 0:
                        pb_dict[year] = pb_val
                except (ValueError, TypeError):
                    pass
        
        for data in yearly_data:
            if data.year in pe_dict:
                data.pe_ratio = pe_dict[data.year]
            if data.year in pb_dict:
                data.pb_ratio = pb_dict[data.year]
                
    except Exception as e:
        pass
    
    return FinancialHistoryResult(
        ticker=stock_id,
        company_name=company_name,
        yearly_data=yearly_data,
        fetched_at=datetime.now().isoformat()
    )


def sync_get_financial_history(stock_id: str, start_year: str = "2010", end_year: str = "2025") -> FinancialHistoryResult:
    import asyncio
    return asyncio.run(get_financial_history(stock_id, start_year, end_year))