"""Selector checks against local HTML. These tests do not open Amazon."""

from __future__ import annotations

import unittest

from playwright.sync_api import sync_playwright

from src.amazon import _EXTRACT_PRODUCT, _EXTRACT_SEARCH, _details_from_raw, hits_from_rows

PRODUCT_HTML = """
<html><body>
  <span id="productTitle">OpenSwim bone conduction headphones</span>
  <div id="corePriceDisplay_desktop_feature_div">
    <span class="a-price"><span class="a-offscreen">$79.95</span></span>
  </div>
  <div id="availability">In Stock</div>
  <div id="desktop_buybox">Ships from Amazon. In Stock.</div>
  <div id="feature-bullets"><ul>
    <li>IP68 waterproof for swimming</li>
  </ul></div>
  <div id="productDescription">Usable underwater.</div>
  <span id="acrPopover" title="4.6 out of 5 stars"></span>
  <span id="acrCustomerReviewText">1,234 ratings</span>
  <button id="add-to-cart-button">Add to Cart</button>
</body></html>
"""

CART_PRICE_HTML = """
<html><body>
  <span id="productTitle">Hidden price headset</span>
  <div id="availability">See price in cart</div>
  <div id="desktop_buybox">See price in cart</div>
  <div id="corePriceDisplay_desktop_feature_div">
    <span class="a-price"><span class="a-offscreen">$19.99</span></span>
  </div>
</body></html>
"""

LDJSON_HTML = """
<html><body>
  <span id="productTitle">Listed in JSON</span>
  <div id="availability"><span>Only 2 left in stock - order soon.</span></div>
  <script type="application/ld+json">
    {"@type": "Product", "offers": {"@type": "Offer", "price": "64.50", "priceCurrency": "USD"}}
  </script>
</body></html>
"""

SEARCH_HTML = """
<html><body>
  <div class="s-main-slot">
    <div data-asin=""><h2><span>Empty</span></h2></div>
    <div data-asin="BSPONSORED" data-component-type="sp-sponsored-result">
      <h2><span>Sponsored component</span></h2>
    </div>
    <div data-asin="BLABEL">
      <span class="puis-sponsored-label-text">Sponsored</span>
      <h2><span>Sponsored label</span></h2>
    </div>
    <div data-asin="BREAL">
      <h2><span>OpenSwim bone conduction</span></h2>
    </div>
  </div>
</body></html>
"""


class ExtractTests(unittest.TestCase):
    def test_local_product_and_search_markup(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.set_content(PRODUCT_HTML)
                details = _details_from_raw(
                    "B000TEST01",
                    "https://www.amazon.com/dp/B000TEST01",
                    page.evaluate(_EXTRACT_PRODUCT),
                )
                page.set_content(CART_PRICE_HTML)
                hidden = _details_from_raw(
                    "B000CART01",
                    "https://www.amazon.com/dp/B000CART01",
                    page.evaluate(_EXTRACT_PRODUCT),
                )
                page.set_content(LDJSON_HTML)
                listed = _details_from_raw(
                    "B000JSON01",
                    "https://www.amazon.com/dp/B000JSON01",
                    page.evaluate(_EXTRACT_PRODUCT),
                )
                page.set_content(SEARCH_HTML)
                hits = hits_from_rows(page.evaluate(_EXTRACT_SEARCH))
            finally:
                browser.close()

        self.assertEqual(details.price, 79.95)
        self.assertTrue(details.in_stock)
        self.assertEqual(details.rating, 4.6)
        self.assertEqual(details.review_count, 1234)
        self.assertIn("IP68", details.text)
        self.assertFalse(details.see_price_in_cart)

        self.assertTrue(hidden.see_price_in_cart)
        self.assertIsNone(hidden.price)
        self.assertFalse(hidden.in_stock)

        self.assertEqual(listed.price, 64.50)
        self.assertTrue(listed.in_stock)
        self.assertEqual([hit.asin for hit in hits], ["BREAL"])


if __name__ == "__main__":
    unittest.main()
