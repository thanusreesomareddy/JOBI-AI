"""Aggregate weak topics across completed practice sessions."""

from collections import Counter


def _normalize_topic(text: str) -> str:
    return " ".join(text.strip().lower().split())[:80]


def compute_focus_areas(sessions: list[dict], *, limit: int = 5) -> list[dict]:
    """Return top recurring improvement topics from session history."""
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}

    for session in sessions:
        if session.get("status") != "completed":
            continue

        summary = session.get("session_summary") or {}
        for area in summary.get("areas_to_improve") or []:
            if not area or not str(area).strip():
                continue
            key = _normalize_topic(str(area))
            counts[key] += 2
            labels.setdefault(key, str(area).strip())

        for turn in session.get("turns") or []:
            evaluation = turn.get("evaluation") or {}
            for item in evaluation.get("improvements") or []:
                if not item or not str(item).strip():
                    continue
                key = _normalize_topic(str(item))
                counts[key] += 1
                labels.setdefault(key, str(item).strip())

    ranked = counts.most_common(limit)
    return [
        {"topic": labels.get(key, key), "mentions": count}
        for key, count in ranked
        if count > 0
    ]
