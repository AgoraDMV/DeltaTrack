"""Tests for the unified renderer's Financial Summary table.

Layout: rowspan groups multiple amount pairs from one change under a single
section cell; each row carries a data-group index for the JS column sort.
Headers are "Old Amount" / "New Amount". Only "real" amount changes (both
sides present and differing) appear — adapters pre-filter amount_pairs.

Money is asserted as a whole cell, never as a bare substring (#264). Comma
grouping makes every amount a prefix of a larger one, so `"$1,000" in html`
is satisfied by "$1,000,000" and a magnitude error renders green. The closing
`</td>` is what makes the assertion able to fail.
"""

from __future__ import annotations

from deltatrack.formatters.diff_html import _build_financial_summary
from deltatrack.formatters.view_model import ChangeView, DiffView


def _change(**overrides) -> ChangeView:
    base = dict(
        change_type="modified",
        heading_html="TITLE I &gt; Customs",
        nav_label_html="TITLE I &gt; Customs",
        section_number="",
        citation_html="",
        degraded=False,
        move_info_html="",
        old_text="",
        new_text="",
        amount_pairs=(),
    )
    base.update(overrides)
    return ChangeView(**base)


def _view(changes) -> DiffView:
    return DiffView(
        bill_type="hr",
        bill_number=1,
        congress=118,
        v1_label="v1",
        v2_label="v2",
        v1_version_number=None,
        v2_version_number=None,
        summary={},
        changes=tuple(changes),
    )


def test_returns_empty_when_no_changes_have_amount_pairs():
    assert _build_financial_summary(_view([])) == ""
    assert _build_financial_summary(_view([_change()])) == ""


def test_table_includes_canonical_headers():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500),))]))
    assert "<h2>Financial Summary</h2>" in html
    assert "<th>Section</th>" in html
    assert "<th>Old Amount</th>" in html
    assert "<th>New Amount</th>" in html
    assert "<th>Change ($)</th>" in html
    assert "<th>Change (%)</th>" in html


def test_table_is_collapsed_by_default_with_an_entry_count():
    """The table is a <details> with no `open`, so the bill text starts on the
    first screen instead of below hundreds of amount rows. The count lives in the
    summary so its size is legible while closed.
    """
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500), (200, 300)))]))
    assert '<details class="financial-summary">' in html
    assert '<details class="financial-summary" open' not in html
    assert '<span class="count">2 amount changes</span>' in html
    assert html.rstrip().endswith("</details>")


def test_entry_count_is_singular_for_one_amount():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500),))]))
    assert '<span class="count">1 amount change</span>' in html


def test_single_pair_row_has_no_rowspan_attribute():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500),))]))
    assert "rowspan=" not in html
    # Section cell links to #change-0 with the heading as the visible label.
    assert '<a href="#change-0">TITLE I &gt; Customs</a>' in html


def test_amounts_and_change_columns_formatted():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500),))]))
    assert '<td class="amount">$1,000</td>' in html
    assert '<td class="amount">$1,500</td>' in html
    assert '<td class="amount change-amount">+$500</td>' in html
    assert '<td class="amount change-amount">+50.0%</td>' in html


def test_decrease_uses_negative_sign_outside_dollar():
    html = _build_financial_summary(_view([_change(amount_pairs=((2000, 1500),))]))
    assert '<td class="amount change-amount">-$500</td>' in html  # sign outside the dollar formatter
    assert '<td class="amount change-amount">-25.0%</td>' in html


def test_multi_pair_change_uses_rowspan_for_section_cell():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500), (2000, 3000)))]))
    # First row carries the section cell with rowspan=2.
    assert 'rowspan="2"' in html
    # Section label appears exactly once even though there are two pairs.
    assert html.count("TITLE I &gt; Customs") == 1
    # Two data rows.
    assert html.count("<tr ") == 2


def test_data_group_attribute_set_per_change():
    """The data-group attr lets the JS sort cluster multi-pair rows together."""
    html = _build_financial_summary(
        _view(
            [
                _change(amount_pairs=((1000, 1500),)),
                _change(amount_pairs=((2000, 2500),)),
            ]
        )
    )
    assert 'data-group="0"' in html
    assert 'data-group="1"' in html


def test_changes_without_amount_pairs_are_skipped():
    html = _build_financial_summary(
        _view(
            [
                _change(),  # no amounts -> skipped
                _change(amount_pairs=((1000, 1500),)),
                _change(),  # no amounts -> skipped
            ]
        )
    )
    # Only the middle change shows up; its anchor is #change-1 (preserves index).
    assert '<a href="#change-1">' in html
    assert "<tr " in html
    assert html.count("<tr ") == 1


def test_zero_old_amount_yields_em_dash_percent():
    html = _build_financial_summary(_view([_change(amount_pairs=((0, 500),))]))
    # Avoids divide-by-zero; em-dash signals "n/a" for percent.
    assert '<td class="amount">$0</td>' in html
    assert '<td class="amount">$500</td>' in html
    assert '<td class="amount change-amount">+$500</td>' in html
    assert '<td class="amount change-amount">—</td>' in html


def test_removed_entry_row_is_negative_and_decrease():
    """#86 whole-item removal: money leaving the bill must read as -$X on a
    decrease row, never as a positive change.

    Only `amount_entries` reaches the added/removed branches — `amount_pairs`
    maps to kind="changed" — so these two branches carried no coverage at all
    while the changed-kind rows were well tested. Cells are asserted whole
    because a substring check cannot see text added around the value.
    """
    html = _build_financial_summary(_view([_change(amount_entries=((500000, None, "removed"),))]))
    assert '<tr class="decrease"' in html
    assert '<td class="amount">$500,000</td>' in html  # old
    assert '<td class="amount">—</td>' in html  # new: gone
    assert '<td class="amount change-amount">-$500,000</td>' in html
    assert '<td class="amount change-amount">-100.0%</td>' in html


def test_added_entry_row_is_positive_with_no_percent_baseline():
    """#86 whole-item addition: +$X on an increase row, and an em-dash percent
    because there is no old amount to compute a change against."""
    html = _build_financial_summary(_view([_change(amount_entries=((None, 500000, "added"),))]))
    assert '<tr class="increase"' in html
    assert '<td class="amount">—</td>' in html  # old: absent
    assert '<td class="amount">$500,000</td>' in html  # new
    assert '<td class="amount change-amount">+$500,000</td>' in html
    assert '<td class="amount change-amount">—</td>' in html


def test_increase_decrease_css_class_on_row():
    html = _build_financial_summary(
        _view(
            [
                _change(amount_pairs=((1000, 1500),)),
                _change(amount_pairs=((2000, 1500),)),
            ]
        )
    )
    assert '<tr class="increase"' in html
    assert '<tr class="decrease"' in html
