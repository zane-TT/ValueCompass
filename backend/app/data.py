from __future__ import annotations

from copy import deepcopy


SAMPLE_COMPANIES = {
    "600519": {
        "ticker": "600519",
        "name": "Kweichow Moutai Sample",
        "industry": "consumer_staples",
        "description": "High-end spirits producer with strong brand power and high cash conversion.",
        "financials": {
            "latest_year": "2025",
            "annual": [
                {
                    "year": "2022",
                    "revenue": 124100,
                    "net_profit": 62700,
                    "operating_cash_flow": 66700,
                    "accounts_receivable": 190,
                    "inventory": 38800,
                    "fixed_assets": 20100,
                    "construction_in_progress": 1800,
                    "goodwill": 0,
                    "total_assets": 254000,
                    "total_liabilities": 70900,
                    "shareholders_equity": 183100,
                    "dividend_payout_ratio": 0.52,
                    "capex": 2400,
                    "roe": 0.342,
                    "gross_margin": 0.916,
                    "net_margin": 0.505,
                    "eps": 49.93,
                    "book_value_per_share": 145.80,
                },
                {
                    "year": "2023",
                    "revenue": 147700,
                    "net_profit": 74700,
                    "operating_cash_flow": 79200,
                    "accounts_receivable": 240,
                    "inventory": 43500,
                    "fixed_assets": 21800,
                    "construction_in_progress": 2200,
                    "goodwill": 0,
                    "total_assets": 289000,
                    "total_liabilities": 78400,
                    "shareholders_equity": 210600,
                    "dividend_payout_ratio": 0.54,
                    "capex": 2900,
                    "roe": 0.355,
                    "gross_margin": 0.918,
                    "net_margin": 0.506,
                    "eps": 59.47,
                    "book_value_per_share": 167.70,
                },
                {
                    "year": "2024",
                    "revenue": 171300,
                    "net_profit": 84200,
                    "operating_cash_flow": 90700,
                    "accounts_receivable": 280,
                    "inventory": 47600,
                    "fixed_assets": 23600,
                    "construction_in_progress": 2500,
                    "goodwill": 0,
                    "total_assets": 323500,
                    "total_liabilities": 84700,
                    "shareholders_equity": 238800,
                    "dividend_payout_ratio": 0.56,
                    "capex": 3100,
                    "roe": 0.353,
                    "gross_margin": 0.919,
                    "net_margin": 0.492,
                    "eps": 67.05,
                    "book_value_per_share": 190.20,
                },
                {
                    "year": "2025",
                    "revenue": 188600,
                    "net_profit": 91900,
                    "operating_cash_flow": 97000,
                    "accounts_receivable": 320,
                    "inventory": 51500,
                    "fixed_assets": 24800,
                    "construction_in_progress": 2600,
                    "goodwill": 0,
                    "total_assets": 352900,
                    "total_liabilities": 90100,
                    "shareholders_equity": 262800,
                    "dividend_payout_ratio": 0.58,
                    "capex": 3400,
                    "roe": 0.350,
                    "gross_margin": 0.918,
                    "net_margin": 0.487,
                    "eps": 73.17,
                    "book_value_per_share": 209.40,
                },
            ],
            "quarterly": [
                {"period": "2025Q2", "revenue_yoy": 0.151, "net_profit_yoy": 0.133, "ocf_yoy": 0.101},
                {"period": "2025Q3", "revenue_yoy": 0.126, "net_profit_yoy": 0.117, "ocf_yoy": 0.098},
            ],
            "market": {
                "price": 1725.00,
                "pe_ttm": 23.6,
                "pb": 8.2,
                "dividend_yield": 0.026,
                "market_cap": 2167000,
            },
        },
    },
    "300999": {
        "ticker": "300999",
        "name": "Growth Hardware Sample",
        "industry": "industrials",
        "description": "Capital-intensive manufacturer with growth ambition but weaker cash conversion.",
        "financials": {
            "latest_year": "2025",
            "annual": [
                {
                    "year": "2022",
                    "revenue": 12800,
                    "net_profit": 860,
                    "operating_cash_flow": 420,
                    "accounts_receivable": 2300,
                    "inventory": 1950,
                    "fixed_assets": 4600,
                    "construction_in_progress": 1200,
                    "goodwill": 680,
                    "total_assets": 12600,
                    "total_liabilities": 4700,
                    "shareholders_equity": 7900,
                    "dividend_payout_ratio": 0.10,
                    "capex": 1080,
                    "roe": 0.109,
                    "gross_margin": 0.238,
                    "net_margin": 0.067,
                    "eps": 1.72,
                    "book_value_per_share": 15.80,
                },
                {
                    "year": "2023",
                    "revenue": 15100,
                    "net_profit": 1010,
                    "operating_cash_flow": 310,
                    "accounts_receivable": 3120,
                    "inventory": 2740,
                    "fixed_assets": 5450,
                    "construction_in_progress": 1800,
                    "goodwill": 900,
                    "total_assets": 15550,
                    "total_liabilities": 6250,
                    "shareholders_equity": 9300,
                    "dividend_payout_ratio": 0.08,
                    "capex": 1530,
                    "roe": 0.109,
                    "gross_margin": 0.231,
                    "net_margin": 0.067,
                    "eps": 2.02,
                    "book_value_per_share": 18.60,
                },
                {
                    "year": "2024",
                    "revenue": 18300,
                    "net_profit": 1190,
                    "operating_cash_flow": 180,
                    "accounts_receivable": 4380,
                    "inventory": 3510,
                    "fixed_assets": 6780,
                    "construction_in_progress": 2590,
                    "goodwill": 900,
                    "total_assets": 19750,
                    "total_liabilities": 8580,
                    "shareholders_equity": 11170,
                    "dividend_payout_ratio": 0.05,
                    "capex": 1970,
                    "roe": 0.107,
                    "gross_margin": 0.219,
                    "net_margin": 0.065,
                    "eps": 2.38,
                    "book_value_per_share": 22.34,
                },
                {
                    "year": "2025",
                    "revenue": 21100,
                    "net_profit": 1240,
                    "operating_cash_flow": 90,
                    "accounts_receivable": 5720,
                    "inventory": 4380,
                    "fixed_assets": 7850,
                    "construction_in_progress": 3220,
                    "goodwill": 900,
                    "total_assets": 23380,
                    "total_liabilities": 10640,
                    "shareholders_equity": 12740,
                    "dividend_payout_ratio": 0.03,
                    "capex": 2340,
                    "roe": 0.097,
                    "gross_margin": 0.206,
                    "net_margin": 0.059,
                    "eps": 2.48,
                    "book_value_per_share": 25.48,
                },
            ],
            "quarterly": [
                {"period": "2025Q2", "revenue_yoy": 0.201, "net_profit_yoy": 0.081, "ocf_yoy": -0.220},
                {"period": "2025Q3", "revenue_yoy": 0.176, "net_profit_yoy": 0.041, "ocf_yoy": -0.340},
            ],
            "market": {
                "price": 43.80,
                "pe_ttm": 17.7,
                "pb": 1.72,
                "dividend_yield": 0.002,
                "market_cap": 21900,
            },
        },
    },
}


