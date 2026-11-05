"""Visible Playwright session for Amazon search and product pages."""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import quote_plus

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

SEARCH_QUERIES = (
    "bone conduction headset swimming",
    "bone conductor headphones swimming waterproof",
)

_CAPTCHA_MARKERS = (
    "enter the characters you see",
    "sorry, we just need to make sure you're not a robot",
    "type the characters you see in this image",
)
_PRICE = re.compile(r"(?:USD|US\$|\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)")
_RATING = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s+out of 5")
_REVIEWS = re.compile(r"([0-9][0-9,]*)")
_UNAVAILABLE = re.compile(
    r"currently unavailable|temporarily out of stock|out of stock",
    re.IGNORECASE,
)
_IN_STOCK = re.compile(r"\bin stock\b", re.IGNORECASE)
_SEE_CART = re.compile(r"see price in cart", re.IGNORECASE)

_EXTRACT_SEARCH = """
() => {
  const isSponsored = (card) => {
    if (card.getAttribute('data-component-type') === 'sp-sponsored-result') return true;
    const label = card.querySelector(
      '.puis-sponsored-label-text, .s-sponsored-label-text, .s-label-popover-default, .puis-label-popover-default'
    );
    if (label && /sponsored/i.test(label.textContent || '')) return true;
    const spans = card.querySelectorAll('span');
    for (const span of spans) {
      if ((span.textContent || '').trim() === 'Sponsored') return true;
    }
    return false;
  };
  const rows = [];
  for (const card of document.querySelectorAll('div[data-asin]')) {
    const asin = (card.getAttribute('data-asin') || '').trim();
    if (!asin) continue;
    const titleNode = card.querySelector('h2 span');
    rows.push({
      asin,
      title: titleNode ? titleNode.textContent.trim() : '',
      sponsored: isSponsored(card),
    });
  }
  return rows;
}
"""

_EXTRACT_PRODUCT = """
() => {
  const textOf = (selector) => {
    const node = document.querySelector(selector);
    return node ? node.innerText.trim() : '';
  };
  const priceFrom = (rootSelector) => {
    const root = document.querySelector(rootSelector);
    if (!root) return '';
    const offscreen = root.querySelector('.a-price .a-offscreen');
    if (offscreen && offscreen.textContent.trim()) return offscreen.textContent.trim();
    const whole = root.querySelector('.a-price-whole');
    if (!whole) return '';
    const dollars = (whole.textContent || '').replace(/[^0-9]/g, '');
    const fractionNode = root.querySelector('.a-price-fraction');
    const cents = fractionNode ? (fractionNode.textContent || '').replace(/[^0-9]/g, '') : '00';
    if (!dollars) return '';
    return '$' + dollars + '.' + (cents || '00');
  };
  const popover = document.querySelector('#acrPopover');
  const bullets = Array.from(document.querySelectorAll('#feature-bullets li'))
    .map((li) => li.innerText.trim())
    .filter(Boolean);
  const ldjson = Array.from(
    document.querySelectorAll('script[type="application/ld+json"]')
  ).map((node) => node.textContent || '');
  return {
    title: textOf('#productTitle'),
    bullets,
    description: textOf('#productDescription'),
    details: textOf('#prodDetails').slice(0, 4000),
    availability: textOf('#availability'),
    buybox: textOf('#desktop_buybox, #buybox').slice(0, 4000),
    ratingLabel: popover ? (popover.getAttribute('title') || '') : '',
    reviewText: textOf('#acrCustomerReviewText'),
    priceCandidates: [
      priceFrom('#corePriceDisplay_desktop_feature_div'),
      priceFrom('#corePrice_feature_div'),
      priceFrom('#apex_desktop'),
    ].filter(Boolean),
    ldjson,
    hasAddToCart: Boolean(document.querySelector('#add-to-cart-button')),
  };
}
"""


class CaptchaTimeout(RuntimeError):
    """Amazon left a challenge up longer than the wait."""


@dataclass(frozen=True)
class SearchHit:
    asin: str
    title: str


@dataclass(frozen=True)
class ProductDetails:
    asin: str
    url: str
    title: str
    price: float | None
    currency: str
    in_stock: bool
    see_price_in_cart: bool
    rating: float | None
    review_count: int | None
    text: str


