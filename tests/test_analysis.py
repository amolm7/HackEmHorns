import json
import unittest

from backend.contracts import Error
from backend.runtime.mcp import analyze_table


class TableAnalysisTests(unittest.TestCase):
    def test_nonfinite_values_fail_with_a_domain_error(self):
        for value in ["NaN", "nan", "Infinity", "-inf", "1e309"]:
            with self.subTest(value=value), self.assertRaisesRegex(Error, "finite"):
                analyze_table(f"channel,spend\nA,{value}\nB,12")

    def test_aggregate_overflow_fails_with_a_domain_error(self):
        with self.assertRaisesRegex(Error, "numeric range"):
            analyze_table("channel,spend\nA,1e308\nB,1e308")
        # The overall sum is finite, but one group overflows before cancellation.
        with self.assertRaisesRegex(Error, "group totals"):
            analyze_table("channel,spend\nA,1e308\nB,-1e308\nA,1e308")

    def test_duplicate_headers_and_extra_cells_are_rejected(self):
        for table in [
            "value,value\n1,x\n2,y",
            "value, value \n1,2",
            ",column 1\n1,2",
            "name,value\nA,1,unlabeled",
        ]:
            with self.subTest(table=table), self.assertRaises(Error):
                analyze_table(table)

    def test_oversized_tables_are_rejected_instead_of_silently_truncated(self):
        tables = [
            "value\n" + "1\n" * 501,
            ",".join(f"c{i}" for i in range(31)) + "\n" + ",".join("1" for _ in range(31)),
        ]
        for table in tables:
            with self.subTest(table=table), self.assertRaisesRegex(Error, "at most"):
                analyze_table(table)
        self.assertEqual(analyze_table("value\n" + "1\n" * 500)["rows"], 500)

    def test_chart_limit_does_not_hide_global_extrema(self):
        table = "channel,spend\n" + "\n".join(f"C{i},{i}" for i in range(13))
        result = analyze_table(table)
        self.assertEqual(len(result["chart"]["points"]), 12)
        self.assertIn("Highest spend: C12 (12)", result["highlights"])
        self.assertIn("Lowest spend: C0 (0)", result["highlights"])
        self.assertTrue(any("first 12 of 13" in h for h in result["highlights"]))
        self.assertEqual(result["numeric"]["spend"]["sum"], 78)

    def test_missing_cells_and_formatted_numbers_remain_json_serializable(self):
        result = analyze_table('channel,spend,notes\nA,"$1,000",ok\nB,25%\nC,,missing')
        self.assertEqual(result["numeric"]["spend"]["sum"], 1025)
        self.assertEqual(result["numeric"]["spend"]["count"], 2)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False))["rows"], 3)
