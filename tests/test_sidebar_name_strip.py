from platform_mac.sidebar_detector import _clean_chat_name, _strip_merged_preview_tail


def test_strip_relative_date_after_name() -> None:
    assert (
        _strip_merged_preview_tail("22 Chapel and 30M 昨天23")
        == "22 Chapel"
    )


def test_strip_clock_time_tail() -> None:
    assert _strip_merged_preview_tail("厦大大纽约地区校友群2 12:30") == "厦大大纽约地区校友群2"


def test_strip_truncates_at_today() -> None:
    assert _strip_merged_preview_tail("曲亦琳 今天回我") == "曲亦琳"


def test_clean_fullwidth_o_between_ascii() -> None:
    assert _clean_chat_name("ISnIM〇LD") == "ISnIMOLD"


def test_strip_girlsse_suffix() -> None:
    assert (
        _strip_merged_preview_tail("Hackathon Super Girlsse")
        == "Hackathon Super Girls"
    )