class AmazonBrowser:
    """One Chromium window. Headed unless `headless` is set."""

    def __init__(self, *, headless: bool = False) -> None:
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._navigated = False

    def __enter__(self) -> AmazonBrowser:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        context = self._browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        self._page = context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def search(self, query: str) -> list[SearchHit]:
        url = f"https://www.amazon.com/s?k={quote_plus(query)}"
        page = self._goto(url)
        self._wait_for_results(page)
        return hits_from_rows(page.evaluate(_EXTRACT_SEARCH))

    def open_product(self, asin: str) -> ProductDetails:
        url = f"https://www.amazon.com/dp/{asin}"
        page = self._goto(url)
        page.wait_for_selector("#productTitle", timeout=30000)
        raw = page.evaluate(_EXTRACT_PRODUCT)
        return _details_from_raw(asin, url, raw)

    def _goto(self, url: str) -> Page:
        if self._page is None:
            raise RuntimeError("browser is not open")
        if self._navigated:
            time.sleep(random.uniform(1.5, 3.0))
        self._page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self._navigated = True
        self._clear_challenge(self._page)
        return self._page

    def _wait_for_results(self, page: Page) -> None:
        try:
            page.wait_for_selector("div.s-main-slot div[data-asin]", timeout=20000)
        except Exception:
            # An empty or blocked page still returns no hits to the caller.
            return

    def _clear_challenge(self, page: Page) -> None:
        if _captcha_visible(page):
            self._wait_for_captcha(page)
            return
        self._click_continue_shopping(page)
        if _captcha_visible(page):
            self._wait_for_captcha(page)

    def _wait_for_captcha(self, page: Page) -> None:
        if self.headless:
            print(
                "Amazon is showing a challenge. Rerun without --headless and complete it in the browser window."
            )
        else:
            print("Amazon is showing a challenge. Complete it in the browser window.")
        deadline = time.time() + 300
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            if not _captcha_visible(page):
                return
        raise CaptchaTimeout(
            "Amazon challenge was still open after 5 minutes. Complete it and run again."
        )

    def _click_continue_shopping(self, page: Page) -> None:
        if page.query_selector("#productTitle, div.s-main-slot"):
            return
        try:
            button = page.locator(
                "button:has-text('Continue shopping'), "
                "a:has-text('Continue shopping'), "
                "input[type='submit'][value*='Continue shopping']"
            )
            if button.count() == 0 or not button.first.is_visible():
                return
            button.first.click(timeout=3000)
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            return


def hits_from_rows(raw_rows: list[dict]) -> list[SearchHit]:
    """Keep the first organic row for each ASIN and drop sponsored-only rows."""
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for row in raw_rows:
        asin = str(row.get("asin") or "").strip()
        if not asin or asin in seen or row.get("sponsored"):
            continue
        seen.add(asin)
        hits.append(SearchHit(asin=asin, title=str(row.get("title") or "").strip()))
    return hits


def parse_price(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 2)
    if not isinstance(value, str):
        return None
    match = _PRICE.search(value.replace("\xa0", " "))
    if not match:
        bare = re.fullmatch(r"\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*", value)
        if not bare:
            return None
        number = bare.group(1)
    else:
        number = match.group(1)
    try:
        return round(float(number.replace(",", "")), 2)
    except ValueError:
        return None


def _details_from_raw(asin: str, url: str, raw: dict) -> ProductDetails:
    title = str(raw.get("title") or "").strip()
    bullets = [str(item).strip() for item in raw.get("bullets") or [] if str(item).strip()]
    description = str(raw.get("description") or "").strip()
    details = str(raw.get("details") or "").strip()
    availability = str(raw.get("availability") or "").strip()
    buybox = str(raw.get("buybox") or "").strip()
    offer_zone = "\n".join(part for part in (availability, buybox) if part)
    see_price_in_cart = bool(_SEE_CART.search(offer_zone))
    unavailable = bool(_UNAVAILABLE.search(offer_zone))
    in_stock = bool(_IN_STOCK.search(availability)) or (
        bool(raw.get("hasAddToCart")) and not unavailable
    )
    if unavailable or see_price_in_cart:
        in_stock = False

    price = None if see_price_in_cart else _first_price(raw)
    text = "\n".join(part for part in [title, *bullets, description, details] if part)
    return ProductDetails(
        asin=asin,
        url=url,
        title=title or asin,
        price=price,
        currency="USD",
        in_stock=in_stock,
        see_price_in_cart=see_price_in_cart,
        rating=_parse_rating(str(raw.get("ratingLabel") or "")),
        review_count=_parse_review_count(str(raw.get("reviewText") or "")),
        text=text,
    )


def _first_price(raw: dict) -> float | None:
    for candidate in raw.get("priceCandidates") or []:
        parsed = parse_price(candidate)
        if parsed is not None:
            return parsed
    for blob in raw.get("ldjson") or []:
        parsed = _price_from_ldjson(str(blob))
        if parsed is not None:
            return parsed
    return None


def _price_from_ldjson(blob: str) -> float | None:
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return _product_offer_price(data)


def _product_offer_price(node: object) -> float | None:
    nodes = node if isinstance(node, list) else [node]
    for item in nodes:
        if not isinstance(item, dict):
            continue
        kind = item.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Product" in kinds:
            price = _offer_price(item.get("offers"))
            if price is not None:
                return price
        if "@graph" in item:
            price = _product_offer_price(item.get("@graph"))
            if price is not None:
                return price
    return None


def _offer_price(offers: object) -> float | None:
    if isinstance(offers, list):
        for offer in offers:
            price = _offer_price(offer)
            if price is not None:
                return price
        return None
    if not isinstance(offers, dict):
        return None
    if "lowPrice" in offers:
        price = parse_price(offers.get("lowPrice"))
        if price is not None:
            return price
    if "price" in offers:
        return parse_price(offers.get("price"))
    return None


def _parse_rating(label: str) -> float | None:
    match = _RATING.search(label)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _parse_review_count(text: str) -> int | None:
    match = _REVIEWS.search(text)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _captcha_visible(page: Page) -> bool:
    if "validatecaptcha" in page.url.lower():
        return True
    try:
        html = page.content().lower()
    except Exception:
        return False
    return any(marker in html for marker in _CAPTCHA_MARKERS)
