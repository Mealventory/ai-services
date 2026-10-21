"""Offline FoodKeeper shelf-life lookup with conservative fuzzy matching."""
from datetime import date, timedelta
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

from rapidfuzz import fuzz


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "foodkeeper.json"
MATCH_THRESHOLD = 75
_DESCRIPTIVE_WORDS = {"fresh", "raw", "uncooked", "fillet", "filet", "whole"}
_RESTRICTIVE_WORDS = {
    "breaded", "canned", "cooked", "dried", "fermented", "fried",
    "pickled", "processed", "smoked", "stuffed", "sweetened", "unsweetened",
}


def _normalize(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    words = re.findall(r"[\w'-]+", value)
    words = [word for word in words if word not in _DESCRIPTIVE_WORDS]
    return " ".join(sorted(words))


@lru_cache(maxsize=1)
def _dataset():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _candidates():
    return [(_normalize(alias), entry, zone, duration)
            for entry in _dataset()["entries"]
            for alias in entry["aliases"] if _normalize(alias)
            for zone, duration in entry["zones"].items()]


def match_food(name, storage_zone):
    """Return the strongest supported FoodKeeper match, or None.

    Ties are left unmatched: a near-identical score for two food groups should
    not silently assign a shelf life to the wrong item.
    """
    query = _normalize(name)
    if not query or storage_zone not in {"pantry", "fridge", "freezer"}:
        return None

    best_by_entry = {}
    query_words = set(query.split())
    for alias, entry, zone, duration in _candidates():
        if zone != storage_zone:
            continue
        required_words = set(_normalize(entry["name"]).split()) & _RESTRICTIVE_WORDS
        if required_words - query_words:
            continue
        score = fuzz.token_sort_ratio(query, alias)
        key = id(entry)
        current = best_by_entry.get(key)
        if current is None or score > current[0]:
            best_by_entry[key] = (score, entry, duration)
    ranked = [candidate for candidate in best_by_entry.values()
              if candidate[0] > MATCH_THRESHOLD]

    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None

    score, entry, duration = ranked[0]
    return {
        "name": entry["name"],
        "matched_food": entry["matched_food"],
        "storage_zone": storage_zone,
        "shelf_life_days": duration["max_days"],
        "minimum_shelf_life_days": duration["min_days"],
        "match_score": round(score),
        "source_name": _dataset()["source_name"],
        "source_url": _dataset()["source_url"],
    }


def estimate_expiry(name, storage_zone, purchase_date=None):
    """Return a purchase-date-based estimate for one FoodKeeper match."""
    match = match_food(name, storage_zone)
    if match is None:
        return None
    start_date = purchase_date or date.today()
    match["purchase_date"] = start_date.isoformat()
    match["predicted_expiry_date"] = (
        start_date + timedelta(days=match["shelf_life_days"])
    ).isoformat()
    return match
