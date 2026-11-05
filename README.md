# Swim-usable bone-conduction price agent

Local CLI that opens Amazon in a visible Chromium window, reads bone-conduction headset listings, and reports the lowest current in-stock price among products that are usable while swimming.

Marketplace is amazon.com (USD). **Best price** means the lowest current in-stock price among listings that pass the swim check. Star rating and review count are shown next to each price so a cheap, low-rated listing is easy to see.

The browser is a normal Playwright Chromium window. There is no stealth plugin, proxy list, or captcha solver. If Amazon shows a challenge, the run pauses for up to five minutes so you can complete it in that window.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Copy `.env.example` to `.env` only if you want the optional model check. The swim rules run either way.

## Run

```bash
python -m src.main
```

Headless mode is optional. A challenge page cannot be completed there:

```bash
python -m src.main --headless
```

`--max-products` defaults to 8. The agent searches the first results page of two queries, then opens that many product pages:

- `bone conduction headset swimming`
- `bone conductor headphones swimming waterproof`

It waits 1.5–3 seconds between page loads. Sponsored-only cards and rows with no ASIN are skipped.

Reports are written to `results/report.json` and `results/report.md`.

## Swim check

A listing counts only if it is bone conduction and swim-usable.

- **Pass:** the page states a swim-grade rating (IP68, IP69, IPX8, IPX9, or 5 ATM or higher) and does not say the product is not for swimming.
- **Borderline:** the page mentions swimming, underwater use, or open water, but not a swim-grade rating. If `OPENAI_API_KEY` is set, one OpenAI-compatible chat call answers yes or no (`OPENAI_BASE_URL`, `OPENAI_MODEL`). An explicit “not for swimming” still rejects the listing if the model disagrees. With no API key, a borderline listing is not ranked.
- **Reject:** the page says not to use it while swimming, or the only water claim is sweat, rain, or workout resistance (IPX4, IPX5, IP55, IP54).

Out-of-stock listings, listings with no parseable price, and “see price in cart” listings are left out of the ranking even when they pass the swim check.

## Tests

Unit tests use pasted page text. They do not open Amazon.

```bash
python -m unittest tests.test_judge
```

A live run needs a display, network access, and sometimes a person at the Amazon challenge page.
