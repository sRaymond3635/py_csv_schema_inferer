# py_csv_schema_inferer

A tiny, zero-dependency library that reads a CSV and infers a data type for each column by sampling the first rows. Exports `infer_schema`, `infer_column_types`, `SchemaInferer`, and `TypeInferenceError`.

```python
from py_csv_schema_inferer import infer_schema

schema = infer_schema("name,age,active\nAlice,30,true\nBob,25,false\n")
# [{'name': 'name', 'type': 'string'},
#  {'name': 'age',  'type': 'int'},
#  {'name': 'active','type': 'bool'}]
```

## Why

The problem is mundane but recurring: you receive an arbitrary CSV and want to know what's in it before loading it into a database or a dataframe. Pulling in pandas or a full schema library for this is overkill and adds a heavy dependency. This library samples the first rows, tries each cell against bool, int, float, date, and string in that order, and assigns each column the most specific type that every sampled non-empty value satisfies.

The trade-off is simplicity over statistical inference. We do not compute confidence scores, do not handle type mixing by majority, and do not support custom type plugins. If one cell in a thousand-row sample is a string where the rest are ints, the column is a string. This all-or-nothing rule keeps the behaviour predictable and the caller in control of any leniency.

## Edge cases you will hit

- `1` and `0` are classified as `int`, not `bool`. Booleans are only inferred from textual forms (`true`, `false`, `yes`, `no`, `y`, `n`, `t`, `f`). A column of ones and zeros will not surprise you by becoming `bool`.
- `NaN` and `Inf` strings are not treated as floats; they fall through to `string`.
- Numeric literals with underscores (e.g. `1_000`) are rejected as ints; Python's `int()` accepts them but CSV cells should not carry them.
- Empty cells are skipped during sampling. A column where every sampled cell is empty is typed `string`.
- A CSV with a header but no data rows raises `TypeInferenceError` by default. Pass `allow_no_header=True` to `SchemaInferer` to get a list of `"string"` types instead.
- Dates are recognised in a small fixed set of formats: `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY/MM/DD`. Other formats fall through to `string`. Note that `01/02/2020` matches both `DD/MM/YYYY` and `MM/DD/YYYY`; this ambiguity is accepted — the column is `date` either way.

## Running the tests

```
PYTHONPATH=src python -m unittest discover -s tests
```

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

