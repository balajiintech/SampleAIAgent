"""Write the ranked price report as JSON and Markdown."""

from __future__ import annotations

import json
from pathlib import Path


def write_report(payload: dict, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "best": payload.get("best"),
    }


def _markdown(payload: dict) -> str:
    lines = [
        "# Swim-usable bone-conduction headsets",
        "",
        "Best price means the lowest current in-stock price on amazon.com among listings the swim check accepted.",
        "",
        "## Best price",
        "",
    ]
    best = payload.get("best")
    if best:
        lines.extend(_product_lines(best))
    else:
        lines.append("No in-stock swim-usable listing with a visible price.")
    lines.extend(["", "## Other swim-usable listings", ""])
    others = payload.get("qualifiers") or []
    others = [item for item in others if not best or item.get("asin") != best.get("asin")]
    if others:
        for item in others:
            lines.extend(_product_lines(item))
            lines.append("")
    else:
        lines.append("None.")
        lines.append("")
    lines.extend(["## Not ranked", ""])
    rejected = payload.get("rejected") or []
    if rejected:
        for item in rejected:
            title = item.get("title") or item.get("asin")
            lines.append(
                f"- {item.get('asin')} — {title} — {item.get('reason')}"
            )
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def _product_lines(item: dict) -> list[str]:
    rating = item.get("rating")
    reviews = item.get("review_count")
    if rating is None:
        rating_text = "not shown"
    elif reviews is None:
        rating_text = str(rating)
    else:
        rating_text = f"{rating} ({reviews} ratings)"
    evidence = item.get("evidence") or ""
    lines = [
        f"- {item.get('title')}",
        f"- Price: {item.get('price_display')}",
        f"- Rating: {rating_text}",
        f"- ASIN: {item.get('asin')}",
        f"- URL: {item.get('url')}",
    ]
    if evidence:
        lines.append(f"- Why: {evidence}")
    return lines
