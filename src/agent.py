"""Search Amazon, judge swim use, and rank the lowest in-stock price."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.amazon import SEARCH_QUERIES, AmazonBrowser, CaptchaTimeout, ProductDetails
from src.judge import Judgment, judge_text
from src.report import write_report


def run(*, headless: bool = False, max_products: int = 8, output_dir: Path | None = None) -> dict:
    load_dotenv()
    allow_model = bool(os.environ.get("OPENAI_API_KEY"))
    if allow_model:
        print("Borderline listings will get one model check.")
    else:
        print("No OPENAI_API_KEY set. Borderline listings will not be ranked.")

    destination = output_dir or Path("results")
    opened: list[tuple[ProductDetails, Judgment | None]] = []
    with AmazonBrowser(headless=headless) as browser:
        hits = _collect_hits(browser, max_products)
        for hit in hits:
            print(f"Opening {hit.asin}: {hit.title}")
            try:
                details = browser.open_product(hit.asin)
            except CaptchaTimeout:
                raise
            except Exception as exc:
                opened.append((_failed_product(hit.asin, str(exc)), None))
                continue
            opened.append((details, judge_text(details.text, allow_model=allow_model)))

    payload = _payload(opened)
    written = write_report(payload, destination)
    payload.update(written)
    return payload


def _collect_hits(browser: AmazonBrowser, max_products: int):
    chosen = []
    seen: set[str] = set()
    for query in SEARCH_QUERIES:
        if len(chosen) >= max_products:
            break
        print(f"Searching: {query}")
        for hit in browser.search(query):
            if hit.asin in seen:
                continue
            seen.add(hit.asin)
            chosen.append(hit)
            if len(chosen) >= max_products:
                break
    return chosen


def _failed_product(asin: str, error: str) -> ProductDetails:
    return ProductDetails(
        asin=asin,
        url=f"https://www.amazon.com/dp/{asin}",
        title=asin,
        price=None,
        currency="USD",
        in_stock=False,
        see_price_in_cart=False,
        rating=None,
        review_count=None,
        text=error,
    )


def _payload(opened: list[tuple[ProductDetails, Judgment | None]]) -> dict:
    qualifiers = []
    rejected = []
    for details, judgment in opened:
        record = _record(details)
        if judgment is None:
            record["reason"] = f"could not open product page: {details.text}"
            record["swim_usable"] = False
            rejected.append(record)
            continue
        record["swim_usable"] = judgment.swim_usable
        record["reason"] = judgment.reason
        record["evidence"] = judgment.evidence
        if judgment.swim_usable and _rankable(details):
            qualifiers.append(record)
        else:
            if judgment.swim_usable:
                record["reason"] = _skip_reason(details)
            rejected.append(record)

    qualifiers.sort(key=lambda item: (item["price"], item["asin"]))
    best = qualifiers[0] if qualifiers else None
    return {
        "marketplace": "amazon.com",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries": list(SEARCH_QUERIES),
        "best": best,
        "qualifiers": qualifiers,
        "rejected": rejected,
    }


def _rankable(details: ProductDetails) -> bool:
    return details.price is not None and details.in_stock and not details.see_price_in_cart


def _skip_reason(details: ProductDetails) -> str:
    if details.see_price_in_cart:
        return "price hidden in cart"
    if details.price is None:
        return "no parseable price"
    if not details.in_stock:
        return "out of stock"
    return "not ranked"


def _record(details: ProductDetails) -> dict:
    return {
        "asin": details.asin,
        "title": details.title,
        "url": details.url,
        "price": details.price,
        "price_display": _price_display(details.price),
        "currency": details.currency,
        "in_stock": details.in_stock,
        "rating": details.rating,
        "review_count": details.review_count,
        "evidence": "",
        "reason": "",
        "swim_usable": False,
    }


def _price_display(price: float | None) -> str:
    if price is None:
        return "n/a"
    return f"${price:,.2f}"
