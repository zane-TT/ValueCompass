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


def parse_int(value: str) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def parse_money(value: str) -> float | None:
    return parse_number(value)


def normalize_manager_code(value: str) -> str:
    code = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", code):
        raise ValueError("Invalid DATAROMA manager code")
    return code


def manager_url(manager_code: str, page: str = "holdings") -> str:
    normalized_code = normalize_manager_code(manager_code)
    if page == "activity":
        return f"{DATAROMA_BASE_URL}/m/m_activity.php?m={normalized_code}&typ=a"
    return f"{DATAROMA_BASE_URL}/m/holdings.php?m={normalized_code}"


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


def parse_manager_heading(value: str) -> dict[str, str | None]:
    manager, firm = split_manager_name(value)
    return {"manager": manager, "firm": firm}


def parse_recent_activity(value: str) -> dict[str, Any]:
    if value == "Buy":
        return {"type": "buy", "label": "Buy", "percent": None}
    match = re.match(r"(Add|Reduce|Sell)\s+(-?[\d,.]+)%", value)
    if not match:
        return {"type": "hold", "label": "", "percent": None}
    action, percent = match.groups()
    return {"type": action.lower(), "label": value, "percent": parse_number(percent)}


def is_activity_token(value: str) -> bool:
    return value == "Buy" or bool(re.match(r"(Add|Reduce|Sell)\s+(-?[\d,.]+)%", value))


def build_holdings(tokens: list[str]) -> list[dict[str, Any]]:
    holdings: list[dict[str, Any]] = []
    index = find_token_index(tokens, "≡")
    while index is not None and index + 8 < len(tokens):
        if tokens[index] != "≡":
            break
        ticker = tokens[index + 1].strip()
        company = tokens[index + 2].lstrip("-").strip()
        portfolio_percent = parse_number(tokens[index + 3])
        if not ticker or portfolio_percent is None or not company:
            next_index = find_token_index(tokens[index + 1 :], "≡")
            if next_index is None:
                break
            index = index + 1 + next_index
            continue

        value_index = index + 4
        recent_activity = parse_recent_activity("")
        if value_index < len(tokens) and is_activity_token(tokens[value_index]):
            recent_activity = parse_recent_activity(tokens[value_index])
            value_index += 1

        if value_index + 6 >= len(tokens):
            break

        holding = {
            "ticker": ticker,
            "name": company,
            "portfolioPercent": portfolio_percent,
            "recentActivity": recent_activity,
            "shares": parse_int(tokens[value_index]),
            "reportedPrice": parse_money(tokens[value_index + 1]),
            "value": parse_money(tokens[value_index + 2]),
            "currentPrice": parse_money(tokens[value_index + 3]),
            "reportedPriceChangePercent": parse_number(tokens[value_index + 4]),
            "week52Low": parse_money(tokens[value_index + 5]),
            "week52High": parse_money(tokens[value_index + 6]),
        }
        holdings.append(holding)

        next_index = find_token_index(tokens[value_index + 7 :], "≡")
        if next_index is None:
            break
        index = value_index + 7 + next_index
    return holdings


def build_activity_by_quarter(tokens: list[str], max_quarters: int = 4) -> list[dict[str, Any]]:
    quarters: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    index = 0
    while index < len(tokens):
        if re.fullmatch(r"Q[1-4]", tokens[index]) and index + 1 < len(tokens) and re.fullmatch(r"\d{4}", tokens[index + 1]):
            if current is not None:
                quarters.append(current)
                if len(quarters) >= max_quarters:
                    break
            current = {"quarter": f"{tokens[index]} {tokens[index + 1]}", "items": []}
            index += 2
            continue

        if current is not None and tokens[index] == "≡" and index + 5 < len(tokens):
            ticker = tokens[index + 1].strip()
            name = tokens[index + 2].lstrip("-").strip()
            activity = tokens[index + 3]
            if is_activity_token(activity):
                current["items"].append(
                    {
                        "ticker": ticker,
                        "name": name,
                        "activity": parse_recent_activity(activity),
                        "shareChange": parse_int(tokens[index + 4]),
                        "portfolioImpactPercent": parse_number(tokens[index + 5]),
                    }
                )
                index += 6
                continue
        index += 1

    if current is not None and len(quarters) < max_quarters:
        quarters.append(current)
    return quarters


