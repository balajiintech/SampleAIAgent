"""Decide whether a product page describes a swim-usable bone-conduction headset."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass

BONE = re.compile(r"\bbone[\s-]?conduction\b|\bbone[\s-]?conductor\b", re.IGNORECASE)

NOT_FOR_SWIM = re.compile(
    r"\b("
    r"not (?:suitable |designed |intended |recommended |meant )?for swimming"
    r"|do not use (?:while |for |when )?swimming"
    r"|don'?t use (?:while |for |when )?swimming"
    r"|not to be used (?:while |for |when )?swimming"
    r"|cannot be used (?:while |for |when )?swimming"
    r"|can'?t be used (?:while |for |when )?swimming"
    r"|avoid swimming"
    r"|no swimming"
    r")",
    re.IGNORECASE,
)

PASS_RATING = re.compile(
    r"\bIP\s?68\b|\bIP\s?69\b|\bIPX\s?8\b|\bIPX\s?9\b",
    re.IGNORECASE,
)
ATM_RATING = re.compile(r"\b(\d+(?:\.\d+)?)\s*ATM\b", re.IGNORECASE)
SWIM_WORDS = re.compile(
    r"\bswimming\b|\bswims\b|\bswimmer(?:'s)?\b|\bswim\b|\bswim[- ]proof\b|"
    r"\bunderwater\b|open[- ]water",
    re.IGNORECASE,
)
SWEAT = re.compile(
    r"\b(IPX4|IPX5|IP55|IP54)\b|\b(sweat|sweatproof|rain|workout|splash[- ]?proof)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Judgment:
    swim_usable: bool
    status: str
    reason: str
    evidence: str


def judge_text(text: str, *, allow_model: bool = False) -> Judgment:
    """Apply the swim rules. A model call happens only for a borderline page."""
    ruled = _apply_rules(text)
    if ruled.status != "borderline":
        return ruled
    if not allow_model or not os.environ.get("OPENAI_API_KEY"):
        return Judgment(
            swim_usable=False,
            status="reject",
            reason="swimming is mentioned but the waterproof rating is unclear",
            evidence=ruled.evidence,
        )
    try:
        confirmed = openai_compatible_yes_no(text)
    except Exception as exc:
        return Judgment(
            swim_usable=False,
            status="reject",
            reason=f"borderline and model check failed: {exc}",
            evidence=ruled.evidence,
        )
    if confirmed:
        return Judgment(
            swim_usable=True,
            status="pass",
            reason="model confirmed swim use on an unclear rating",
            evidence=ruled.evidence,
        )
    return Judgment(
        swim_usable=False,
        status="reject",
        reason="model judged the listing not usable while swimming",
        evidence=ruled.evidence,
    )


def openai_compatible_yes_no(text: str) -> bool:
    """Ask an OpenAI-compatible chat endpoint for YES or NO."""
    api_key = os.environ["OPENAI_API_KEY"]
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You decide if a bone-conduction headset is usable while swimming. "
                    "Swimming means the product is meant to be worn in the water, not merely "
                    "sweatproof. Reply with exactly YES or NO."
                ),
            },
            {"role": "user", "content": text[:6000]},
        ],
    }
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode())
    answer = body["choices"][0]["message"]["content"].strip().upper()
    if answer.startswith("YES"):
        return True
    if answer.startswith("NO"):
        return False
    raise RuntimeError(f"unexpected model reply: {answer[:80]}")


def _apply_rules(text: str) -> Judgment:
    if not BONE.search(text):
        return Judgment(False, "reject", "not bone conduction", "")

    banned = NOT_FOR_SWIM.search(text)
    if banned:
        return Judgment(
            False,
            "reject",
            "page says not for swimming",
            _quote(text, NOT_FOR_SWIM),
        )

    if _has_swim_grade_rating(text):
        return Judgment(
            True,
            "pass",
            "swim-grade waterproof rating",
            _quote(text, PASS_RATING) or _quote(text, ATM_RATING),
        )

    if SWIM_WORDS.search(text):
        return Judgment(
            False,
            "borderline",
            "swimming is mentioned but the waterproof rating is unclear",
            _quote(text, SWIM_WORDS),
        )

    if SWEAT.search(text):
        return Judgment(
            False,
            "reject",
            "sweat, rain, or workout resistance only",
            _quote(text, SWEAT),
        )

    return Judgment(False, "reject", "no swimming claim or swim-grade rating", "")


def _has_swim_grade_rating(text: str) -> bool:
    if PASS_RATING.search(text):
        return True
    for match in ATM_RATING.finditer(text):
        try:
            if float(match.group(1)) >= 5:
                return True
        except ValueError:
            continue
    return False


def _quote(text: str, pattern: re.Pattern[str]) -> str:
    for sentence in _SENTENCE_SPLIT.split(text):
        cleaned = sentence.strip()
        if cleaned and pattern.search(cleaned):
            return cleaned[:400]
    match = pattern.search(text)
    if not match:
        return ""
    start = max(0, match.start() - 80)
    end = min(len(text), match.end() + 80)
    return " ".join(text[start:end].split())
