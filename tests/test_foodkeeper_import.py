import importlib.util
from datetime import date
import json
from pathlib import Path

import pytest
from openpyxl import Workbook


MODULE_PATH = Path(__file__).resolve().parents[1] / "Scripts" / "import_foodkeeper.py"
spec = importlib.util.spec_from_file_location("foodkeeper_import", MODULE_PATH)
foodkeeper_import = importlib.util.module_from_spec(spec)
spec.loader.exec_module(foodkeeper_import)


def source_product(**values):
    row = {field: None for field in foodkeeper_import.PRODUCT_FIELDS}
    row.update(values)
    return row


def make_workbook(path, *, sheets=None, product_fields=None, products=(), current_version=True, source_date=date(2018, 9, 6)):
    workbook = Workbook()
    version = workbook.active
    version.title = "Version"
    version_fields = ["Data_Version_Number", "Current_Version", "Modified_Date"]
    version.append(version_fields)
    version.append([128, "Yes" if current_version else "", source_date])

    category = workbook.create_sheet("Category")
    category.append(list(foodkeeper_import.CATEGORY_FIELDS))
    category.append([1, "Produce", "Fruit"])

    product = workbook.create_sheet("Product")
    fields = product_fields or list(foodkeeper_import.PRODUCT_FIELDS)
    product.append(fields)
    for item in products:
        product.append([item.get(field) for field in fields])

    if sheets:
        for sheet_name in sheets:
            if sheet_name not in workbook.sheetnames:
                workbook.create_sheet(sheet_name)
    workbook.save(path)


def test_imports_real_foodkeeper_fields_and_reports_bad_ranges(tmp_path):
    source = tmp_path / "fixture.xlsx"
    make_workbook(source, products=[
        source_product(ID=1, Category_ID=1, Name="Apple", Pantry_Min=3, Pantry_Max=5, Pantry_Metric="Days"),
        source_product(ID=2, Category_ID=1, Name="Negative", DOP_Pantry_Min=-1, DOP_Pantry_Max=3, DOP_Pantry_Metric="Weeks"),
        source_product(ID=3, Category_ID=1, Name="Inverted", Freeze_Min=8, Freeze_Max=2, Freeze_Metric="Months"),
        source_product(ID=4, Category_ID=1, Name="Prose", Refrigerate_After_Thawing_Min="Or until best-by date."),
        source_product(ID=7, Category_ID=1, Name="Unknown unit", Pantry_Metric="seasons"),
        source_product(ID=5, Category_ID=1, Name="Fruit cocktail", Pantry_Max=18, Pantry_Metric="Months"),
        source_product(ID=6, Category_ID=1, Name="Banana", Pantry_Metric="When Ripe"),
    ])

    result = foodkeeper_import.build_catalogue(source)

    assert result["source_data_version"] == 128
    assert result["source_data_date"] == "2018-09-06"
    assert result["provenance_status"] == "available"
    assert result["imported_count"] == 2
    assert result["entry_count"] == 2
    assert result["skipped_count"] == 5
    assert result["range_issue_count"] == 4
    apple, cocktail = result["entries"]
    assert apple["zones"]["pantry"] == {"min_days": 3, "max_days": 5}
    assert cocktail["zones"]["pantry"] == {"min_days": 540, "max_days": 540}
    reasons = [issue["reason"] for issue in result["range_issues"]]
    assert "minimum must be nonnegative" in reasons
    assert "minimum exceeds maximum" in reasons
    assert "minimum is not numeric" in reasons
    assert "unsupported shelf-life metric: seasons" in reasons
    skipped_reasons = [record["reason"] for record in result["skipped"]]
    assert any("minimum must be nonnegative" in reason for reason in skipped_reasons)


@pytest.mark.parametrize("missing_sheet,missing_field,expected", [
    ("Product", None, "Missing required sheet"),
    (None, "DOP_Refrigerate_Min", "Product' sheet is missing required fields: DOP_Refrigerate_Min"),
])
def test_changed_source_structure_fails_without_replacing_catalogue(tmp_path, missing_sheet, missing_field, expected):
    source, output = tmp_path / "changed.xlsx", tmp_path / "catalogue.json"
    product_fields = [field for field in foodkeeper_import.PRODUCT_FIELDS if field != missing_field]
    make_workbook(source, product_fields=product_fields,
                  products=[source_product(ID=1, Category_ID=1, Name="Apple", Pantry_Min=1, Pantry_Max=2, Pantry_Metric="Days")])
    if missing_sheet == "Product":
        # Make a structurally altered workbook by replacing the required tab.
        altered = Workbook()
        altered.active.title = "Version"
        altered.active.delete_rows(1, 1)
        altered.active.append(["Data_Version_Number", "Current_Version", "Modified_Date"])
        altered.active.append([128, "Yes", date(2018, 9, 6)])
        category = altered.create_sheet("Category")
        category.append(list(foodkeeper_import.CATEGORY_FIELDS))
        category.append([1, "Produce", "Fruit"])
        altered.create_sheet("Products")
        altered.save(source)
    output.write_text("old runtime catalogue", encoding="utf-8")

    with pytest.raises(foodkeeper_import.ImportValidationError, match=expected):
        catalogue = foodkeeper_import.build_catalogue(source)
        foodkeeper_import.write_catalogue(catalogue, output)

    assert output.read_text(encoding="utf-8") == "old runtime catalogue"


def test_missing_current_version_is_reported_as_unavailable(tmp_path):
    source = tmp_path / "unknown-version.xlsx"
    make_workbook(source, current_version=False,
                  products=[source_product(ID=1, Category_ID=1, Name="Apple", Pantry_Min=1, Pantry_Max=2, Pantry_Metric="Days")])

    result = foodkeeper_import.build_catalogue(source)

    assert result["source_data_version"] is None
    assert result["source_data_date"] is None
    assert result["provenance_status"] == "unavailable"


def test_unparseable_source_date_is_not_claimed_as_available(tmp_path):
    source = tmp_path / "bad-date.xlsx"
    make_workbook(source, source_date="unknown date",
                  products=[source_product(ID=1, Category_ID=1, Name="Apple", Pantry_Min=1, Pantry_Max=2, Pantry_Metric="Days")])

    result = foodkeeper_import.build_catalogue(source)

    assert result["source_data_version"] == 128
    assert result["source_data_date"] is None
    assert result["provenance_status"] == "unavailable"


def test_json_workbook_export_preserves_runtime_catalogue_shape(tmp_path):
    source = tmp_path / "source.json"
    product = source_product(ID=1, Category_ID=1, Name="Apple", Keywords="Apple,fruit",
                             DOP_Pantry_Min=2, DOP_Pantry_Max=4, DOP_Pantry_Metric="Weeks")
    payload = {"fileName": "FoodKeeper-Data.xls", "sheets": [
        {"name": "Version", "data": [[
            {"Data_Version_Number": 128}, {"Current_Version": "Yes"}, {"Modified_Date": "09-06-2018"},
        ]]},
        {"name": "Category", "data": [[
            {"ID": 1}, {"Category_Name": "Produce"}, {"Subcategory_Name": "Fruit"},
        ]]},
        {"name": "Product", "data": [[{key: value} for key, value in product.items()]]},
    ]}
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = foodkeeper_import.build_catalogue(source)

    assert result["source_data_version"] == 128
    assert result["source_data_date"] == "2018-09-06"
    assert result["entries"][0]["zones"]["pantry"] == {"min_days": 14, "max_days": 28}
