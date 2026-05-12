from shared.ocr_hunyuan import HunyuanOcrEngine
from shared.ocr_hunyuan_parser import OcrLine


def _line(text: str) -> OcrLine:
    return OcrLine(text=text, bbox=(0, 0, 10, 10))


def test_match_target_accepts_normalized_unicode_ellipsis_prefix() -> None:
    engine = HunyuanOcrEngine()
    candidate = _line("Operations Team…")

    assert engine.match_target([candidate], "Operations Team Daily Standup") is candidate


def test_match_target_accepts_case_insensitive_truncated_prefix() -> None:
    engine = HunyuanOcrEngine()
    candidate = _line("ny cua...")

    assert engine.match_target([candidate], "NY Cua Full Name") is candidate


def test_match_target_rejects_unsafe_short_truncated_prefix() -> None:
    engine = HunyuanOcrEngine()
    candidate = _line("NY...")

    assert engine.match_target([candidate], "NY Cua Full Name", min_sim=0.95) is None


def test_match_target_accepts_truncated_config_name_against_full_ocr_text() -> None:
    engine = HunyuanOcrEngine()
    candidate = _line("Operations Team Daily Standup")

    assert engine.match_target([candidate], "Operations Team...") is candidate