def get_company_data(ticker: str) -> dict | None:
    company = SAMPLE_COMPANIES.get(ticker)
    if not company:
        return None
    return deepcopy(company)


INDUSTRY_LABELS = {
    "consumer_staples": {
        "industry_level_1": "Consumer",
        "industry_level_2": "Food & Beverage",
        "industry_level_3": "Premium Liquor",
    },
    "industrials": {
        "industry_level_1": "Industrials",
        "industry_level_2": "Capital Goods",
        "industry_level_3": "Hardware Manufacturing",
    },
}


INDUSTRY_PEERS = {
    "consumer_staples": [
        {"ticker": "000858", "company_name": "Wuliangye Sample", "reason": "Comparable premium liquor operator."},
        {"ticker": "000568", "company_name": "Luzhou Laojiao Sample", "reason": "Comparable high-margin liquor peer."},
        {"ticker": "603369", "company_name": "Jing Brand Sample", "reason": "Useful channel and pricing comparison."},
    ],
    "industrials": [
        {"ticker": "300124", "company_name": "Robotics Sample", "reason": "Comparable capital equipment peer."},
        {"ticker": "002353", "company_name": "Jerry Sample", "reason": "Comparable manufacturing and order-cycle peer."},
        {"ticker": "688777", "company_name": "Zhongkong Sample", "reason": "Useful asset-heavy industrial comparison."},
    ],
}


def get_industry_labels(industry_key: str) -> dict | None:
    labels = INDUSTRY_LABELS.get(industry_key)
    if not labels:
        return None
    return deepcopy(labels)


def get_industry_peers(industry_key: str) -> list[dict]:
    return deepcopy(INDUSTRY_PEERS.get(industry_key, []))
