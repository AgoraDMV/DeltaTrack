"""Browser-level (Playwright) tests for the Pass 2 labeling form (#333).

The form (`docs/research/provision-matching/probes/form_template.html`) is where a reviewer's
afternoon of hand labels turns into a file. All of its logic is embedded JavaScript, and the
load-bearing part is the completeness rule: a card reaches the download only with an answer, a
confidence, and — at medium or low confidence — a written rationale. Cards failing that are
dropped silently, which is indistinguishable from cards the reviewer never reached. Nothing
exercised any of it.

These drive a real browser against a real generated form and assert on the downloaded JSON,
because the rule only exists at runtime. Also covers the decision-time timestamps (#334) and the
not-yet-downloaded counter (#335), both of which live in the same export path.

Marked ``browser``; excluded from the default suite. Run with::

    uv run playwright install chromium   # one-time, downloads the browser
    uv run pytest -m browser
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.browser

_PROBES = Path(__file__).resolve().parent.parent / "docs" / "research" / "provision-matching" / "probes"


def _make_form(reviewer: str, n_cards: int) -> str:
    """Render a real form of `n_cards` synthetic cards through the generator reviewers use.

    Goes through `make_form.build_form`, so the rubric, the §5 leak guard and the `</`-escaping
    are the real ones; only the candidate texts are synthetic. The mined worklist is gitignored
    and absent from a fresh clone, so a test cannot depend on it.
    """
    sys.path.insert(0, str(_PROBES))
    try:
        import make_form
    finally:
        sys.path.pop(0)

    cards = [
        make_form._build_card(
            {
                "id": f"hcd-{i:03d}",
                "stratum": "high-containment-different",
                "bill_old": "119-hr-9999",
                "bill_new": "119-hr-9999",
                "version_old": "ih",
                "version_new": "rh",
                "display_path_old": ["Title I", f"Sec. {i}"],
                "display_path_new": ["Title I", f"Sec. {i}"],
                "text_old": f"Synthetic old provision number {i}.",
                "text_new": f"Synthetic new provision number {i}.",
            }
        )
        for i in range(n_cards)
    ]
    return make_form.build_form(reviewer, cards)


@pytest.fixture(scope="module")
def chromium():
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            yield b
            b.close()
    except Exception as exc:  # browser binary not installed, etc.
        pytest.skip(f"Chromium unavailable (run 'playwright install chromium'): {exc}")


class _Form:
    """One open form, driven the way a reviewer drives it."""

    def __init__(self, page, reviewer):
        self.page = page
        self.reviewer = reviewer
        self.dialogs: list[str] = []
        page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.message)
        dialog.accept()

    @property
    def index(self) -> int:
        return int(self.page.inner_text("#pos").split("/")[0]) - 1

    def goto_card(self, index: int) -> None:
        """Navigate to card `index` from wherever we are, using the form's own Prev/Next.

        Forward movement is gated on the current card being finished, so an unfinished card would
        otherwise surface as an opaque click timeout. Assert it directly instead.
        """
        while self.index < index:
            assert self.page.is_enabled("#next"), (
                f"cannot advance past card {self.index}: it is unfinished ({self.page.inner_text('.status')})"
            )
            self.page.click("#next")
        while self.index > index:
            self.page.click("#prev")

    def seed_stored_answers(self, stored: dict) -> None:
        """Put answers straight into browser storage, then reload as a returning reviewer would.

        Reaches past the interface on purpose, to reconstruct a state the interface no longer
        produces (see the stored-without-confidence case below).
        """
        self.page.evaluate(
            "([k, v]) => localStorage.setItem(k, JSON.stringify(v))",
            [f"pass2-labels-{self.reviewer}", stored],
        )
        self.page.reload(wait_until="domcontentloaded")

    def answer(self, index, label=None, confidence=None, rationale=None) -> None:
        self.goto_card(index)
        if label is not None:
            self.page.check(f"input[name=lab][value={label}]")
        if confidence is not None:
            self.page.select_option("#card select", confidence)
        if rationale is not None:
            self.page.fill("#card textarea", rationale)

    def export(self) -> dict:
        with self.page.expect_download() as info:
            self.page.click("text=Download my labels")
        return json.loads(Path(info.value.path()).read_text(encoding="utf-8"))

    @property
    def pending_text(self) -> str:
        return self.page.inner_text("#pending")


@pytest.fixture
def form(chromium, tmp_path, request):
    """A form with 12 cards, opened from disk exactly as a reviewer opens theirs.

    A unique reviewer per test keeps localStorage separate: Chromium treats all `file://` pages as
    one origin, and the form keys its storage by reviewer name, so a shared name would leak one
    test's answers into the next.
    """
    reviewer = f"t{abs(hash(request.node.name)) % 100000}"
    path = tmp_path / f"form_{reviewer}.html"
    path.write_text(_make_form(reviewer, 12), encoding="utf-8")
    page = chromium.new_page()
    page.goto(path.as_uri(), wait_until="domcontentloaded")
    yield _Form(page, reviewer)
    page.close()


def test_complete_card_exports_with_its_answer_intact(form):
    """The straightforward case: what the reviewer entered is what reaches the file."""
    form.answer(0, label="different", confidence="high")

    doc = form.export()

    assert doc["n"] == 1
    (rec,) = doc["labels"]
    assert rec["candidate_id"] == "hcd-000"
    assert rec["label"] == "different"
    assert rec["confidence"] == "high"


def test_medium_confidence_needs_a_rationale_to_be_exported(form):
    """Medium/low confidence without a written rationale is dropped; with one it survives.

    Both halves matter: the drop is the rule, and the recovery proves the rationale is what the
    rule is actually keyed on rather than something incidental about the card.
    """
    form.answer(0, label="same", confidence="medium")

    assert form.export()["n"] == 0, "medium confidence with no rationale must not be exported"

    form.answer(0, rationale="Shared citation, but the subject really continues.")
    doc = form.export()

    assert doc["n"] == 1
    assert doc["labels"][0]["rationale"] == "Shared citation, but the subject really continues."


def test_whitespace_only_rationale_does_not_satisfy_the_rule(form):
    """A rationale of spaces is not a rationale — the rule trims before judging."""
    form.answer(0, label="same", confidence="low", rationale="   ")

    assert form.export()["n"] == 0


def test_started_but_incomplete_cards_are_named_and_untouched_ones_are_not(form):
    """The distinction the reviewer depends on when deciding whether they are done.

    A card downgraded to medium without a rationale is dropped AND named, so the reviewer can go
    finish it. A card never touched is also dropped but must NOT be named, or the warning would
    list every remaining card and be ignored.
    """
    form.answer(0, label="different")  # complete: the answer click sets confidence to high
    form.answer(1, label="same", confidence="medium")  # started, owes a rationale
    # cards 2..11 never touched

    doc = form.export()

    assert [r["candidate_id"] for r in doc["labels"]] == ["hcd-000"]
    assert len(form.dialogs) == 1, f"expected exactly one warning, got {form.dialogs}"
    warning = form.dialogs[0]
    assert "hcd-001" in warning, "the started-but-incomplete card must be named"
    assert "hcd-002" not in warning, "a never-touched card must not be reported as incomplete"


def test_picking_an_answer_sets_confidence_to_high(form):
    """A clear-cut card is one click.

    Most cards in the pool are clear-cut, and the reviewer labels hundreds, so a mandatory second
    click on every one of them costs a lot and decides nothing. `high` consequently means "not
    downgraded"; medium and low remain deliberate.
    """
    form.answer(0, label="different")  # answer only, no confidence touched

    (rec,) = form.export()["labels"]

    assert rec["confidence"] == "high"


def test_downgrading_confidence_overrides_the_default_and_survives_a_re_answer(form):
    """The default must not claw back a downgrade the reviewer made on purpose."""
    form.answer(0, label="different", confidence="low", rationale="Shared citation only.")
    form.answer(0, label="same")  # change the answer; confidence must stay where it was put

    (rec,) = form.export()["labels"]

    assert rec["label"] == "same"
    assert rec["confidence"] == "low"


def test_cannot_advance_past_an_unfinished_card(form):
    """Forward movement is gated so a card cannot be left half-answered by walking past it."""
    assert not form.page.is_enabled("#next"), "an unanswered card must block Next"
    assert not form.page.is_enabled("#jump"), "and must block 'Next unfinished' too"

    form.answer(0, label="same", confidence="medium")  # owes a rationale
    assert not form.page.is_enabled("#next"), "medium confidence without a rationale still blocks"
    assert "add a rationale" in form.page.inner_text(".status")

    # Call the navigation directly, not through the buttons. A disabled button cannot be clicked,
    # so clicking alone would only ever prove the button is disabled and would leave the rule
    # itself unexercised — the gate has to hold even if a later change re-enables the control.
    form.page.evaluate("go(1)")
    form.page.evaluate("jumpNext()")
    assert form.index == 0, "navigation must refuse to leave an unfinished card"

    form.answer(0, rationale="Same account, amount edited.")
    assert form.page.is_enabled("#next")

    form.page.click("#next")
    assert form.index == 1


def test_going_back_is_never_blocked(form):
    """Reviewing an earlier answer is not what leaves a card unfinished, so Prev stays free."""
    form.answer(0, label="different")
    form.page.click("#next")
    form.page.click("#card select")  # focus only; card 1 is still unanswered

    form.page.click("#prev")

    assert form.index == 0


def test_an_answer_stored_without_a_confidence_is_still_held_back(form):
    """The completeness rule does not lean on the default having run.

    The interface no longer produces an answer without a confidence, but browser storage from an
    earlier build can hold one, and it must not be exported as though it were finished.
    """
    form.seed_stored_answers({"hcd-000": {"label": "different"}})

    doc = form.export()

    assert doc["n"] == 0
    assert "hcd-000" in form.dialogs[0]


def test_answers_survive_a_reload(form):
    """Reviewers work in sittings, so a closed tab must not cost them the sitting."""
    form.answer(0, label="different", confidence="high")
    form.answer(1, label="same", confidence="medium", rationale="Same account, amount edited.")

    form.page.reload(wait_until="domcontentloaded")

    doc = form.export()
    assert {r["candidate_id"] for r in doc["labels"]} == {"hcd-000", "hcd-001"}
    assert doc["labels"][1]["rationale"] == "Same account, amount edited."


def test_labels_carry_the_decision_time_not_the_download_time(form):
    """`labeled_at` means what its name says (#334).

    Pre-fix, every record in a file carried one timestamp computed at export, so two decisions
    made hours apart were indistinguishable. Asserting only that the field exists would pass on
    that bug; these assert it differs from the export stamp and between two cards answered at
    different moments.
    """
    form.answer(0, label="different", confidence="high")
    form.page.wait_for_timeout(1100)  # a real gap, so second-resolution clocks can't collapse it
    form.answer(1, label="same", confidence="high")

    doc = form.export()
    first, second = (r["labeled_at"] for r in sorted(doc["labels"], key=lambda r: r["candidate_id"]))

    assert first < second, "two cards answered a second apart must not share a timestamp"
    assert first < doc["exported_at"], "labeled_at must precede the download, not equal it"


def test_editing_an_answer_keeps_the_original_decision_time(form):
    """A later edit moves `last_modified_at`, not `labeled_at`."""
    form.answer(0, label="different", confidence="high")
    form.page.wait_for_timeout(1100)
    form.answer(0, label="same")

    (rec,) = form.export()["labels"]

    assert rec["labeled_at"] < rec["last_modified_at"]


def test_header_reports_answers_not_yet_in_a_downloaded_file(form):
    """The gap #335 is about: labeled and downloaded are different states, and only one is durable."""
    form.answer(0, label="different", confidence="high")
    form.answer(1, label="same", confidence="high")

    assert form.pending_text == "2 not downloaded"

    form.export()
    assert form.pending_text == "", "after a download nothing is pending"

    form.answer(2, label="different", confidence="high")
    assert form.pending_text == "1 not downloaded"


def test_editing_a_downloaded_answer_makes_it_pending_again(form):
    """The file the reviewer already sent no longer matches what is in the browser."""
    form.answer(0, label="different", confidence="high")
    form.export()
    assert form.pending_text == ""

    form.answer(0, label="same")

    assert form.pending_text == "1 not downloaded"


def test_backlog_banner_appears_and_a_download_clears_it(form):
    """A counter alone is easy to not look at; the banner is the part that interrupts.

    It stays up while the backlog stands rather than firing once, so a reviewer who ignores it
    is not left with a silently accumulating risk.
    """
    banner = form.page.locator("#nudge")

    for i in range(9):
        form.answer(i, label="different", confidence="high")
    assert not banner.is_visible(), "banner must not fire below the threshold"

    form.answer(9, label="different", confidence="high")
    assert banner.is_visible(), "10 undownloaded answers must raise the banner"
    assert "not in a downloaded file" in banner.inner_text()

    form.export()
    assert not banner.is_visible(), "downloading must clear the banner"
