"""Validate a local USDA FoodKeeper workbook and publish its runtime catalogue."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import math
import os
from pathlib import Path
import tempfile

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None
try:
    import xlrd
except ImportError:
    xlrd = None


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


def _open_workbook(path):
    if Path(path).suffix.casefold() == ".xls":
        if xlrd is None:
            raise RuntimeError("Importing .xls files requires xlrd; install the ai-services requirements")
        return _XlsWorkbook(xlrd.open_workbook(filename=str(path), on_demand=True))
    if load_workbook is None:
        raise RuntimeError("Importing .xlsx files requires openpyxl; install the ai-services requirements")
    return load_workbook(filename=path, read_only=True, data_only=True)


def _text(value):
    return "" if value is None else str(value).strip()


def _empty(value):
    return value is None or _text(value) == ""


def _as_number(value, label):
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


def _as_id(value, label):
    number = _as_number(value, label)
    if not isinstance(number, int):
        raise ValueError(f"{label} must be a whole number")
    return number


def _date_text(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value) or None


def _table(workbook, sheet_name, required_fields):
    sheet = workbook[sheet_name]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        raise ImportValidationError(f"'{sheet_name}' sheet is empty; expected fields: {', '.join(required_fields)}")
    columns = {}
    duplicates = []
    for index, value in enumerate(header):
        name = _text(value)
        if not name:
            continue
        if name in columns:
            duplicates.append(name)
        columns[name] = index
    if duplicates:
        raise ImportValidationError(f"'{sheet_name}' sheet has duplicate fields: {', '.join(sorted(set(duplicates)))}")
    missing = [field for field in required_fields if field not in columns]
    if missing:
        raise ImportValidationError(f"'{sheet_name}' sheet is missing required fields: {', '.join(missing)}")
    return columns, rows


def _row_record(row, columns):
    return {name: row[index] if index < len(row) else None for name, index in columns.items()}


def _source_provenance(workbook):
    columns, rows = _table(workbook, "Version", VERSION_FIELDS)
    current = []
    for row in rows:
        record = _row_record(row, columns)
        if _text(record.get("Current_Version")).casefold() in {"yes", "y", "true", "1"}:
            current.append(record)
    if len(current) > 1:
        raise ImportValidationError("'Version' sheet marks more than one row as the current source version")
    if not current:
        return {"source_version": None, "source_date": None, "provenance_status": "unavailable"}
    row = current[0]
    try:
        version = _as_id(row.get("Data_Version_Number"), "Data_Version_Number")
    except ValueError:
        version = None
    source_date = _date_text(row.get("Modified_Date"))
    available = version is not None and source_date is not None
    return {
        "source_version": version,
        "source_date": source_date,
        "provenance_status": "available" if available else "unavailable",
    }


def _parse_ranges(record, row_number, name, issues):
    ranges, qualitative = [], []
    for field, min_field, max_field, metric_field, tips_field in RANGE_GROUPS:
        raw_min, raw_max = record.get(min_field), record.get(max_field)
        metric = _text(record.get(metric_field))
        tips = _text(record.get(tips_field)) if tips_field else ""
        if _empty(raw_min) and _empty(raw_max):
            if metric.casefold() in QUALITATIVE_METRICS:
                qualitative.append({"field": field, "value": metric, "tips": tips})
            elif metric and metric.casefold() not in NUMERIC_UNITS:
                issues.append({"row": row_number, "name": name, "field": field,
                               "reason": f"unsupported shelf-life metric: {metric}"})
            continue
        try:
            minimum = None if _empty(raw_min) else _as_number(raw_min, "minimum")
            maximum = None if _empty(raw_max) else _as_number(raw_max, "maximum")
            if minimum is None and maximum is None:
                continue
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError("minimum exceeds maximum")
            if metric.casefold() not in NUMERIC_UNITS:
                raise ValueError("unit is missing or unsupported for a numeric shelf-life value")
        except ValueError as exc:
            issues.append({"row": row_number, "name": name, "field": field, "reason": str(exc)})
            continue
        ranges.append({"field": field, "min": minimum, "max": maximum, "unit": metric, "tips": tips})
    return ranges, qualitative


def build_catalogue(workbook_path):
    try:
        workbook = _open_workbook(workbook_path)
    except Exception as exc:
        raise ImportValidationError(f"Unable to read source workbook: {exc}") from exc
    try:
        missing_sheets = [name for name in REQUIRED_SHEETS if name not in workbook.sheetnames]
        if missing_sheets:
            raise ImportValidationError(
                f"Missing required sheet(s): {', '.join(missing_sheets)} "
                f"(found: {', '.join(workbook.sheetnames) or 'none'})"
            )
        provenance = _source_provenance(workbook)
        category_columns, category_rows = _table(workbook, "Category", CATEGORY_FIELDS)
        categories = {}
        for row in category_rows:
            category = _row_record(row, category_columns)
            try:
                category_id = _as_id(category.get("ID"), "category ID")
            except ValueError as exc:
                raise ImportValidationError(f"Invalid category row: {exc}") from exc
            if category_id in categories:
                raise ImportValidationError(f"Duplicate category ID {category_id}")
            categories[category_id] = {
                "name": _text(category.get("Category_Name")),
                "subcategory": _text(category.get("Subcategory_Name")) or None,
            }

        product_columns, product_rows = _table(workbook, "Product", PRODUCT_FIELDS)
        imported, skipped, range_issues = [], [], []
        seen_ids = set()
        for row_number, row in enumerate(product_rows, start=2):
            record = _row_record(row, product_columns)
            if not any(not _empty(value) for value in record.values()):
                continue
            name = _text(record.get("Name"))
            try:
                product_id = _as_id(record.get("ID"), "product ID")
                category_id = _as_id(record.get("Category_ID"), "category ID")
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
            if category_id not in categories:
                skipped.append({"row": row_number, "name": name, "reason": f"unknown category ID {category_id}"})
                continue
            row_issues = []
            ranges, qualitative = _parse_ranges(record, row_number, name, row_issues)
            range_issues.extend(row_issues)
            if not ranges and not qualitative:
                reason = "no valid numeric or qualitative shelf-life data"
                skipped.append({"row": row_number, "product_id": product_id, "name": name, "reason": reason})
                continue
            imported.append({
                "id": product_id,
                "name": name,
                "subtitle": _text(record.get("Name_subtitle")) or None,
                "keywords": _text(record.get("Keywords")) or None,
                "category_id": category_id,
                "category": categories[category_id],
                "shelf_life": ranges,
                "qualitative_guidance": qualitative,
                "range_issues": row_issues,
            })
        if not imported:
            raise ImportValidationError("No usable FoodKeeper product records found; catalogue was not written")
        return {
            "source": "USDA FSIS FoodKeeper",
            **provenance,
            "records": imported,
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "range_issue_count": len(range_issues),
            "range_issues": range_issues,
        }
    finally:
        workbook.close()


def write_catalogue(catalogue, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_path.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(catalogue, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, output_path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local USDA FoodKeeper .xls or .xlsx workbook")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "foodkeeper.json")
    args = parser.parse_args(argv)
    try:
        catalogue = build_catalogue(args.source)
    except (ImportValidationError, RuntimeError) as exc:
        parser.error(str(exc))
    write_catalogue(catalogue, args.output)
    summary = {key: catalogue[key] for key in (
        "source_version", "source_date", "provenance_status", "imported_count",
        "skipped_count", "skipped", "range_issue_count", "range_issues",
    )}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
