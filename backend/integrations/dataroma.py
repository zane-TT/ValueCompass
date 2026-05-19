from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import httpx


DATAROMA_BASE_URL = "https://www.dataroma.com"
DATAROMA_HOME_URL = f"{DATAROMA_BASE_URL}/m/home.php"


class DataromaHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []
        self.links: list[dict[str, str]] = []
        self._href_stack: list[str | None] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href_stack.append(self._current_href)
        self._current_href = dict(attrs).get("href")
        self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a":
            return
        text = normalize_text(" ".join(self._current_text))
        if text and self._current_href:
            self.links.append({"text": text, "href": absolute_url(self._current_href)})
        self._current_href = self._href_stack.pop() if self._href_stack else None
        self._current_text = []

    def handle_data(self, data: str) -> None:
        text = normalize_text(data)
        if not text:
            return
        self.tokens.append(text)
        if self._current_href is not None:
            self._current_text.append(text)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def absolute_url(href: str) -> str:
    href = href.strip()
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/"):
        return f"{DATAROMA_BASE_URL}{href}"
    return f"{DATAROMA_BASE_URL}/m/{href}"


def fetch_dataroma_html(url: str = DATAROMA_HOME_URL) -> str:
    headers = {
        "User-Agent": "ValueCompass research cache contact=valuecompass@example.com",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def parse_number(value: str) -> float | None:
    clean = value.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        return float(clean)
    except ValueError:
        return None


def is_date_token(value: str) -> bool:
    return value == "Today" or bool(re.fullmatch(r"\d{1,2} [A-Z][a-z]{2}", value))


def is_stock_label(value: str) -> bool:
    return bool(re.match(r"^[A-Z][A-Z0-9.\-]{0,8}(?:\s+-\s+.+)?$", value))


def link_code_from_href(href: str) -> str | None:
    match = re.search(r"[?&]m=([^&]+)", href)
    return match.group(1) if match else None


def split_manager_name(value: str) -> tuple[str, str | None]:
    if " - " not in value:
        return value.strip(), None
    manager, firm = value.split(" - ", 1)
    return manager.strip(), firm.strip()


def find_token_index(tokens: list[str], marker: str) -> int | None:
    for index, token in enumerate(tokens):
        if token == marker or token.startswith(marker):
            return index
    return None


def section_tokens(tokens: list[str], start_marker: str, stop_markers: list[str]) -> list[str]:
    start_index = find_token_index(tokens, start_marker)
    if start_index is None:
        return []
    end_index = len(tokens)
    for marker in stop_markers:
        marker_index = find_token_index(tokens[start_index + 1 :], marker)
        if marker_index is not None:
            end_index = min(end_index, start_index + 1 + marker_index)
    return tokens[start_index + 1 : end_index]


def build_superinvestor_updates(links: list[dict[str, str]], limit: int = 24) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for link in links:
        if "holdings.php?m=" not in link["href"]:
            continue
        match = re.match(r"(.+?) Updated (.+)$", link["text"])
        if not match:
            continue
        name_text, updated_at = match.groups()
        manager, firm = split_manager_name(name_text)
        updates.append(
            {
                "code": link_code_from_href(link["href"]),
                "manager": manager,
                "firm": firm,
                "updatedAt": updated_at,
                "url": link["href"],
            }
        )
    return updates[:limit]


def build_stock_list(tokens: list[str], start_marker: str, stop_markers: list[str], limit: int = 10) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw = section_tokens(tokens, start_marker, stop_markers)
    index = 0
    while index < len(raw) - 1:
        ticker = raw[index].strip()
        name = raw[index + 1].strip()
        if (
            ticker
            and len(ticker) <= 10
            and re.fullmatch(r"[A-Z][A-Z0-9.\-]*", ticker)
            and name.startswith("-")
        ):
            items.append({"ticker": ticker, "name": name.lstrip("-").strip()})
            if len(items) >= limit:
                break
            index += 2
            continue
        index += 1
    return items


def build_big_bets(tokens: list[str], stop_markers: list[str], limit: int = 10) -> list[dict[str, Any]]:
    raw = section_tokens(tokens, 'Top "big bets"', stop_markers)
    items: list[dict[str, Any]] = []
    index = 0
    while index < len(raw) - 3:
        ticker = raw[index].strip()
        name = raw[index + 1].strip()
        if re.fullmatch(r"[A-Z][A-Z0-9.\-]*", ticker) and name.startswith("-"):
            max_percent = parse_number(raw[index + 2])
            ownership_count = parse_number(raw[index + 3])
            if max_percent is not None and ownership_count is not None:
                items.append(
                    {
                        "ticker": ticker,
                        "name": name.lstrip("-").strip(),
                        "maxPortfolioPercent": max_percent,
                        "ownershipCount": int(ownership_count),
                    }
                )
                if len(items) >= limit:
                    break
                index += 4
                continue
        index += 1
    return items


def build_insider_buys(tokens: list[str], limit: int = 18) -> list[dict[str, Any]]:
    raw = section_tokens(tokens, "Latest significant* insider buys", ["* Real time", "Success in investing"])
    items: list[dict[str, Any]] = []
    index = 0
    while index < len(raw) - 3:
        if not is_date_token(raw[index]):
            index += 1
            continue
        filed_at = raw[index]
        stock = raw[index + 1]
        if not is_stock_label(stock):
            index += 1
            continue

        ticker = stock
        company = ""
        value_index = index + 2
        if " - " in stock:
            ticker, company = stock.split(" - ", 1)
        elif value_index < len(raw) and raw[value_index].startswith("-"):
            company = raw[value_index].lstrip("-").strip()
            value_index += 1

        total_value = parse_number(raw[value_index]) if value_index < len(raw) else None
        price = parse_number(raw[value_index + 1]) if value_index + 1 < len(raw) else None
        if total_value is None or price is None:
            index += 1
            continue

        items.append(
            {
                "filedAt": filed_at,
                "ticker": ticker.strip(),
                "company": company,
                "totalValueUsd": total_value,
                "priceUsd": price,
            }
        )
        if len(items) >= limit:
            break
        index = value_index + 2
    return items


def extract_quarter_label(tokens: list[str]) -> str | None:
    for token in tokens:
        match = re.search(r"\(\s*(Q\d\s+\d{4})\s*\)", token)
        if match:
            return match.group(1)
    return None


def extract_tracked_count(tokens: list[str]) -> int | None:
    for token in tokens:
        match = re.search(r"Currently tracking portfolios of (\d+) Superinvestors", token)
        if match:
            return int(match.group(1))
    for index, token in enumerate(tokens[:-1]):
        if token == "Currently tracking portfolios of":
            match = re.search(r"(\d+)", tokens[index + 1])
            if match:
                return int(match.group(1))
    return None


def build_dataroma_overview_payload() -> dict[str, Any]:
    html = fetch_dataroma_html()
    parser = DataromaHtmlParser()
    parser.feed(html)
    tokens = parser.tokens
    stop_markers = [
        "Top 10 stocks by %",
        'Top "big bets"',
        "Top 10 buys last qtr",
        "Top 10 buys last qtr by %",
        "Top 10 buys last 2 qtrs",
        "Top 10 buys last 2 qtrs by %",
        "5% or greater holdings near 52 week low",
        "Superinvestor stocks with most insider buys",
        "Latest significant* insider buys",
    ]

    return {
        "source": "DATAROMA",
        "sourceUrl": DATAROMA_HOME_URL,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "trackedSuperinvestors": extract_tracked_count(tokens),
            "latestQuarter": extract_quarter_label(tokens),
        },
        "superinvestorUpdates": build_superinvestor_updates(parser.links),
        "topOwnedStocks": build_stock_list(tokens, "Top 10 most owned stocks", stop_markers),
        "topOwnedByPercent": build_stock_list(tokens, "Top 10 stocks by %", stop_markers),
        "topBigBets": build_big_bets(tokens, stop_markers),
        "topBuysLastQuarter": build_stock_list(tokens, "Top 10 buys last qtr", stop_markers),
        "topBuysLastQuarterByPercent": build_stock_list(tokens, "Top 10 buys last qtr by %", stop_markers),
        "topBuysLastTwoQuarters": build_stock_list(tokens, "Top 10 buys last 2 qtrs", stop_markers),
        "insiderBuys": build_insider_buys(tokens),
        "notice": (
            "DATAROMA data is shown as a low-frequency research summary with links back to the source. "
            "13F filings can lag actual portfolio activity and this page is not investment advice."
        ),
    }
