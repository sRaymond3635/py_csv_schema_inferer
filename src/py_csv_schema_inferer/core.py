"""Infer column data types for a CSV by sampling rows.

Supported types, in order of increasing generality:
    bool < int < float < date < string

A column is classified as the most specific type that EVERY non-empty sampled
value satisfies. This all-or-nothing rule avoids surprising mixed schemas and
keeps the caller in control of leniency.
"""

from __future__ import annotations

import csv
import datetime
import io
from typing import Dict, List, Optional, Sequence


__all__ = [
    "infer_schema",
    "infer_column_types",
    "SchemaInferer",
    "TypeInferenceError",
]


_TYPE_ORDER = ("bool", "int", "float", "date", "string")


# Booleans match a small, fixed set of textual forms. By refusing "1"/"0" here
# we force a numeric-looking column to classify as int rather than bool, which is
# far less surprising to downstream consumers. Adjust this set if your data uses
# other spellings.
_BOOL_FORMS = frozenset({
    "true", "false",
    "yes", "no",
    "y", "n",
    "t", "f",
})

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
)


class TypeInferenceError(ValueError):
    """Raised when the CSV cannot be read or has no header row."""


def _is_bool(value: str) -> bool:
    return value.lower() in _BOOL_FORMS


def _is_int(value: str) -> bool:
    # int() accepts leading/trailing whitespace and surrounding underscores in
    # modern Python; neither is desirable in a CSV cell, so validate strictly.
    stripped = value.strip()
    if stripped == "":
        return False
    if "_" in stripped:
        return False
    try:
        int(stripped, 10)
    except ValueError:
        return False
    return True

def _is_float(value: str) -> bool:
    stripped = value.strip()
    if stripped == "":
        return False
    if "_" in stripped:
        return False
    if "inf" in stripped.lower() or "nan" in stripped.lower():
        # float() parses these; treat them as non-numeric so a column of "NaN"
        # strings doesn't silently become float.
        return False
    try:
        float(stripped)
    except ValueError:
        return False
    return True


def _is_date(value: str) -> bool:
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
        # Reject out-of-range components like 2020-13-40 that strptime may
        # accept via overflow.
        reconstructed = parsed.strftime(fmt)
        if reconstructed != value:
            continue
        return True
    return False


def _classify_value(value: str) -> str:
    """Return the most specific type name a single non-empty cell matches."""
    if _is_bool(value):
        return "bool"
    if _is_int(value):
        return "int"
    if _is_float(value):
        return "float"
    if _is_date(value):
        return "date"
    return "string"


def _narrowest_common_type(types: Sequence[str]) -> str:
    """Pick the most specific type that all sampled values satisfy.

    Implemented as an intersection over a total order rather than per-pair
    narrowing: it is O(n) in the number of samples and the order itself makes
    the "and" rule unambiguous.
    """
    if not types:
        return "string"
    best = _TYPE_ORDER.index("bool")
    for t in types:
        idx = _TYPE_ORDER.index(t)
        if idx > best:
            best = idx
    return _TYPE_ORDER[best]


class SchemaInferer:
    """Infer per-column types by sampling the first N data rows of a CSV.

    Attributes:
        sample_size: Maximum number of data rows to inspect. Defaults to 100.
        allow_no_header: If False (default) a CSV with zero data rows
            raises TypeInferenceError. Set True to accept an empty CSV.

    The CSV is parsed with Python's csv module. An explicit NUL byte in a cell
    is treated as a literal empty cell because the csv module cannot represent
    NULs and surrounding code should never feed them in.
    """

    def __init__(
        self,
        sample_size: int = 100,
        *,
        allow_no_header: bool = False,
    ) -> None:
        if sample_size <= 0:
            raise ValueError("sample_size must be a positive integer")
        self.sample_size = sample_size
        self.allow_no_header = allow_no_header

    def _read_rows(self, source) -> List[List[str]]:
        """Parse up to sample_size+1 rows (header + samples) from source."""
        rows: List[List[str]] = []
        if isinstance(source, str):
            reader = csv.reader(io.StringIO(source))
        elif isinstance(source, io.IOBase):
            reader = csv.reader(source)
        else:
            reader = csv.reader(source)
        for row in reader:
            rows.append(row)
            if len(rows) > self.sample_size:
                break
        return rows

    def infer(self, source) -> List[str]:
        """Return a list of type names, one per column, in header order."""
        if isinstance(source, str):
            source = io.StringIO(source)
        rows = self._read_rows(source)
        if not rows or not rows[0]:
            if self.allow_no_header:
                return []
            raise TypeInferenceError("CSV has no header row")

        header = rows[0]
        data_rows = rows[1:]
        if not data_rows:
            if self.allow_no_header:
                return ["string"] * len(header)
            raise TypeInferenceError("CSV has no data rows to sample")

        columns: List[List[str]] = [[] for _ in header]
        for row in data_rows:
            for i in range(len(header)):
                if i >= len(row):
                    continue
                cell = row[i]
                if "\x00" in cell:
                    cell = cell.replace("\x00", "")
                if cell == "":
                    continue
                columns[i].append(cell)

        types: List[str] = []
        for col in columns:
            per_value = [_classify_value(v) for v in col]
            types.append(_narrowest_common_type(per_value))
        return types


def infer_column_types(source, sample_size: int = 100) -> List[str]:
    """Infer types for each column of a CSV file or string.

    Args:
        source: An iterable yielding lines/rows (e.g. an open text file) or a
            string containing the full CSV text.
        sample_size: Maximum number of data rows to inspect.

    Returns:
        A list of type names ("int", "float", "date", "bool", "string"), one
        per column, in header order.
    """
    return SchemaInferer(sample_size=sample_size).infer(source)


def infer_schema(source, sample_size: int = 100) -> List[Dict[str, str]]:
    """Infer a list of {name, type} dicts, one per column."""
    inferer = SchemaInferer(sample_size=sample_size)
    rows = inferer._read_rows(source)
    if not rows or not rows[0]:
        raise TypeInferenceError("CSV has no header row")
    header = rows[0]
    if isinstance(source, str):
        source = io.StringIO(source)
    types = inferer.infer(source)
    return [{"name": name, "type": t} for name, t in zip(header, types)]
