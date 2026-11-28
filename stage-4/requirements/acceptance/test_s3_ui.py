"""Stage 3 screens: the data-testid attributes of stage-2.md name only the six fields; `executives` takes none of them
and a screen that shows it does so with other markup; on /contested "no field is contested" means none of the six.
IDs (S3-*) in docstrings refer to ../LEDGER.md. (The stage-2 screen tests, carried forward, still apply.)"""
import re

from playwright.sync_api import expect

from conftest import FIELDS
from test_s2_ui import api_ready, build_many, goto, t, tids

PAX, MER = "paxton-quay.test", "meridian-ledger.test"


def all_ids(page):
    return page.eval_on_selector_all("[data-testid]", "els => els.map(e => e.getAttribute('data-testid'))")


def test_a_contested_executive_alone_does_not_fill_the_contested_screen(ui):
    """S3-EX-14 S3-UI-1 (paxton-quay: cfo contested, the six fields are not: /contested says nothing is contested)"""
    w = ui.w
    build_many(w, PAX)
    pg = ui.page()
    goto(pg, "/contested", "empty-contested|contested-list")
    expect(t(pg, "empty-contested")).to_be_visible()
    assert not tids(pg, r"contested-item-.*"), tids(pg, r"contested-item-.*")
    assert not any("executives" in i for i in all_ids(pg))
    assert not ui.errors, ui.errors


def test_executives_take_none_of_the_stage_2_test_ids(ui):
    """S3-EX-14 S3-UI-2 (dossier and evidence screens keep exactly six field-* and evidence-* containers; no test id
    names executives or a title as a field; contested lists only the six fields)"""
    w = ui.w
    build_many(w, PAX, MER)
    pg = ui.page()
    goto(pg, f"/dossiers/{PAX}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready")
    assert tids(pg, r"field-(legal_name|hq_city|ceo|founded_year|headcount_range|funding_total)") \
        == [f"field-{f}" for f in FIELDS]
    assert not [i for i in all_ids(pg) if re.search(r"(^|-)(executives?|cfo|coo|cto)(-|$)", i)], all_ids(pg)
    assert not [i for i in tids(pg, r"field-[a-z_]+") if i not in [f"field-{f}" for f in FIELDS]]
    goto(pg, f"/dossiers/{PAX}/evidence", "evidence-ceo")
    assert sorted(tids(pg, r"evidence-(legal_name|hq_city|ceo|founded_year|headcount_range|funding_total)")) \
        == sorted(f"evidence-{f}" for f in FIELDS)
    assert not [i for i in all_ids(pg) if re.search(r"(^|-)(executives?|cfo|coo|cto)(-|$)", i)], all_ids(pg)
    goto(pg, "/contested", "contested-list|empty-contested")
    items = tids(pg, r"contested-item-.*")
    assert items == [i for i in items if re.fullmatch(rf"contested-item-{re.escape(MER)}-({'|'.join(FIELDS)})", i)], items
    assert f"contested-item-{MER}-ceo" in items            # meridian's ceo: the company's page against an aggregator
    assert not any(PAX in i for i in items)
    assert not ui.errors, ui.errors