def build_activity_label(action_type: str, percent: float | None) -> str:
    labels = {
        "buy": "Buy",
        "add": "Add",
        "reduce": "Reduce",
        "sell": "Sell",
    }
    label = labels.get(action_type)
    if not label:
        return ""
    if percent is None:
        return label
    return f"{label} {percent:.2f}%"


def apply_portfolio_activity_impacts(holdings: list[dict[str, Any]], activity_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    impacts_by_ticker = {
        item["ticker"]: item
        for item in activity_items
        if item.get("ticker") and isinstance(item.get("portfolioImpactPercent"), (int, float))
    }
    for holding in holdings:
        activity = holding.get("recentActivity")
        if not isinstance(activity, dict) or activity.get("type") == "hold":
            continue

        impact_item = impacts_by_ticker.get(holding.get("ticker"))
        if impact_item is None:
            continue

        portfolio_impact = impact_item["portfolioImpactPercent"]
        activity["positionChangePercent"] = activity.get("percent")
        activity["portfolioImpactPercent"] = portfolio_impact
        activity["percent"] = portfolio_impact
        activity["label"] = build_activity_label(str(activity.get("type")), portfolio_impact)
    return holdings


def summarize_activity(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"buy": 0, "add": 0, "reduce": 0, "sell": 0}
    for item in items:
        action_type = item.get("activity", {}).get("type")
        if action_type in summary:
            summary[action_type] += 1
    return summary


def build_concentration(holdings: list[dict[str, Any]]) -> dict[str, float | int | None]:
    weights = [item["portfolioPercent"] for item in holdings if isinstance(item.get("portfolioPercent"), (int, float))]
    return {
        "top1Percent": round(sum(weights[:1]), 2) if weights else None,
        "top5Percent": round(sum(weights[:5]), 2) if weights else None,
        "top10Percent": round(sum(weights[:10]), 2) if weights else None,
        "holdingCount": len(holdings),
    }


def build_dataroma_manager_payload(manager_code: str) -> dict[str, Any]:
    code = normalize_manager_code(manager_code)
    holdings_url = manager_url(code)
    activity_url = manager_url(code, "activity")

    holdings_parser = DataromaHtmlParser()
    holdings_parser.feed(fetch_dataroma_html(holdings_url))
    holdings_tokens = holdings_parser.tokens

    activity_parser = DataromaHtmlParser()
    activity_parser.feed(fetch_dataroma_html(activity_url))
    activity_tokens = activity_parser.tokens

    heading_index = 15 if len(holdings_tokens) > 15 else None
    heading = parse_manager_heading(holdings_tokens[heading_index]) if heading_index is not None else {"manager": code, "firm": None}
    holdings = build_holdings(holdings_tokens)
    activity_by_quarter = build_activity_by_quarter(activity_tokens)
    latest_activity = activity_by_quarter[0] if activity_by_quarter else {"quarter": None, "items": []}
    holdings = apply_portfolio_activity_impacts(holdings, latest_activity["items"])

    portfolio_date_index = find_token_index(holdings_tokens, "Portfolio date:")
    stock_count_index = find_token_index(holdings_tokens, "No. of stocks:")
    portfolio_value_index = find_token_index(holdings_tokens, "Portfolio value:")
    period_index = find_token_index(holdings_tokens, "Period:")

    return {
        "source": "DATAROMA",
        "managerCode": code,
        "manager": heading["manager"],
        "firm": heading["firm"],
        "sourceUrl": holdings_url,
        "activityUrl": activity_url,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "period": holdings_tokens[period_index + 1] if period_index is not None and period_index + 1 < len(holdings_tokens) else None,
        "portfolioDate": holdings_tokens[portfolio_date_index + 1] if portfolio_date_index is not None and portfolio_date_index + 1 < len(holdings_tokens) else None,
        "reportedStockCount": parse_int(holdings_tokens[stock_count_index + 1]) if stock_count_index is not None and stock_count_index + 1 < len(holdings_tokens) else None,
        "portfolioValue": parse_money(holdings_tokens[portfolio_value_index + 1]) if portfolio_value_index is not None and portfolio_value_index + 1 < len(holdings_tokens) else None,
        "concentration": build_concentration(holdings),
        "holdings": holdings,
        "topHoldings": holdings[:10],
        "activityByQuarter": activity_by_quarter,
        "latestActivitySummary": summarize_activity(latest_activity["items"]),
        "latestActivityItems": latest_activity["items"],
        "notice": (
            "This is a low-frequency summary of DATAROMA public pages with source links. "
            "13F data is delayed and does not represent current trading activity."
        ),
    }


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
