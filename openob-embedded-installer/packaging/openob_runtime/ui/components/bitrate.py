"""Helpers for bitrate selection UI.

Kept small and UI-focused: provides allowed/locked bitrate lists and parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BitrateChoice:
    value: Optional[int]
    label: str
    selectable: bool


# Plan Free – 48 kbps (selectable)
# Plan Básico – 192 kbps (locked)
# Plan Premium – 384 kbps (locked)
FREE_BITRATES = (16, 24, 32, 48)
BASICO_BITRATES = (64, 96, 128, 192)
PREMIUM_BITRATES = (256, 384)


def build_bitrate_choices() -> list[BitrateChoice]:
    choices: list[BitrateChoice] = []
    for b in FREE_BITRATES:
        choices.append(BitrateChoice(value=b, label=str(b), selectable=True))
    for b in BASICO_BITRATES:
        choices.append(BitrateChoice(value=b, label=f"{b} (Plan Básico)", selectable=False))
    for b in PREMIUM_BITRATES:
        choices.append(BitrateChoice(value=b, label=f"{b} (Plan Premium)", selectable=False))
    return choices


def parse_bitrate_label(label: str) -> Optional[int]:
    """Extract numeric bitrate from a label like '96' or '128 (Plan Premium)'."""
    if not label:
        return None
    # Take the first token, expected to be an int
    first = label.strip().split()[0]
    try:
        return int(first)
    except Exception:
        return None
