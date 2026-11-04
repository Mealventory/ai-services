"""Normalize the USDA FoodKeeper workbook JSON export for the runtime matcher.

Usage: python Scripts/import_foodkeeper.py path/to/foodkeeper-source.json

FoodKeeper's public dump is a JSON representation of its workbook. This keeps
the checked-in runtime data small and gives shelf-life ranges consistent units.
For range estimates we use the upper endpoint, matching the consumer-facing
FoodKeeper guidance window (for example, fresh fatty fish is 1–2 days).
"""
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "foodkeeper.json"
SOURCE_URL = "https://www.fsis.usda.gov/shared/data/EN/foodkeeper.json"
UNIT_TO_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def row_object(cells):
    """Convert FoodKeeper's [{column: value}, ...] rows into a dictionary."""
    return {key: value for cell in cells for key, value in cell.items()}


def as_days(value, metric):
    if value is None or metric is None:
        return None
    unit = str(metric).strip().casefold().rstrip("s")
    factor = UNIT_TO_DAYS.get(unit)
    if not factor:
        return None
    try:
        return round(float(value) * factor)
    except (TypeError, ValueError):
        return None


def aliases_for(product):
    keyword_parts = [part.strip() for part in re.split(r"[,;]", product.get("Keywords") or "") if part.strip()]
    aliases = [product.get("Name"), product.get("Name_subtitle"), *keyword_parts]
    # Do not turn compound entries such as "salmon salad" into an alias for
    # plain salmon; the latter has its own FoodKeeper group.
    compound_words = {word.casefold() for part in keyword_parts if len(part.split()) > 1
                      for word in re.findall(r"[\w'-]+", part)}
    product_name = (product.get("Name") or "").casefold().strip()
    primary_forms = {product_name}
    if product_name.endswith("ies"):
        primary_forms.add(product_name[:-3] + "y")
    elif product_name.endswith("s"):
        primary_forms.add(product_name[:-1])
    # FoodKeeper sometimes separates the preparation from the food name
    # (for example Name="Beef", Name_subtitle="ground"). Add that usable
    # phrase to the alias list so it can match "ground beef".
    subtitle = (product.get("Name_subtitle") or "").strip()
    if len(product_name.split()) == 1 and len(subtitle.split()) == 1:
        aliases.append(f"{subtitle} {product.get('Name')}")
    # "Chicken parts" entries include fresh breast halves in the subtitle.
    # Give those records the common user-facing alias while retaining USDA's
    # original product grouping and duration.
    if product_name == "chicken parts" and "breast" in subtitle.casefold():
        aliases.extend(("chicken breast", "chicken breasts"))
    name_words = set(re.findall(r"[\w'-]+", product_name))
    subtitle_words = set(re.findall(r"[\w'-]+", subtitle.casefold()))
    def is_ambiguous_component(alias):
        if not alias or len(alias.split()) != 1:
            return False
        word = alias.casefold()
        if word in primary_forms:
            return False
        # Drop keyword fragments such as "apple" from apple juice/applesauce,
        # and "chicken" from chicken salad. Keep genuine singular aliases such
        # as "apple" for the canonical product "Apples".
        return (word in compound_words or word in name_words or word in subtitle_words
                or (len(product_name.split()) == 1
                    and product_name.startswith(word) and len(word) < len(product_name)))
    aliases = [alias for alias in aliases if not is_ambiguous_component(alias)]
    return list(dict.fromkeys(value.strip() for value in aliases
                              if value and value.strip() and value.strip().casefold() != "all"))


def normalize(source):
    sheets = {sheet["name"]: sheet["data"] for sheet in source["sheets"]}
    categories = {int(row["ID"]): row for row in
                  (row_object(cells) for cells in sheets["Category"])}
    entries_by_key = {}
    for cells in sheets["Product"]:
        product = row_object(cells)
        category = categories.get(int(product["Category_ID"]), {})
        primary = category.get("Category_Name") or "Food"
        subcategory = category.get("Subcategory_Name")
        group = "Fish" if primary == "Seafood" else primary
        label = f"{group} - {subcategory}" if subcategory else group
        zones = {}
        for zone, prefix in (("pantry", "Pantry"), ("fridge", "Refrigerate"), ("freezer", "Freeze")):
            # DOP means "date of purchase" and is the right countdown for a
            # newly purchased item. Fall back to the general storage field.
            start = f"DOP_{prefix}"
            minimum = product.get(f"{start}_Min")
            maximum = product.get(f"{start}_Max")
            metric = product.get(f"{start}_Metric")
            if minimum is None and maximum is None:
                minimum = product.get(f"{prefix}_Min")
                maximum = product.get(f"{prefix}_Max")
                metric = product.get(f"{prefix}_Metric")
            days_min = as_days(minimum, metric)
            days_max = as_days(maximum, metric)
            # A single endpoint is still useful when FoodKeeper publishes a
            # point value. Text-only guidance remains intentionally unestimated.
            if days_min is not None or days_max is not None:
                zones[zone] = {"min_days": days_min if days_min is not None else days_max,
                               "max_days": days_max if days_max is not None else days_min}
        if not zones:
            continue
        name = product.get("Name") or label
        key = (name, label, json.dumps(zones, sort_keys=True))
        entry = entries_by_key.setdefault(key, {"name": name,
            "matched_food": label, "aliases": [], "zones": zones})
        entry["aliases"] = list(dict.fromkeys(entry["aliases"] + aliases_for(product)))
    entries = list(entries_by_key.values())
    return {
        "source_name": "USDA FoodKeeper (FSIS)",
        "source_url": SOURCE_URL,
        "source_data_version": 128,
        "source_data_date": "2018-09-07",
        "license": "CC0-1.0",
        "entries": entries,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Pass the USDA FoodKeeper workbook JSON export as the only argument.")
    source = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(normalize(source), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(f"Wrote {len(normalize(source)['entries'])} FoodKeeper entries to {OUTPUT}")
