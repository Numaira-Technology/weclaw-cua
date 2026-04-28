"""Unit tests for HunyuanOCR text spotting parser.

Usage:
    python3 -m unittest tests.test_ocr_hunyuan_parser

Input spec:
    - Synthetic decoded HunyuanOCR strings with rectangle and quadrilateral
      coordinate formats.

Output spec:
    - Verifies parser normalization, coordinate scaling, clipping, and sorting.
"""

import unittest

from shared.ocr_hunyuan_parser import parse_hunyuan_lines


class TestHunyuanOcrParser(unittest.TestCase):
    def test_parse_ref_quad_with_four_points(self) -> None:
        raw = (
            "<ref>群聊</ref><quad>"
            "(10,20),(120,20),(120,50),(10,50)"
            "</quad>"
        )

        lines = parse_hunyuan_lines(raw, 300, 200)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "群聊")
        self.assertEqual(lines[0].bbox, (10, 20, 120, 50))

    def test_parse_plain_text_boxes_and_sort(self) -> None:
        raw = "Bottom (20,100),(80,120)\nTop (5,10),(70,30)"

        lines = parse_hunyuan_lines(raw, 100, 150)

        self.assertEqual([line.text for line in lines], ["Top", "Bottom"])
        self.assertEqual(
            [line.bbox for line in lines],
            [(5, 10, 70, 30), (20, 100, 80, 120)],
        )

    def test_parse_normalized_coordinates(self) -> None:
        raw = "<ref>Alice</ref><quad>(0.1,0.2),(0.4,0.5)</quad>"

        lines = parse_hunyuan_lines(raw, 200, 100)

        self.assertEqual(lines[0].bbox, (20, 20, 80, 50))

    def test_clips_and_strips_wrapper_backslashes(self) -> None:
        raw = r"\ Chat \ (-10,-5),(110,60)"

        lines = parse_hunyuan_lines(raw, 100, 50)

        self.assertEqual(lines[0].text, "Chat")
        self.assertEqual(lines[0].bbox, (0, 0, 100, 50))


if __name__ == "__main__":
    unittest.main()
