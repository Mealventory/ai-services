"""Validate USDA FoodKeeper source data and build the runtime matcher catalogue."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import math
import os
from pathlib import Path
import re
import tempfile

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None
try:
    import xlrd
except ImportError:
    xlrd = None


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "foodkeeper.json"
SOURCE_URL = "https://www.fsis.usda.gov/shared/data/EN/foodkeeper.json"
UNIT_TO_DAYS = {"day": 1, "hour": 1 / 24, "week": 7, "month": 30, "year": 365}

REQUIRED_SHEETS = ("Version", "Category", "Product")
VERSION_FIELDS = ("Data_Version_Number", "Current_Version", "Modified_Date")
CATEGORY_FIELDS = ("ID", "Category_Name", "Subcategory_Name")
PRODUCT_FIELDS = (
    "ID", "Category_ID", "Name", "Name_subtitle", "Keywords",
    "Pantry_Min", "Pantry_Max", "Pantry_Metric", "Pantry_tips",
    "DOP_Pantry_Min", "DOP_Pantry_Max", "DOP_Pantry_Metric", "DOP_Pantry_tips",
    "Pantry_After_Opening_Min", "Pantry_After_Opening_Max", "Pantry_After_Opening_Metric",
    "Refrigerate_Min", "Refrigerate_Max", "Refrigerate_Metric", "Refrigerate_tips",
    "DOP_Refrigerate_Min", "DOP_Refrigerate_Max", "DOP_Refrigerate_Metric", "DOP_Refrigerate_tips",
    "Refrigerate_After_Opening_Min", "Refrigerate_After_Opening_Max", "Refrigerate_After_Opening_Metric",
    "Refrigerate_After_Thawing_Min", "Refrigerate_After_Thawing_Max", "Refrigerate_After_Thawing_Metric",
    "Freeze_Min", "Freeze_Max", "Freeze_Metric", "Freeze_Tips",
    "DOP_Freeze_Min", "DOP_Freeze_Max", "DOP_Freeze_Metric", "DOP_Freeze_Tips",
)
RANGE_GROUPS = (
    ("Pantry", "Pantry_Min", "Pantry_Max", "Pantry_Metric", "Pantry_tips"),
    ("DOP_Pantry", "DOP_Pantry_Min", "DOP_Pantry_Max", "DOP_Pantry_Metric", "DOP_Pantry_tips"),
    ("Pantry_After_Opening", "Pantry_After_Opening_Min", "Pantry_After_Opening_Max", "Pantry_After_Opening_Metric", None),
    ("Refrigerate", "Refrigerate_Min", "Refrigerate_Max", "Refrigerate_Metric", "Refrigerate_tips"),
    ("DOP_Refrigerate", "DOP_Refrigerate_Min", "DOP_Refrigerate_Max", "DOP_Refrigerate_Metric", "DOP_Refrigerate_tips"),
    ("Refrigerate_After_Opening", "Refrigerate_After_Opening_Min", "Refrigerate_After_Opening_Max", "Refrigerate_After_Opening_Metric", None),
    ("Refrigerate_After_Thawing", "Refrigerate_After_Thawing_Min", "Refrigerate_After_Thawing_Max", "Refrigerate_After_Thawing_Metric", None),
    ("Freeze", "Freeze_Min", "Freeze_Max", "Freeze_Metric", "Freeze_Tips"),
    ("DOP_Freeze", "DOP_Freeze_Min", "DOP_Freeze_Max", "DOP_Freeze_Metric", "DOP_Freeze_Tips"),
)
NUMERIC_UNITS = {"day", "days", "hour", "hours", "week", "weeks", "month", "months", "year", "years"}
QUALITATIVE_METRICS = {"indefinitely", "not recommended", "package use-by date", "when ripe"}


class ImportValidationError(ValueError):
    """The source workbook structure cannot be safely imported."""


class _XlsSheet:
    def __init__(self, sheet):
        self.sheet = sheet

    def iter_rows(self, *, values_only=True, min_row=1):
        for row_index in range(min_row - 1, self.sheet.nrows):
            values = []
            for cell in self.sheet.row(row_index):
                if cell.ctype == xlrd.XL_CELL_DATE:
                    values.append(xlrd.xldate_as_datetime(cell.value, self.sheet.book.datemode))
                elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    values.append(None)
                else:
                    values.append(cell.value)
            yield tuple(values)


class _XlsWorkbook:
    def __init__(self, book):
        self.book = book
        self.sheetnames = book.sheet_names()

    def __getitem__(self, name):
        return _XlsSheet(self.book.sheet_by_name(name))

    def close(self):
        self.book.release_resources()


def _text(value):
    return "" if value is None else str(value).strip()


def _empty(value):
    return value is None or _text(value) == ""


def _number(value, label):
    if isinstance(value, bool) or _empty(value):
        raise ValueError(f"{label} is missing")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} is not numeric") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if number < 0:
        raise ValueError(f"{label} must be nonnegative")
    return int(number) if number.is_integer() else number


def _id(value, label):
    number = _number(value, label)
    if not isinstance(number, int):
        raise ValueError(f"{label} must be a whole number")
    return number


def _date_text(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _text(value)
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return None


def row_object(cells):
    """Convert FoodKeeper JSON-export cells into a normal row dictionary."""
    if isinstance(cells, dict):
        return dict(cells)
    if not isinstance(cells, (list, tuple)):
        raise ImportValidationError("JSON source contains a malformed table row")
    result = {}
    for cell in cells:
        if not isinstance(cell, dict):
            raise ImportValidationError("JSON source cells must be column/value objects")
        result.update(cell)
    return result


def _read_json_source(path):
    try:
        source = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImportValidationError(f"Unable to read FoodKeeper JSON source: {exc}") from exc
    if not isinstance(source, dict) or not isinstance(source.get("sheets"), list):
        raise ImportValidationError("JSON source must contain a 'sheets' array")
    sheets = {}
    for sheet in source["sheets"]:
        if not isinstance(sheet, dict) or not _text(sheet.get("name")) or not isinstance(sheet.get("data"), list):
            raise ImportValidationError("Each JSON sheet must contain a name and data array")
        name = _text(sheet["name"])
        if name in sheets:
            raise ImportValidationError(f"Duplicate source sheet '{name}'")
        sheets[name] = [row_object(row) for row in sheet["data"]]
    return sheets


def _read_workbook_source(path):
    suffix = Path(path).suffix.casefold()
    try:
        if suffix == ".xls":
            if xlrd is None:
                raise RuntimeError("Importing .xls files requires xlrd; install the ai-services requirements")
            workbook = _XlsWorkbook(xlrd.open_workbook(filename=str(path), on_demand=True))
        elif suffix == ".xlsx":
            if load_workbook is None:
                raise RuntimeError("Importing .xlsx files requires openpyxl; install the ai-services requirements")
            workbook = load_workbook(filename=path, read_only=True, data_only=True)
        else:
            raise ImportValidationError(f"Unsupported source format '{suffix}'; use .xls, .xlsx, or .json")
    except ImportValidationError:
        raise
    except Exception as exc:
        raise ImportValidationError(f"Unable to read source workbook: {exc}") from exc
    try:
        result = {}
        for name in workbook.sheetnames:
            rows = workbook[name].iter_rows(values_only=True)
            header = next(rows, None)
            if not header:
                result[name] = []
                continue
            fields = [_text(value) for value in header]
            populated_fields = [field for field in fields if field]
            if len(populated_fields) != len(set(populated_fields)):
                raise ImportValidationError(f"'{name}' sheet has duplicate fields")
            result[name] = [
                {field: row[index] if index < len(row) else None for index, field in enumerate(fields) if field}
                for row in rows
                if any(not _empty(value) for value in row)
            ]
        return result
    finally:
        workbook.close()


def _required_table(sheets, name, fields):
    rows = sheets.get(name)
    if rows is None:
        raise ImportValidationError(f"Missing required sheet '{name}'")
    if not rows:
        raise ImportValidationError(f"'{name}' sheet is empty; expected fields: {', '.join(fields)}")
    found = set().union(*(row.keys() for row in rows))
    missing = [field for field in fields if field not in found]
    if missing:
        raise ImportValidationError(f"'{name}' sheet is missing required fields: {', '.join(missing)}")
    return rows


def _provenance(version_rows):
    current = [row for row in version_rows
               if _text(row.get("Current_Version")).casefold() in {"yes", "y", "true", "1"}]
    if len(current) > 1:
        raise ImportValidationError("'Version' sheet marks more than one row as the current source version")
    if not current:
        return None, None, "unavailable"
    row = current[0]
    try:
        version = _id(row.get("Data_Version_Number"), "Data_Version_Number")
    except ValueError:
        version = None
    modified = _date_text(row.get("Modified_Date"))
    return version, modified, "available" if version is not None and modified else "unavailable"


def _validate_ranges(product, row_number, issues):
    valid, qualitative = {}, []
    for field, minimum_key, maximum_key, metric_key, tips_key in RANGE_GROUPS:
        raw_min, raw_max = product.get(minimum_key), product.get(maximum_key)
        metric = _text(product.get(metric_key))
        tips = _text(product.get(tips_key)) if tips_key else ""
        if _empty(raw_min) and _empty(raw_max):
            if metric.casefold() in QUALITATIVE_METRICS:
                qualitative.append({"field": field, "value": metric, "tips": tips})
            elif metric and metric.casefold() not in NUMERIC_UNITS:
                issues.append({"row": row_number, "name": _text(product.get("Name")), "field": field,
                               "reason": f"unsupported shelf-life metric: {metric}"})
            continue
        try:
            minimum = None if _empty(raw_min) else _number(raw_min, "minimum")
            maximum = None if _empty(raw_max) else _number(raw_max, "maximum")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError("minimum exceeds maximum")
            if metric.casefold() not in NUMERIC_UNITS:
                raise ValueError("unit is missing or unsupported for a numeric shelf-life value")
        except ValueError as exc:
            issues.append({"row": row_number, "name": _text(product.get("Name")), "field": field,
                           "reason": str(exc)})
            continue
        valid[field] = {"min": minimum, "max": maximum, "metric": metric, "tips": tips}
    return valid, qualitative


def _days(value, metric):
    unit = _text(metric).casefold().rstrip("s")
    factor = UNIT_TO_DAYS.get(unit)
    if value is None or factor is None:
        return None
    return round(float(value) * factor)


def aliases_for(product):
    keyword_parts = [part.strip() for part in re.split(r"[,;]", product.get("Keywords") or "") if part.strip()]
    aliases = [product.get("Name"), product.get("Name_subtitle"), *keyword_parts]
    compound_words = {word.casefold() for part in keyword_parts if len(part.split()) > 1
                      for word in re.findall(r"[\w'-]+", part)}
    product_name = (product.get("Name") or "").casefold().strip()
    primary_forms = {product_name}
    if product_name.endswith("ies"):
        primary_forms.add(product_name[:-3] + "y")
    elif product_name.endswith("s"):
        primary_forms.add(product_name[:-1])
    subtitle = (product.get("Name_subtitle") or "").strip()
    if len(product_name.split()) == 1 and len(subtitle.split()) == 1:
        aliases.append(f"{subtitle} {product.get('Name')}")
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
        return (word in compound_words or word in name_words or word in subtitle_words
                or (len(product_name.split()) == 1 and product_name.startswith(word) and len(word) < len(product_name)))

    aliases = [alias for alias in aliases if not is_ambiguous_component(alias)]
    return list(dict.fromkeys(value.strip() for value in aliases
                              if value and value.strip() and value.strip().casefold() != "all"))


def _runtime_zones(valid_ranges):
    zones = {}
    for zone, dop, general in (("pantry", "DOP_Pantry", "Pantry"),
                               ("fridge", "DOP_Refrigerate", "Refrigerate"),
                               ("freezer", "DOP_Freeze", "Freeze")):
        source_range = valid_ranges.get(dop) or valid_ranges.get(general)
        if not source_range:
            continue
        days_min = _days(source_range["min"], source_range["metric"])
        days_max = _days(source_range["max"], source_range["metric"])
        if days_min is None and days_max is None:
            continue
        zones[zone] = {
            "min_days": days_min if days_min is not None else days_max,
            "max_days": days_max if days_max is not None else days_min,
        }
    return zones


def build_catalogue(source_path):
    source_path = Path(source_path)
    sheets = _read_json_source(source_path) if source_path.suffix.casefold() == ".json" else _read_workbook_source(source_path)
    missing_sheets = [name for name in REQUIRED_SHEETS if name not in sheets]
    if missing_sheets:
        raise ImportValidationError(f"Missing required sheet(s): {', '.join(missing_sheets)}")
    version_rows = _required_table(sheets, "Version", VERSION_FIELDS)
    category_rows = _required_table(sheets, "Category", CATEGORY_FIELDS)
    product_rows = _required_table(sheets, "Product", PRODUCT_FIELDS)
    source_version, source_date, provenance_status = _provenance(version_rows)

    categories = {}
    for row in category_rows:
        try:
            category_id = _id(row.get("ID"), "category ID")
        except ValueError as exc:
            raise ImportValidationError(f"Invalid category row: {exc}") from exc
        if category_id in categories:
            raise ImportValidationError(f"Duplicate category ID {category_id}")
        if not _text(row.get("Category_Name")):
            raise ImportValidationError(f"Category {category_id} has no Category_Name")
        categories[category_id] = row

    skipped, range_issues = [], []
    entries_by_key = {}
    imported_count = 0
    seen_ids = set()
    for row_number, product in enumerate(product_rows, start=2):
        name = _text(product.get("Name"))
        try:
            product_id = _id(product.get("ID"), "product ID")
            category_id = _id(product.get("Category_ID"), "category ID")
        except ValueError as exc:
            skipped.append({"row": row_number, "name": name or None, "reason": str(exc)})
            continue
        if product_id in seen_ids:
            skipped.append({"row": row_number, "name": name or None, "reason": f"duplicate product ID {product_id}"})
            continue
        seen_ids.add(product_id)
        if not name:
            skipped.append({"row": row_number, "product_id": product_id, "reason": "food name is missing"})
            continue
        category = categories.get(category_id)
        if category is None:
            skipped.append({"row": row_number, "name": name, "reason": f"unknown category ID {category_id}"})
            continue
        row_issues = []
        valid_ranges, qualitative = _validate_ranges(product, row_number, row_issues)
        range_issues.extend(row_issues)
        zones = _runtime_zones(valid_ranges)
        if not zones:
            detail = "no numeric pantry, refrigerator, or freezer duration"
            if qualitative:
                detail += " (qualitative guidance only)"
            if row_issues:
                issue_reasons = "; ".join(f"{issue['field']}: {issue['reason']}" for issue in row_issues)
                detail += f"; rejected ranges: {issue_reasons}"
            skipped.append({"row": row_number, "product_id": product_id, "name": name, "reason": detail})
            continue

        primary = _text(category.get("Category_Name")) or "Food"
        subcategory = _text(category.get("Subcategory_Name")) or None
        group = "Fish" if primary == "Seafood" else primary
        label = f"{group} - {subcategory}" if subcategory else group
        key = (name, label, json.dumps(zones, sort_keys=True))
        entry = entries_by_key.setdefault(key, {
            "name": name, "matched_food": label, "aliases": [], "zones": zones,
        })
        entry["aliases"] = list(dict.fromkeys(entry["aliases"] + aliases_for(product)))
        imported_count += 1

    entries = list(entries_by_key.values())
    if not entries:
        raise ImportValidationError("No usable FoodKeeper entries found; catalogue was not written")
    return {
        "source_name": "USDA FoodKeeper (FSIS)",
        "source_url": SOURCE_URL,
        "source_data_version": source_version,
        "source_data_date": source_date,
        "provenance_status": provenance_status,
        "license": "CC0-1.0",
        "entries": entries,
        "imported_count": imported_count,
        "entry_count": len(entries),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "range_issue_count": len(range_issues),
        "range_issues": range_issues,
    }


def write_catalogue(catalogue, output_path=OUTPUT):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_path.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(catalogue, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, output_path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local USDA FoodKeeper .xls, .xlsx, or workbook JSON export")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    try:
        catalogue = build_catalogue(args.source)
    except (ImportValidationError, RuntimeError) as exc:
        parser.error(str(exc))
    write_catalogue(catalogue, args.output)
    print(json.dumps({key: catalogue[key] for key in (
        "source_data_version", "source_data_date", "provenance_status", "imported_count",
        "entry_count", "skipped_count", "skipped", "range_issue_count", "range_issues",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
