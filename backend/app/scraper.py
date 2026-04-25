from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup


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


SINA_BULLETIN_URL = "https://money.finance.sina.com.cn/corp/go.php/vCB_Bulletin/stockid/{stock_id}/page_type/{page_type}.phtml"

PAGE_TYPE_MAPPING = {
    "ndbg": "年度报告",
    "qndbg": "年度报告", 
    "bjdbg": "半年报",
    "sndbg": "三季度报",
    "yjdbg": "一季度报",
}


def _build_url(stock_id: str, page_type: str = "ndbg") -> str:
    return SINA_BULLETIN_URL.format(stock_id=stock_id, page_type=page_type)


def _parse_bulletin_list(html_content: str, stock_id: str) -> list[BulletinItem]:
    bulletins = []
    soup = BeautifulSoup(html_content, "html.parser")
    
    table = soup.find("table", {"id": " bulletins_tb"})
    if not table:
        table = soup.find("table")
    
    if table:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 2:
                title_cell = cells[0]
                date_cell = cells[1]
                
                link = title_cell.find("a")
                if link:
                    title = link.get_text(strip=True)
                    url = link.get("href", "")
                    publish_date = date_cell.get_text(strip=True)
                    
                    bulletin_type = PAGE_TYPE_MAPPING.get(page_type, "其他")
                    
                    if title and url:
                        bulletins.append(BulletinItem(
                            title=title,
                            publish_date=publish_date,
                            url=url,
                            bulletin_type=bulletin_type
                        ))
    
    return bulletins


async def fetch_bulletin_list(stock_id: str, page_type: str = "ndbg") -> FinancialReport:
    url = _build_url(stock_id, page_type)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        html_content = response.text
    
    bulletins = _parse_bulletin_list(html_content, stock_id)
    
    company_name = _extract_company_name_from_html(html_content)
    
    return FinancialReport(
        ticker=stock_id,
        company_name=company_name,
        bulletins=bulletins,
        fetched_at=datetime.now().isoformat()
    )


def _extract_company_name_from_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        if ">" in title_text:
            parts = title_text.split(">")
            if len(parts) >= 2:
                return parts[1].strip()
    
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    
    return "Unknown"


async def get_annual_reports(stock_id: str) -> FinancialReport:
    return await fetch_bulletin_list(stock_id, "ndbg")


async def get_semiannual_reports(stock_id: str) -> FinancialReport:
    return await fetch_bulletin_list(stock_id, "bjdbg")


async def get_quarterly_reports(stock_id: str, quarter: int = 3) -> FinancialReport:
    page_type_map = {1: "yjd_bg", 3: "sndbg"}
    page_type = page_type_map.get(quarter, "sndbg")
    return await fetch_bulletin_list(stock_id, page_type)


def sync_fetch_bulletin_list(stock_id: str, page_type: str = "ndbg") -> FinancialReport:
    url = _build_url(stock_id, page_type)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    response = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    html_content = response.text
    
    bulletins = _parse_bulletin_list(html_content, stock_id)
    company_name = _extract_company_name_from_html(html_content)
    
    return FinancialReport(
        ticker=stock_id,
        company_name=company_name,
        bulletins=bulletins,
        fetched_at=datetime.now().isoformat()
    )


def sync_get_annual_reports(stock_id: str) -> FinancialReport:
    return sync_fetch_bulletin_list(stock_id, "ndbg")
