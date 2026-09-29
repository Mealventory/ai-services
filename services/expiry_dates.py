"""Conservative extraction of explicitly labelled expiry dates from OCR text."""
from datetime import date
import re

_MONTHS = {}
for number, name in enumerate(('january', 'february', 'march', 'april', 'may', 'june',
                               'july', 'august', 'september', 'october', 'november', 'december'), 1):
    _MONTHS[name] = _MONTHS[name[:3]] = number
_MONTHS['sept'] = 9
# Canadian bilingual month symbols, in year-month-day order.
# https://inspection.canada.ca/en/food-labels/labelling/consumers/date-labels-food
_CANADIAN_MONTHS = dict(zip(
    ('ja', 'fe', 'mr', 'al', 'ma', 'jn', 'jl', 'au', 'se', 'oc', 'no', 'de'),
    range(1, 13),
))
_CANADIAN_MONTH = '(?:' + '|'.join(_CANADIAN_MONTHS) + ')'
_MONTH = '(?:' + '|'.join(sorted(_MONTHS, key=len, reverse=True)) + ')'
_YEAR = r'(?:\d{4}|\d{2})'
_DATE = rf'(?:{_YEAR}[ \t]+{_CANADIAN_MONTH}[ \t]+\d{{1,2}}|\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}}|\d{{1,2}}[-/]\d{{1,2}}[-/]{_YEAR}|{_MONTH}\.?[ \t]+\d{{1,2}},?[ \t]+{_YEAR}|\d{{1,2}}[ \t]+{_MONTH}\.?[ \t]+{_YEAR})'
_LABELLED_DATE = re.compile(
    rf'\b(?:best[ \t]+before|m[ei]+ll?e?u?r[ \t]+avant|use[ \t]+by|expiry|expiration|expires|exp|bb)\b'
    rf'(?:[ \t]+date\b)?[ \t.:\-]*(?:\r?\n[ \t]*)?'
    rf'(?P<date>{_DATE})(?![\w/\-])', re.IGNORECASE,
)


def _validated_date(value: str) -> date | None:
    tokens = re.sub(r'[.,]', '', value.lower()).split()
    try:
        if len(tokens) == 3 and tokens[1] in _CANADIAN_MONTHS and tokens[0].isdigit():
            year, month, day = tokens[0], _CANADIAN_MONTHS[tokens[1]], int(tokens[2])
        elif len(tokens) == 3 and tokens[0] in _MONTHS:
            month, day, year = _MONTHS[tokens[0]], int(tokens[1]), tokens[2]
        elif len(tokens) == 3 and tokens[1] in _MONTHS:
            day, month, year = int(tokens[0]), _MONTHS[tokens[1]], tokens[2]
        else:
            parts = re.split(r'[-/]', value)
            if len(parts) != 3:
                return None
            if len(parts[0]) == 4:
                year, month, day = parts[0], int(parts[1]), int(parts[2])
            else:
                first, second, year = int(parts[0]), int(parts[1]), parts[2]
                # Without a locale, 04/06 could be April 6 or June 4.
                if 1 <= first <= 12 and 1 <= second <= 12 and first != second:
                    return None
                day, month = (first, second) if first > 12 else (second, first)
        full_year = int(year) + (2000 if len(year) == 2 else 0)
        return date(full_year, month, day)
    except ValueError:
        return None


def extract_expiry_dates(text: str) -> list[str]:
    """Return validated date text; never infer an expiry from an unlabelled date.

    Missing years and ambiguous numeric dates are left for manual review.
    Two-digit years mean 2000–2099. Preserve the existing uppercase text API.
    """
    found = []
    seen = set()
    for match in _LABELLED_DATE.finditer(text):
        candidate = ' '.join(match['date'].split()).upper()
        parsed = _validated_date(candidate)
        if parsed is not None and parsed not in seen:
            seen.add(parsed)
            found.append(candidate)

    if not found:
        label_match = re.search(
            r'\b(?:best[ \t]+before|m[ei]+ll?e?u?r[ \t]+avant|use[ \t]+by|expiry|expiration|expires|exp|bb)\b',
            text,
            re.IGNORECASE,
        )
        if label_match:
            canadian_match = re.search(
                rf'\b({_CANADIAN_MONTH})[ \t]+(\d{{1,2}})\b',
                text,
                re.IGNORECASE,
            )
            year_match = re.search(r'\b(202\d|203\d)\b', text)
            if canadian_match and year_match:
                c_month = canadian_match.group(1).upper()
                c_day = canadian_match.group(2)
                candidate = f"{year_match.group(1)} {c_month} {c_day}"
                parsed = _validated_date(candidate)
                if parsed is not None and parsed not in seen:
                    seen.add(parsed)
                    found.append(candidate)

    return found
