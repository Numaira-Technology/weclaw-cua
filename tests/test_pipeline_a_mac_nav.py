from algo_a.pipeline_a_mac_nav import _allowed_chat_title


def test_allowed_chat_title_accepts_wildcard_groups() -> None:
    assert _allowed_chat_title("Project Group", ["*"])


def test_allowed_chat_title_matches_configured_group() -> None:
    assert _allowed_chat_title("运营核心群", ["运营核心群后半段被隐藏"])


def test_allowed_chat_title_rejects_other_group() -> None:
    assert not _allowed_chat_title("其他群", ["运营核心群后半段被隐藏"])
