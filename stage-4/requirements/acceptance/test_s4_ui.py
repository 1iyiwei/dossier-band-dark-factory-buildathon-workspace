"""Stage 4 screens: `investors` takes none of the data-testid attributes of stage-2.md (as `executives` does); on /contested
"no field is contested" means none of the six fields is. IDs (S4-*) in ../LEDGER.md."""
import re

from playwright.sync_api import expect

from conftest import FIELDS
from test_s2_ui import build_many, goto, t, tids
from test_s3_ui import all_ids

V = "vantage-mill.test"


def test_investors_take_none_of_the_stage_2_test_ids_and_do_not_fill_contested(ui):
    """S4-INV-13 (vantage-mill has investors and a contested funding... the dossier and evidence screens keep exactly six
    field-* and evidence-* containers, no test id names investors, /contested lists only the six fields)"""
    build_many(ui.w, V)
    pg = ui.page()
    goto(pg, f"/dossiers/{V}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready")
    assert tids(pg, r"field-(legal_name|hq_city|ceo|founded_year|headcount_range|funding_total)") == [f"field-{f}" for f in FIELDS]
    assert not [i for i in all_ids(pg) if re.search(r"investor", i)], all_ids(pg)
    assert not [i for i in tids(pg, r"field-[a-z_]+") if i not in [f"field-{f}" for f in FIELDS]]
    goto(pg, f"/dossiers/{V}/evidence", "evidence-ceo")
    assert sorted(tids(pg, r"evidence-[a-z_]+")) == sorted(f"evidence-{f}" for f in FIELDS) or \
        sorted(i for i in tids(pg, r"evidence-[a-z_]+") if not i.startswith("evidence-empty")) == sorted(f"evidence-{f}" for f in FIELDS)
    assert not [i for i in all_ids(pg) if re.search(r"investor", i)]
    goto(pg, "/contested", "contested-list|empty-contested")
    items = tids(pg, r"contested-item-.*")
    assert all(re.fullmatch(rf"contested-item-{re.escape(V)}-({'|'.join(FIELDS)})", i) for i in items), items
    assert not ui.errors, ui.errors
