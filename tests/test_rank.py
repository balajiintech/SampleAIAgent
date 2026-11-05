"""Price parsing and ranking. These tests do not open Amazon."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.agent import _payload
from src.amazon import ProductDetails, hits_from_rows, parse_price
from src.judge import Judgment
from src.report import write_report


def _product(**overrides: object) -> ProductDetails:
    values: dict[str, object] = {
        "asin": "B000000001",
        "url": "https://www.amazon.com/dp/B000000001",
        "title": "Swim headset",
        "price": 80.0,
        "currency": "USD",
        "in_stock": True,
        "see_price_in_cart": False,
        "rating": 4.5,
        "review_count": 20,
        "text": "Bone conduction IP68 swimming",
    }
    values.update(overrides)
    return ProductDetails(**values)  # type: ignore[arg-type]


class ParsePriceTests(unittest.TestCase):
    def test_dollar_and_bare_numbers(self) -> None:
        self.assertEqual(parse_price("$1,299.00"), 1299.00)
        self.assertEqual(parse_price(64.5), 64.5)
        self.assertEqual(parse_price("64.50"), 64.50)
        self.assertIsNone(parse_price("see price in cart"))

    def test_sponsored_only_rows_are_dropped(self) -> None:
        hits = hits_from_rows(
            [
                {"asin": "", "title": "blank", "sponsored": False},
                {"asin": "BSPONSORED", "title": "Ad", "sponsored": True},
                {"asin": "BBOTH", "title": "Ad first", "sponsored": True},
                {"asin": "BBOTH", "title": "Organic", "sponsored": False},
                {"asin": "BREAL", "title": "Real", "sponsored": False},
            ]
        )
        self.assertEqual([hit.asin for hit in hits], ["BBOTH", "BREAL"])
        self.assertEqual(hits[0].title, "Organic")


class RankTests(unittest.TestCase):
    def test_lowest_in_stock_price_wins(self) -> None:
        passed = Judgment(True, "pass", "swim-grade waterproof rating", "IP68")
        cheap = _product(asin="BCHEAP", price=49.0, title="Cheap swim")
        pricey = _product(asin="BPRICE", price=120.0, title="Pricey swim", url="https://www.amazon.com/dp/BPRICE")
        hidden = _product(
            asin="BHIDDEN",
            price=10.0,
            see_price_in_cart=True,
            in_stock=False,
            title="Hidden price",
        )
        sold_out = _product(asin="BSOLDOUT", price=30.0, in_stock=False, title="Sold out")
        sweat = _product(asin="BSWEAT", price=15.0, title="Sweat only")
        failed = _product(asin="BFAIL", title="BFAIL", price=None, in_stock=False, text="timeout")
        sweat_judgment = Judgment(False, "reject", "sweat, rain, or workout resistance only", "IPX5")

        payload = _payload(
            [
                (pricey, passed),
                (cheap, passed),
                (hidden, passed),
                (sold_out, passed),
                (sweat, sweat_judgment),
                (failed, None),
            ]
        )

        self.assertEqual(payload["best"]["asin"], "BCHEAP")
        self.assertEqual(payload["best"]["price_display"], "$49.00")
        self.assertEqual([item["asin"] for item in payload["qualifiers"]], ["BCHEAP", "BPRICE"])
        reasons = {item["asin"]: item["reason"] for item in payload["rejected"]}
        self.assertEqual(reasons["BHIDDEN"], "price hidden in cart")
        self.assertEqual(reasons["BSOLDOUT"], "out of stock")
        self.assertEqual(reasons["BSWEAT"], "sweat, rain, or workout resistance only")
        self.assertIn("timeout", reasons["BFAIL"])

    def test_report_files(self) -> None:
        payload = {
            "best": {
                "asin": "BCHEAP",
                "title": "Cheap swim",
                "url": "https://www.amazon.com/dp/BCHEAP",
                "price_display": "$49.00",
                "rating": 4.5,
                "review_count": 20,
                "evidence": "IP68",
            },
            "qualifiers": [
                {
                    "asin": "BCHEAP",
                    "title": "Cheap swim",
                    "url": "https://www.amazon.com/dp/BCHEAP",
                    "price_display": "$49.00",
                    "rating": 4.5,
                    "review_count": 20,
                    "evidence": "IP68",
                }
            ],
            "rejected": [{"asin": "BSWEAT", "title": "Sweat only", "reason": "sweat, rain, or workout resistance only"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            written = write_report(payload, Path(directory))
            self.assertIn("Cheap swim", Path(written["markdown_path"]).read_text(encoding="utf-8"))
            self.assertIn("BSWEAT", Path(written["json_path"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
