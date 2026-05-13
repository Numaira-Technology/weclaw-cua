from shared.sidebar_classification import parse_threads_json, threads_to_sidebar_rows


def test_threads_to_sidebar_rows_preserves_selected_state() -> None:
    threads = parse_threads_json(
        '{"threads": [{"name": "运营核心群", "y": 500, '
        '"is_group": true, "unread": true, "unread_badge": "2", "selected": true}]}',
    )

    rows = threads_to_sidebar_rows(
        threads,
        sidebar_image_width=300,
        sidebar_image_height=1000,
        window_left=10,
        window_top=20,
    )

    assert len(rows) == 1
    assert rows[0].selected is True
    assert rows[0].badge_text == "2"
