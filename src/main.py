"""CLI entry: python -m src.main"""

from __future__ import annotations

import argparse
import sys

from src.agent import run
from src.amazon import CaptchaTimeout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find the lowest in-stock Amazon price for a swim-usable bone-conduction headset."
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium headless. A visible window is the default so you can complete an Amazon challenge.",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        default=8,
        help="How many unique product pages to open (default: 8).",
    )
    args = parser.parse_args(argv)
    if args.max_products < 1:
        print("--max-products must be at least 1.", file=sys.stderr)
        return 2
    try:
        report = run(headless=args.headless, max_products=args.max_products)
    except CaptchaTimeout as exc:
        print(exc, file=sys.stderr)
        return 2
    print(report["markdown_path"])
    best = report.get("best")
    if best:
        print(f"Best price: {best['price_display']} — {best['title']}")
    else:
        print("No in-stock swim-usable listing with a price.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
