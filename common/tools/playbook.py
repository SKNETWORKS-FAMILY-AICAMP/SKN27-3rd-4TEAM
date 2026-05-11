"""Playbook card loader and query helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK_PATH = PROJECT_ROOT / "data" / "playbook_cards.json"


def load_playbook_cards() -> dict[str, Any]:
    """Load playbook card data from the local JSON file."""
    with PLAYBOOK_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def list_playbook_cards(
    *,
    risk_type: str | None = None,
    severity: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Return playbook cards filtered by risk type, severity, or keyword."""
    payload = load_playbook_cards()
    cards = payload.get("cards", [])
    result: list[dict[str, Any]] = []
    for card in cards:
        if risk_type and risk_type not in card.get("risk_types", []):
            continue
        if severity and str(card.get("severity", "")).upper() != severity.upper():
            continue
        if keyword and keyword not in _card_search_text(card):
            continue
        result.append(card)
    return result


def get_playbook_card(card_id: str) -> dict[str, Any] | None:
    """Return one playbook card by card_id."""
    for card in load_playbook_cards().get("cards", []):
        if card.get("card_id") == card_id:
            return card
    return None


def summarize_playbook_cards() -> dict[str, Any]:
    """Summarize playbook card counts for UI navigation."""
    cards = load_playbook_cards().get("cards", [])
    severity_counts: dict[str, int] = {}
    risk_type_counts: dict[str, int] = {}
    for card in cards:
        severity = str(card.get("severity", "UNKNOWN"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        for risk_type in card.get("risk_types", []):
            risk_type_counts[risk_type] = risk_type_counts.get(risk_type, 0) + 1
    return {
        "total_count": len(cards),
        "severity_counts": severity_counts,
        "risk_type_counts": risk_type_counts,
        "card_ids": [card.get("card_id") for card in cards],
    }


def _card_search_text(card: dict[str, Any]) -> str:
    parts = [
        card.get("title"),
        card.get("situation"),
        card.get("user_goal"),
        card.get("source_query"),
        " ".join(card.get("risk_types", [])),
        " ".join(card.get("evidence_tags", [])),
    ]
    return " ".join(str(part or "") for part in parts)


@tool
def load_playbook_cards_tool() -> dict[str, Any]:
    """Load all jeonse fraud response playbook cards."""
    return load_playbook_cards()


@tool
def list_playbook_cards_tool(
    risk_type: str | None = None,
    severity: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """List playbook cards filtered by risk type, severity, or keyword."""
    return list_playbook_cards(risk_type=risk_type, severity=severity, keyword=keyword)


@tool
def get_playbook_card_tool(card_id: str) -> dict[str, Any] | None:
    """Get one playbook card by card_id."""
    return get_playbook_card(card_id)


@tool
def summarize_playbook_cards_tool() -> dict[str, Any]:
    """Summarize playbook card counts for UI navigation."""
    return summarize_playbook_cards()
