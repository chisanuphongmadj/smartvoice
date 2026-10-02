"""Shared Dashboard helpers — the bits that don't need a running Streamlit page."""

from datetime import date

import pandas as pd

from smartvoice import dashboard_common as dc

MIN, MAX = date(2026, 5, 1), date(2026, 5, 31)


def test_saved_range_inside_the_data_is_kept():
    assert dc.clamp_date_range((date(2026, 5, 3), date(2026, 5, 9)), MIN, MAX) == (
        date(2026, 5, 3), date(2026, 5, 9),
    )


def test_range_outside_the_loaded_calls_falls_back_to_everything():
    # e.g. a range picked with "ทั้งหมด" loaded, then the limit shrank to 100 calls.
    assert dc.clamp_date_range((date(2026, 4, 1), date(2026, 5, 9)), MIN, MAX) == (MIN, MAX)


def test_half_picked_range_survives_the_rerun():
    assert dc.clamp_date_range((date(2026, 5, 3),), MIN, MAX) == (date(2026, 5, 3),)


def test_missing_or_garbage_range_means_everything():
    assert dc.clamp_date_range(None, MIN, MAX) == (MIN, MAX)
    assert dc.clamp_date_range(("x", "y"), MIN, MAX) == (MIN, MAX)


def test_default_load_limit_depends_on_table_size():
    assert dc.LIMIT_OPTIONS[dc.default_limit_label(800)] is None
    assert dc.LIMIT_OPTIONS[dc.default_limit_label(5000)] == 1000


def test_count_list_field_skips_bad_json_and_blank_items():
    calls = [
        {"keywords": '["ที่นอน", "จัดส่ง"]'},
        {"keywords": '["ที่นอน", " "]'},
        {"keywords": "not json"},
        {"keywords": None},
    ]
    assert dc.count_list_field(calls, "keywords") == [("ที่นอน", 2), ("จัดส่ง", 1)]


def test_hbar_leaves_room_for_the_value_label():
    fig = dc.hbar(pd.DataFrame({"Topic": ["a", "b"], "Count": [4, 2]}), "Topic", dc.SCALE_BRAND)
    assert fig.layout.xaxis.range == (0, 5.0)
