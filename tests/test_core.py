import datetime
import io
import os
import tempfile
import unittest

from py_csv_schema_inferer import (
    SchemaInferer,
    TypeInferenceError,
    infer_column_types,
    infer_schema,
)


class TestPrimitives(unittest.TestCase):

    def test_bool_forms(self):
        self.assertEqual(
            infer_column_types("a\ntrue\nfalse\nyes\nno\ny\nn\nt\nf\n"), ["bool"]
        )

    def test_int_column(self):
        self.assertEqual(infer_column_types("a\n1\n2\n3\n"), ["int"])

    def test_float_column(self):
        self.assertEqual(infer_column_types("a\n1.5\n2.0\n3.14\n"), ["float"])

    def test_int_with_negative_and_plus(self):
        self.assertEqual(infer_column_types("a\n-1\n+2\n3\n"), ["int"])

    def test_date_iso(self):
        self.assertEqual(infer_column_types("a\n2020-01-01\n2021-12-31\n"), ["date"])

    def test_date_slash(self):
        self.assertEqual(infer_column_types("a\n01/02/2020\n03/04/2021\n"), ["date"])

    def test_string_fallback(self):
        self.assertEqual(infer_column_types("a\nhello\nworld\n"), ["string"])


class TestBooleanClassification(unittest.TestCase):

    def test_one_and_zero_are_int_not_bool(self):
        self.assertEqual(infer_column_types("a\n1\n0\n"), ["int"])

    def test_true_mixed_with_text_is_string(self):
        self.assertEqual(infer_column_types("a\ntrue\nbanana\n"), ["string"])


class TestNumberClassification(unittest.TestCase):

    def test_float_column_becomes_float_even_if_some_look_int(self):
        self.assertEqual(infer_column_types("a\n1\n2.5\n3\n"), ["float"])

    def test_int_underscores_rejected(self):
        self.assertEqual(infer_column_types("a\n1_000\n2\n"), ["string"])

    def test_nan_string_not_float(self):
        self.assertEqual(infer_column_types("a\nNaN\nnan\n"), ["string"])

    def test_inf_string_not_float(self):
        self.assertEqual(infer_column_types("a\nInf\ninf\n"), ["string"])


class TestDateClassification(unittest.TestCase):

    def test_mixed_date_formats_still_date(self):
        self.assertEqual(
            infer_column_types("a\n2020-01-01\n01/02/2020\n2020/03/04\n"), ["date"]
        )

    def test_not_a_date(self):
        self.assertEqual(infer_column_types("a\n2020-13-40\n2021-01-01\n"), ["string"])


class TestEmptyCells(unittest.TestCase):

    def test_empty_cells_skipped(self):
        self.assertEqual(infer_column_types("a\n1\n\n3\n"), ["int"])

    def test_all_empty_column_is_string(self):
        self.assertEqual(infer_column_types("a\n\n\n\n"), ["string"])


class TestMultipleColumns(unittest.TestCase):

    def test_three_columns(self):
        csv = "id,name,score\n1,alice,3.5\n2,bob,4.0\n"
        self.assertEqual(infer_column_types(csv), ["int", "string", "float"])

    def test_ragged_rows(self):
        csv = "a,b,c\n1,2,3\n4,5\n6\n"
        self.assertEqual(infer_column_types(csv), ["int", "int", "int"])

    def test_schema_with_names(self):
        csv = "id,name,score\n1,alice,3.5\n2,bob,4.0\n"
        schema = infer_schema(csv)
        self.assertEqual(
            schema,
            [
                {"name": "id", "type": "int"},
                {"name": "name", "type": "string"},
                {"name": "score", "type": "float"},
            ],
        )


class TestSampling(unittest.TestCase):

    def test_only_sampled_rows_count(self):
        # 2 good rows then a string; with sample_size=2 stays int.
        csv = "a\n1\n2\nhello\n"
        self.assertEqual(infer_column_types(csv, sample_size=2), ["int"])

    def test_sample_size_zero_raises(self):
        with self.assertRaises(ValueError):
            SchemaInferer(sample_size=0)


class TestEmptyAndErrors(unittest.TestCase):

    def test_empty_csv_raises(self):
        with self.assertRaises(TypeInferenceError):
            infer_column_types("")

    def test_header_only_without_flag_raises(self):
        with self.assertRaises(TypeInferenceError):
            infer_column_types("a,b,c\n")

    def test_header_only_with_flag_returns_strings(self):
        inferer = SchemaInferer(allow_no_header=True)
        self.assertEqual(inferer.infer("a,b,c\n"), ["string", "string", "string"])

    def test_truly_empty_with_flag_returns_empty(self):
        inferer = SchemaInferer(allow_no_header=True)
        self.assertEqual(inferer.infer(""), [])

    def test_quoted_field_with_comma(self):
        csv = 'a,b\n"hello, world",1\n"foo",2\n'
        self.assertEqual(infer_column_types(csv), ["string", "int"])

    def test_nul_byte_treated_as_empty(self):
        csv = "a\n1\n\x00\n3\n"
        self.assertEqual(infer_column_types(csv), ["int"])


class TestFileObjects(unittest.TestCase):

    def test_accepts_open_file_object(self):
        csv = "a\n1\n2\n3\n"
        self.assertEqual(infer_column_types(io.StringIO(csv)), ["int"])

    def test_accepts_real_file_on_disk(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        ) as f:
            f.write("a\n1\n2\n3\n")
            path = f.name
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                self.assertEqual(infer_column_types(fh), ["int"])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
