from __future__ import annotations

import sys
from io import BytesIO

import akshare as ak
import akshare.stock_feature.stock_disclosure_cninfo as disclosure_cninfo
import pandas as pd
import requests

try:
    from pypdf import PdfReader
except ImportError:
    bundled_python_packages = r"C:\Users\1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages"
    if bundled_python_packages not in sys.path:
        sys.path.append(bundled_python_packages)
    from pypdf import PdfReader

try:
    from ..core.cache import load_cached_payload, save_cached_payload
    from .akshare_client import temporary_disable_proxy_env
except ImportError:
    from core.cache import load_cached_payload, save_cached_payload
    from integrations.akshare_client import temporary_disable_proxy_env


def load_disclosure_reports(stock: str, category: str, start_date: str = "20200101", end_date: str = "20300101") -> pd.DataFrame:
    print(f"[INFO] Fetching disclosure reports, stock={stock}, category={category}")
    with temporary_disable_proxy_env():
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=stock,
            category=category,
            start_date=start_date,
            end_date=end_date,
        )
    print("[DEBUG] Disclosure report columns:")
    print(df.columns.tolist())
    return df


def fetch_pdf_text_from_cninfo(adjunct_url: str, max_pages: int = 15, max_chars: int = 20000) -> str:
    if not adjunct_url:
        return ""

    pdf_url = adjunct_url
    if not pdf_url.startswith("http"):
        pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}"

    with temporary_disable_proxy_env():
        response = requests.get(pdf_url, timeout=60, proxies={"http": None, "https": None})
        response.raise_for_status()

    reader = PdfReader(BytesIO(response.content))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            parts.append(text)
        if sum(len(item) for item in parts) >= max_chars:
            break

    combined_text = "\n".join(parts).strip()
    return combined_text[:max_chars]


def get_latest_report_text_payload_with_cache(stock: str, category: str, cache_key: str) -> dict:
    cached_payload = load_cached_payload(cache_key, stock)
    if cached_payload is not None:
        return cached_payload

    df = load_disclosure_reports(stock=stock, category=category)
    if df is None or df.empty:
        payload = {"stock": stock, "category": category, "title": "", "date": "", "pdfUrl": "", "textExcerpt": ""}
        save_cached_payload(payload, cache_key, stock)
        return payload

    df = df.copy()
    df["公告时间_dt"] = pd.to_datetime(df["公告时间"], errors="coerce")
    df = df.sort_values("公告时间_dt", ascending=False)
    latest_row = df.iloc[0]

    with temporary_disable_proxy_env():
        ak.stock_zh_a_disclosure_report_cninfo(
            symbol=stock,
            category=category,
            start_date="20200101",
            end_date="20300101",
        )

    with temporary_disable_proxy_env():
        stock_json = disclosure_cninfo.__get_stock_json("沪深京")
        category_dict = disclosure_cninfo.__get_category_dict()
        payload = {
            "pageNum": "1",
            "pageSize": "30",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{stock},{stock_json[stock]}",
            "searchkey": "",
            "secid": "",
            "category": f"{category_dict[category]}",
            "trade": "",
            "seDate": "2020-01-01~2030-01-01",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        raw_response = requests.post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data=payload,
            timeout=60,
            proxies={"http": None, "https": None},
        )
        raw_response.raise_for_status()
        raw_json = raw_response.json()

    selected_item = None
    for item in raw_json.get("announcements", []):
        announcement_title = item.get("announcementTitle", "")
        if announcement_title == latest_row["公告标题"]:
            selected_item = item
            break

    adjunct_url = selected_item.get("adjunctUrl", "") if selected_item else ""
    pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}" if adjunct_url else ""
    text_excerpt = fetch_pdf_text_from_cninfo(adjunct_url) if adjunct_url else ""

    payload = {
        "stock": stock,
        "category": category,
        "title": latest_row["公告标题"],
        "date": str(latest_row["公告时间"]),
        "pdfUrl": pdf_url,
        "textExcerpt": text_excerpt,
    }
    save_cached_payload(payload, cache_key, stock)
    return payload


def get_latest_report_text_payload_v2(stock: str, category: str, cache_key: str) -> dict:
    cached_payload = load_cached_payload(cache_key, stock)
    if cached_payload is not None:
        return cached_payload

    df = load_disclosure_reports(stock=stock, category=category)
    if df is None or df.empty:
        payload = {"stock": stock, "category": category, "title": "", "date": "", "pdfUrl": "", "textExcerpt": ""}
        save_cached_payload(payload, cache_key, stock)
        return payload

    df = df.copy()
    df["公告时间_dt"] = pd.to_datetime(df["公告时间"], errors="coerce")
    df = df.sort_values("公告时间_dt", ascending=False)
    latest_row = df.iloc[0]

    with temporary_disable_proxy_env():
        stock_json = disclosure_cninfo.__get_stock_json("沪深京")
        category_dict = disclosure_cninfo.__get_category_dict()
        query_payload = {
            "pageNum": "1",
            "pageSize": "30",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{stock},{stock_json[stock]}",
            "searchkey": "",
            "secid": "",
            "category": f"{category_dict[category]}",
            "trade": "",
            "seDate": "2020-01-01~2030-01-01",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        raw_response = requests.post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data=query_payload,
            timeout=60,
            proxies={"http": None, "https": None},
        )
        raw_response.raise_for_status()
        raw_json = raw_response.json()

    selected_item = None
    for item in raw_json.get("announcements", []):
        if item.get("announcementTitle", "") == latest_row["公告标题"]:
            selected_item = item
            break

    adjunct_url = selected_item.get("adjunctUrl", "") if selected_item else ""
    pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}" if adjunct_url else ""
    text_excerpt = fetch_pdf_text_from_cninfo(adjunct_url) if adjunct_url else ""

    payload = {
        "stock": stock,
        "category": category,
        "title": latest_row["公告标题"],
        "date": str(latest_row["公告时间"]),
        "pdfUrl": pdf_url,
        "textExcerpt": text_excerpt,
    }
    save_cached_payload(payload, cache_key, stock)
    return payload
