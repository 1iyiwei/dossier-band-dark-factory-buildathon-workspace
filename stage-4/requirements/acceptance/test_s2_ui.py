"""Stage 2 screens, through a browser (Playwright/Chromium) and only by `data-testid`.
IDs (S2-*, e.g. S2-DOS-4) in docstrings refer to ../LEDGER.md.
Dossiers are built through the API (fast, mock web); the browser reads and acts."""
import json
import re
import time
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

import s2model as m
from conftest import ADA, BASE, FIELDS, PW, new_key, ok_json, parse_ts, assert_status, domain_searches

TO = 10000
A, B, C, D = "ashgrove-labs.test", "brightmoor-energy.test", "cobalt-harbor.test", "driftwood-games.test"
ISO = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d")


def t(page, name):
    return page.get_by_test_id(name)


def tids(page, pattern):
    ids = page.eval_on_selector_all("[data-testid]", "els => els.map(e => e.getAttribute('data-testid'))")
    return [i for i in ids if re.fullmatch(pattern, i)]


def has_link(locator, path):
    """The element is, is in, or contains a link whose path is `path`."""
    return locator.evaluate(
        "(el, p) => [el.closest('a[href]'), ...el.querySelectorAll('a[href]')]"
        ".some(a => a && new URL(a.getAttribute('href'), location.href).pathname === p)", path)


def href_exact(locator, url):
    return locator.evaluate("(el, u) => [el, ...el.querySelectorAll('a')].some(a => a.tagName === 'A' && a.getAttribute('href') === u)", url)


def text(locator):
    return " ".join((locator.text_content() or "").split())


def shows(txt, name, value):
    """Whether the formatted text shows the value (people-first formats are ours to choose)."""
    low = txt.lower()
    if name == "funding_total":
        n = int(value)
        forms = {f"{n:,}", str(n), f"{n / 1e6:g}m", f"{n / 1e6:g} million", f"{n / 1e6:g}\u00a0million",
                 f"{n / 1e3:g}k", f"{n / 1e3:g} thousand"}
        return any(f.lower() in low.replace("$", "").replace("us", "") for f in forms)
    if name == "headcount_range":
        lo = value.split("-")[0].rstrip("+")
        return lo in txt and (value in txt or value.replace("-", "\u2013") in txt or value.replace("-", " to ") in txt
                              or value.replace("-", "\u2014") in txt or value.rstrip("+") in txt)
    return str(value).lower() in low


def api_ready(w, d, key=None):
    w.request(w.ada, d, key)
    return w.wait(w.ada, d, 30)


def build_many(w, *doms):
    return {d: api_ready(w, d) for d in doms}


def goto(page, path, anchor):
    page.goto(path)
    expect(page.locator(", ".join(f"[data-testid='{a}']" for a in anchor.split("|"))).first).to_be_attached(timeout=TO)


def lose_next(page, path_re, method="POST", commit=True):
    """Make the next matching fetch lose its response: with commit, the server receives and
    processes it first. Later requests pass through."""
    st = {"lost": 0}

    def handler(route, request):
        if request.method == method and st["lost"] == 0 and request.resource_type in ("fetch", "xhr"):
            st["lost"] = 1
            if commit:
                route.fetch()
            route.abort("failed")
        else:
            route.continue_()
    page.route(re.compile(path_re), handler)
    return st


def record_posts(page, path_re):
    reqs = []
    page.on("request", lambda r: reqs.append({"key": r.headers.get("idempotency-key"), "body": r.post_data,
                                             "url": r.url}) if r.method == "POST" and re.search(path_re, urlparse(r.url).path) else None)
    return reqs


def same_request(reqs):
    assert len(reqs) >= 2, reqs
    assert reqs[0]["key"] and all(r["key"] == reqs[0]["key"] for r in reqs), \
        f"a retry reuses the same Idempotency-Key: {[r['key'] for r in reqs]}"
    bodies = {json.dumps(json.loads(r["body"])) if r["body"] else "" for r in reqs}
    assert len(bodies) == 1, f"a retry reuses the same body: {bodies}"


def builds_started(w, domain):
    return len(domain_searches(w.mock.log(), domain))


def search_log(w, domain):
    return [(c["seq"], c["provider"], c["depth"], c["query"], c["status"]) for c in w.mock.log()
            if c["method"] == "search"]


# ============================================================================ signup / login
def test_signup_login_logout_through_the_ui(ui):
    """S2-AU-1 S2-AU-3 S2-AU-4 (sign up, see the display name on every screen, log out, log in again)"""
    pg = ui.page(signed=False)
    pg.goto("/signup")
    expect(t(pg, "auth-error")).to_have_count(0)
    t(pg, "signup-email").fill("newuser@example.com")
    t(pg, "signup-password").fill("a long password")
    t(pg, "signup-display-name").fill("Nia Newcomer")
    t(pg, "signup-submit").click()
    expect(t(pg, "current-user")).to_contain_text("Nia Newcomer", timeout=TO)
    for path, anchor in (("/", "research-domain"), ("/contested", "contested-list|empty-contested"),
                         ("/login", "login-submit"), ("/signup", "signup-submit")):
        goto(pg, path, anchor)
        expect(t(pg, "current-user")).to_contain_text("Nia Newcomer")
    goto(pg, "/", "research-domain")
    t(pg, "logout-button").click()
    expect(t(pg, "current-user")).to_have_count(0, timeout=TO)
    pg.goto("/login")
    t(pg, "login-email").fill("newuser@example.com")
    t(pg, "login-password").fill("a long password")
    t(pg, "login-submit").click()
    expect(t(pg, "current-user")).to_contain_text("Nia Newcomer", timeout=TO)
    assert ui.errors == [], ui.errors


def test_auth_errors_are_shown_only_when_there_is_one(ui):
    """S2-AU-2 (duplicate email on signup, wrong password on login: auth-error; absent otherwise)"""
    pg = ui.page(signed=False)
    pg.goto("/signup")
    expect(t(pg, "auth-error")).to_have_count(0)
    t(pg, "signup-email").fill(ADA["email"])
    t(pg, "signup-password").fill("another password")
    t(pg, "signup-display-name").fill("Ada Again")
    t(pg, "signup-submit").click()
    expect(t(pg, "auth-error")).to_be_visible(timeout=TO)
    assert text(t(pg, "auth-error")), "the error has text"
    expect(t(pg, "current-user")).to_have_count(0)
    pg.goto("/login")
    expect(t(pg, "auth-error")).to_have_count(0)
    t(pg, "login-email").fill(ADA["email"])
    t(pg, "login-password").fill("not the password")
    t(pg, "login-submit").click()
    expect(t(pg, "auth-error")).to_be_visible(timeout=TO)
    expect(t(pg, "current-user")).to_have_count(0)
    t(pg, "login-password").fill(PW)
    t(pg, "login-submit").click()
    expect(t(pg, "current-user")).to_be_visible(timeout=TO)
    expect(t(pg, "auth-error")).to_have_count(0)


def test_current_user_is_on_every_screen_when_signed_in(ui):
    """S2-AU-3 (all six routes; the display name of the signed-in user)"""
    w = ui.w
    build_many(w, A)
    pg = ui.page()
    for path, anchor in (("/", "research-domain"), (f"/dossiers/{A}", "dossier-domain"),
                         (f"/dossiers/{A}/evidence", "evidence-legal_name"),
                         ("/contested", "contested-list|empty-contested"), ("/signup", "signup-submit"),
                         ("/login", "login-submit")):
        goto(pg, path, anchor)
        expect(t(pg, "current-user")).to_contain_text("Ada")


# ============================================================================ list screen
def test_list_shows_dossiers_ordered_by_domain_linked_with_their_state(ui):
    """S2-LST-1 S2-LST-2 (items: data-state, domain, legal name when known, link; ordered by domain)"""
    w = ui.w
    bodies = build_many(w, D, A, B)
    pg = ui.page()
    goto(pg, "/", "dossier-list")
    items = tids(pg, r"dossier-item-.+")
    assert items == [f"dossier-item-{d}" for d in sorted(bodies)], items
    inside = pg.eval_on_selector_all("[data-testid='dossier-list'] [data-testid^='dossier-item-']", "els => els.length")
    assert inside == len(items), "the items are inside dossier-list"
    for d, b in bodies.items():
        it = t(pg, f"dossier-item-{d}")
        expect(it).to_have_attribute("data-state", b["state"])
        assert d in text(it)
        assert has_link(it, f"/dossiers/{d}")
    assert "Ashgrove Labs, Inc." in text(t(pg, f"dossier-item-{A}"))
    assert "Brightmoor Energy Ltd" in text(t(pg, f"dossier-item-{B}"))
    assert "null" not in text(t(pg, f"dossier-item-{D}")).lower()
    t(pg, f"dossier-item-{A}").click()
    pg.wait_for_url(f"**/dossiers/{A}")
    expect(t(pg, "dossier-domain")).to_have_text(A)


def test_list_search_filters_like_q(ui):
    """S2-LST-3 (domain or legal name, case-insensitive; empty-dossiers when nothing matches; clearing restores)"""
    w = ui.w
    build_many(w, A, B, D)
    pg = ui.page()
    goto(pg, "/", "dossier-list")
    s = t(pg, "dossier-search")
    s.fill("ASHGROVE")
    expect(t(pg, f"dossier-item-{A}")).to_be_visible(timeout=TO)
    expect(t(pg, f"dossier-item-{B}")).to_have_count(0)
    expect(t(pg, f"dossier-item-{D}")).to_have_count(0)
    s.fill("energy ltd")                                    # a legal name, not a domain
    expect(t(pg, f"dossier-item-{B}")).to_be_visible(timeout=TO)
    expect(t(pg, f"dossier-item-{A}")).to_have_count(0)
    s.fill("no such company")
    expect(t(pg, "empty-dossiers")).to_be_visible(timeout=TO)
    assert text(t(pg, "empty-dossiers"))
    expect(t(pg, f"dossier-item-{A}")).to_have_count(0)
    s.fill("")
    expect(t(pg, "dossier-list")).to_be_visible(timeout=TO)
    expect(t(pg, "empty-dossiers")).to_have_count(0)
    assert len(tids(pg, r"dossier-item-.+")) == 3


def test_empty_list_says_so(ui):
    """S2-LST-3 S2-PQ-9 (no dossier at all: empty-dossiers with text instead of the list)"""
    pg = ui.page()
    goto(pg, "/", "research-domain")
    expect(t(pg, "empty-dossiers")).to_be_visible(timeout=TO)
    assert text(t(pg, "empty-dossiers"))
    assert tids(pg, r"dossier-item-.+") == []


def test_researching_a_domain_opens_its_dossier_and_starts_one_build(ui):
    """S2-LST-4 (WWW., case and a trailing dot are normalised; the dossier screen follows the build)"""
    w = ui.w
    pg = ui.page()
    goto(pg, "/", "research-domain")
    t(pg, "research-domain").fill("  WWW.Cobalt-Harbor.TEST. ")
    t(pg, "research-submit").click()
    pg.wait_for_url(f"**/dossiers/{C}", timeout=TO)
    expect(t(pg, "dossier-domain")).to_have_text(C)
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=20000)
    expect(t(pg, "field-ceo")).to_have_attribute("data-status", "contested")
    assert builds_started(w, C) == 1
    assert ui.errors == [], ui.errors


def test_an_invalid_domain_is_refused_without_a_build(ui):
    """S2-LST-5 S2-PQ-9 (research-error with text, no navigation, no provider call; a valid domain then works)"""
    w = ui.w
    pg = ui.page()
    goto(pg, "/", "research-domain")
    expect(t(pg, "research-error")).to_have_count(0)
    t(pg, "research-domain").fill("https://acme-robotics.test/about")
    t(pg, "research-submit").click()
    expect(t(pg, "research-error")).to_be_visible(timeout=TO)
    assert text(t(pg, "research-error"))
    expect(t(pg, "research-uncertain")).to_have_count(0)
    assert urlparse(pg.url).path == "/"
    assert w.mock.log() == []
    t(pg, "research-domain").fill(D)
    t(pg, "research-submit").click()
    pg.wait_for_url(f"**/dossiers/{D}", timeout=TO)
    expect(t(pg, "research-error")).to_have_count(0)


def test_researching_a_domain_another_client_created_opens_it_and_starts_no_build(ui):
    """S2-LST-6 (the list was read before bob created the dossier: still 200, same dossier, one build in all)"""
    w = ui.w
    pg = ui.page()
    goto(pg, "/", "research-domain")
    expect(t(pg, "empty-dossiers")).to_be_visible(timeout=TO)
    w.request(w.bob, A)                                   # another client researches it after this read
    b0 = w.wait(w.bob, A, 30)
    t(pg, "research-domain").fill(A.upper())
    t(pg, "research-submit").click()
    pg.wait_for_url(f"**/dossiers/{A}", timeout=TO)
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(b0["spent_units"]))
    time.sleep(1)
    assert builds_started(w, A) == 1
    assert w.dossier(w.ada, A)["spent_units"] == b0["spent_units"]


@pytest.mark.parametrize("commit", [True, False], ids=["committed-then-lost", "never-arrived"])
def test_research_with_a_lost_response_is_uncertain_and_retries_with_the_same_key(ui, commit):
    """S2-LST-7 S2-RS-1 S2-RS-2 S2-RS-3 (research-uncertain, not research-error; retry: same key and body; one build)"""
    w = ui.w
    pg = ui.page()
    goto(pg, "/", "research-domain")
    reqs = record_posts(pg, r"^/dossiers$")
    lose_next(pg, r"/dossiers$", "POST", commit=commit)
    t(pg, "research-domain").fill(D)
    t(pg, "research-submit").click()
    expect(t(pg, "research-uncertain")).to_be_visible(timeout=TO)
    assert text(t(pg, "research-uncertain"))
    expect(t(pg, "research-error")).to_have_count(0)
    assert urlparse(pg.url).path == "/"
    t(pg, "research-submit").click()                     # retry: nothing changed
    pg.wait_for_url(f"**/dossiers/{D}", timeout=TO)
    expect(t(pg, "research-uncertain")).to_have_count(0)
    expect(t(pg, "research-error")).to_have_count(0)
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=20000)
    same_request(reqs)
    time.sleep(1)
    assert builds_started(w, D) == 1, "at most one build"


# ============================================================================ dossier screen
def test_dossier_screen_shows_state_spend_fields_and_citations(ui):
    """S2-DOS-1 S2-DOS-2 S2-DOS-3 S2-DOS-4 S2-DOS-5 S2-PQ-7 (every status; citations in API order with excerpt, link, provider)"""
    w = ui.w
    bodies = build_many(w, A, D)
    pg = ui.page()
    for d, b in bodies.items():
        goto(pg, f"/dossiers/{d.upper()}.", "dossier-domain")          # normalised in the route
        expect(t(pg, "dossier-domain")).to_have_text(d)
        expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
        expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(b["spent_units"]))
        ra = t(pg, "dossier-researched-at")
        assert text(ra) and not ISO.search(text(ra)), f"researched_at formatted for people: {text(ra)!r}"
        assert has_link(t(pg, "dossier-evidence-link"), f"/dossiers/{d}/evidence")
        assert tids(pg, r"field-(legal_name|hq_city|ceo|founded_year|headcount_range|funding_total)") \
            == [f"field-{f}" for f in FIELDS], "six fields in the order of stage-1 §4"
        for name in FIELDS:
            f = b["fields"][name]
            expect(t(pg, f"field-{name}")).to_have_attribute("data-status", f["status"])
            if f["value"] is None:
                expect(t(pg, f"field-value-{name}")).to_have_count(0)
            else:
                expect(t(pg, f"field-value-{name}")).to_have_attribute("data-value", str(f["value"]))
                assert shows(text(t(pg, f"field-value-{name}")), name, f["value"]), \
                    (name, f["value"], text(t(pg, f"field-value-{name}")))
            expect(t(pg, f"field-contested-{name}")).to_have_count(1 if f["status"] == "contested" else 0)
            cites = tids(pg, rf"citation-{name}-\d+")
            assert cites == [f"citation-{name}-{i}" for i in range(1, len(f["citations"]) + 1)], (name, cites)
            assert cites == [i for i in tids(pg, r"citation-.+") if i.startswith(f"citation-{name}-")]
            container = t(pg, f"field-citations-{name}")
            for i, c in enumerate(f["citations"], 1):
                el = t(pg, f"citation-{name}-{i}")
                assert o_collapse(c["excerpt"]) in o_collapse(text(el)), (name, i)
                assert href_exact(el, c["url"]), (name, i, c["url"])
                expect(el).to_have_attribute("data-provider", c["provider"])
                assert container.locator(f"[data-testid='citation-{name}-{i}']").count() == 1
                quoted = el.evaluate("(el, ex) => { const q = el.querySelector('blockquote, q'); "
                                     "if (q) return q.textContent.replace(/\\s+/g,' ').includes(ex); "
                                     "return /[\\u201c\\u201d\"]/.test(el.textContent) }", o_collapse(c["excerpt"]))
                assert quoted, "S2-PQ-7: each citation shows its excerpt as quoted text"
    assert ui.errors == [], ui.errors


def o_collapse(s):
    return " ".join(s.split())


def test_every_status_has_its_marker(ui):
    """S2-DOS-4 (driftwood: known, contested and unknown fields side by side)"""
    w = ui.w
    b = api_ready(w, D)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    got = {n: pg.locator(f"[data-testid='field-{n}']").get_attribute("data-status") for n in FIELDS}
    assert got == {"legal_name": "unknown", "hq_city": "unknown", "ceo": "contested",
                   "founded_year": "known", "headcount_range": "known", "funding_total": "known"}, got
    assert tids(pg, r"field-contested-.+") == ["field-contested-ceo"]


def test_unknown_dossier_shows_not_found_instead_of_fields(ui):
    """S2-DOS-8 S2-PQ-9 (dossier-not-found with text; no field is shown; the domain is normalised)"""
    pg = ui.page()
    for path in ("/dossiers/nobody-here.test", "/dossiers/WWW.Nobody-Here.TEST."):
        goto(pg, path, "dossier-not-found|dossier-domain")
        expect(t(pg, "dossier-not-found")).to_be_visible(timeout=TO)
        assert text(t(pg, "dossier-not-found"))
        assert tids(pg, r"field-.+") == []


def test_failed_dossier_shows_failed_and_no_researched_at(ui):
    """S2-DOS-2 S2-DOS-6 (a dossier whose build failed: state failed, researched_at absent, six unknown fields)"""
    w = ui.w
    w.mock.break_all()
    w.request(w.ada, A)
    assert w.wait(w.ada, A, 30)["state"] == "failed"
    pg = ui.page()
    goto(pg, f"/dossiers/{A}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("failed", timeout=TO)
    expect(t(pg, "dossier-researched-at")).to_have_count(0)
    for n in FIELDS:
        expect(t(pg, f"field-{n}")).to_have_attribute("data-status", "unknown")
        expect(t(pg, f"field-value-{n}")).to_have_count(0)
        expect(t(pg, f"field-contested-{n}")).to_have_count(0)
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", "0")


def test_dossier_links_to_its_evidence(ui):
    """S2-DOS-7 (dossier-evidence-link goes to /dossiers/{domain}/evidence)"""
    api_ready(ui.w, A)
    pg = ui.page()
    goto(pg, f"/dossiers/{A}", "dossier-domain")
    t(pg, "dossier-evidence-link").click()
    pg.wait_for_url(f"**/dossiers/{A}/evidence", timeout=TO)
    expect(t(pg, "evidence-ceo")).to_be_visible(timeout=TO)


# ============================================================================ evidence screen
def test_evidence_lists_every_candidate_in_api_order_with_its_attributes(ui):
    """S2-EV-1 S2-EV-2 S2-EV-3 S2-PQ-8 (six containers; candidate-{f}-{n}: data-*; text has value and excerpt)"""
    w = ui.w
    b = api_ready(w, A)
    pg = ui.page()
    goto(pg, f"/dossiers/{A}/evidence", "evidence-legal_name")
    assert sorted(tids(pg, r"evidence-(legal_name|hq_city|ceo|founded_year|headcount_range|funding_total)")) \
        == sorted(f"evidence-{f}" for f in FIELDS)
    for name in FIELDS:
        cands = b["fields"][name]["candidates"]
        ids = tids(pg, rf"candidate-{name}-\d+")
        assert ids == [f"candidate-{name}-{i}" for i in range(1, len(cands) + 1)], (name, ids)
        for i, c in enumerate(cands, 1):
            el = t(pg, f"candidate-{name}-{i}")
            expect(el).to_have_attribute("data-value", str(c["value"]))
            expect(el).to_have_attribute("data-provider", c["provider"])
            expect(el).to_have_attribute("data-kind", c["kind"])
            expect(el).to_have_attribute("data-url", c["url"])
            expect(el).to_have_attribute("data-selected", "true" if c["selected"] else "false")
            got = el.get_attribute("data-published-at")
            if c["published_at"] is None:
                assert got == "", (name, i, got)
            else:
                assert m.parse_rfc3339(got) == m.parse_rfc3339(c["published_at"]), (name, i, got)
            tx = text(el)
            assert o_collapse(c["excerpt"]) in tx and shows(tx, name, c["value"]), (name, i, tx)
            assert not ISO.search(tx), f"timestamps are formatted for people: {tx!r}"
            assert not re.search(r"\bnull\b|\bundefined\b|\[object", tx), tx
        expect(t(pg, f"evidence-empty-{name}")).to_have_count(0)
    assert ui.errors == [], ui.errors


def test_evidence_says_so_for_a_field_without_candidates(ui):
    """S2-EV-4 S2-PQ-9 (driftwood: no legal name or city anywhere)"""
    api_ready(ui.w, D)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}/evidence", "evidence-legal_name")
    for name in ("legal_name", "hq_city"):
        expect(t(pg, f"evidence-empty-{name}")).to_be_visible(timeout=TO)
        assert text(t(pg, f"evidence-empty-{name}"))
        assert tids(pg, rf"candidate-{name}-\d+") == []
    for name in ("ceo", "founded_year", "headcount_range", "funding_total"):
        expect(t(pg, f"evidence-empty-{name}")).to_have_count(0)
        assert tids(pg, rf"candidate-{name}-\d+")


def test_evidence_route_normalises_its_domain_and_handles_an_unknown_one(ui):
    """S2-EV-5 (WWW./case in the route; an unknown dossier shows a message, not a crash)"""
    api_ready(ui.w, A)
    pg = ui.page()
    goto(pg, f"/dossiers/WWW.{A.upper()}/evidence", "evidence-legal_name")
    assert tids(pg, r"candidate-ceo-\d+")
    pg.goto("/dossiers/nobody-here.test/evidence")
    pg.wait_for_load_state()
    assert text(pg.locator("body")).strip()
    assert tids(pg, r"candidate-.+") == []


# ============================================================================ contested screen
def test_contested_lists_every_contested_field_by_domain_then_field_order(ui):
    """S2-CT-1 S2-CT-2 (ashgrove has six, driftwood one, brightmoor none)"""
    w = ui.w
    bodies = build_many(w, D, B, A)
    pg = ui.page()
    goto(pg, "/contested", "contested-list")
    want = [f"contested-item-{d}-{f}" for d in sorted(bodies) for f in FIELDS
            if bodies[d]["fields"][f]["status"] == "contested"]
    assert len(want) == 7
    assert tids(pg, r"contested-item-.+") == want
    inside = pg.eval_on_selector_all("[data-testid='contested-list'] [data-testid^='contested-item-']", "els => els.length")
    assert inside == len(want), "the items are inside contested-list"
    for tid in want:
        d, f = re.fullmatch(r"contested-item-(.+\.test)-(\w+)", tid).groups()
        fld = bodies[d]["fields"][f]
        el = t(pg, tid)
        expect(el).to_have_attribute("data-value", str(fld["value"]))
        tx = text(el)
        assert d in tx and (f in tx or f.replace("_", " ") in tx.lower()), tx
        for v in {c["value"] for c in fld["candidates"]}:
            assert shows(tx, f, v), (tid, v, tx)
        assert has_link(el, f"/dossiers/{d}/evidence"), tid
    expect(t(pg, "empty-contested")).to_have_count(0)


def test_contested_says_so_when_nothing_is_contested(ui):
    """S2-CT-3 S2-PQ-9 (only a clean dossier: empty-contested instead of the list)"""
    api_ready(ui.w, B)
    pg = ui.page()
    goto(pg, "/contested", "empty-contested|contested-list")
    expect(t(pg, "empty-contested")).to_be_visible(timeout=TO)
    assert text(t(pg, "empty-contested"))
    assert tids(pg, r"contested-item-.+") == []


# ============================================================================ building and polling
def slow_providers(w, seconds=4):
    for p in ("nimble", "tavily"):
        w.mock.fault(p, ["search"], "delay", seconds)


def test_a_building_dossier_is_read_again_every_two_seconds_until_it_ends(ui):
    """S2-DOS-9 (state building, then ready with the new fields, without a manual reload)"""
    w = ui.w
    slow_providers(w, 4)
    w.request(w.ada, D)
    pg = ui.page()
    reads = []
    pg.on("request", lambda r: reads.append(time.time()) if urlparse(r.url).path == f"/dossiers/{D}" and r.method == "GET" else None)
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("building", timeout=TO)
    for n in FIELDS:
        expect(t(pg, f"field-{n}")).to_have_attribute("data-status", "unknown")
    t0 = time.time()
    while w.dossier(w.ada, D)["state"] == "building":
        assert time.time() - t0 < 30
        time.sleep(0.2)
    t_ready = time.time()
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=3500)     # within the 2 s cadence (+ margin)
    expect(t(pg, "field-founded_year")).to_have_attribute("data-status", "known")
    expect(t(pg, "field-value-founded_year")).to_have_attribute("data-value", "2012")
    gaps = [b - a for a, b in zip(reads, reads[1:]) if b < t_ready]
    assert len(reads) >= 3, f"the building dossier was read again: {len(reads)} reads"
    assert max(gaps, default=0) <= 2.6, f"at least every 2 seconds: gaps {[round(g, 1) for g in gaps]}"
    spent = w.dossier(w.ada, D)["spent_units"]
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(spent))


def hold_reads(page, domain, skip=0):
    """Hold back the response of the next fetch/xhr GET of /dossiers/{domain} (after `skip` reads
    went through): the server answers now, the page receives it when release() is called.
    st["reads"] counts every such read the page makes."""
    st = {"armed": True, "held": [], "reads": 0, "skip": skip}

    def handler(route, request):
        if request.method == "GET" and request.resource_type in ("fetch", "xhr") \
                and urlparse(request.url).path == f"/dossiers/{domain}":
            st["reads"] += 1
            if st["armed"] and st["reads"] > st["skip"]:
                st["armed"] = False
                st["held"].append((route, route.fetch()))
                return
        route.continue_()
    page.route(re.compile(rf"/dossiers/{re.escape(domain)}$"), handler)

    def release():
        for route, resp in st["held"]:
            route.fulfill(response=resp)
        n = len(st["held"])
        st["held"].clear()
        return n
    st["release"] = release
    return st


def test_a_delayed_earlier_read_never_overwrites_a_later_one_after_reload(ui):
    """S2-RW-1 S2-RW-3 (reload twice, answers out of order; reload starts no build and makes no provider call)"""
    w = ui.w
    b0 = api_ready(w, D)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
    st = hold_reads(pg, D)
    t(pg, "dossier-reload").click()
    for _ in range(30):
        if st["held"]:
            break
        pg.wait_for_timeout(100)
    # another client moves the dossier on while the first read is in flight
    r = w.refresh(w.bob, D)[0]
    assert r["spent_units"] > b0["spent_units"]
    n_calls = len(w.mock.log())
    if st["held"] and not t(pg, "dossier-reload").is_disabled():
        t(pg, "dossier-reload").click()
        expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(r["spent_units"]), timeout=TO)
        st["release"]()                                  # the older answer arrives last
        pg.wait_for_timeout(1200)
        expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(r["spent_units"]))
    else:
        st["release"]()
        t(pg, "dossier-reload").click()
        expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(r["spent_units"]), timeout=TO)
    time.sleep(0.5)
    assert len(w.mock.log()) == n_calls, "reload reads the dossier again, no provider call"
    assert builds_started(w, D) == 2


def test_a_delayed_read_while_building_never_overwrites_the_final_state(ui):
    """S2-RW-2 (a read made while building is answered late, after the end of the build was shown)"""
    w = ui.w
    api_ready(w, D)
    slow_providers(w, 5)
    assert_status(w.ada.post(f"/dossiers/{D}/refresh", key=new_key()), 202)
    pg = ui.page(signed=True)
    st = hold_reads(pg, D, skip=1)                       # the first read (page load) passes, the next is held
    pg.goto(f"/dossiers/{D}")
    expect(t(pg, "dossier-state")).to_have_text("building", timeout=TO)
    for _ in range(40):
        if st["held"]:
            break
        pg.wait_for_timeout(100)
    # a UI that reads one at a time cannot issue another read while this one is pending: then release it
    reads_before = st["reads"]
    pg.wait_for_timeout(2600)
    concurrent = st["reads"] > reads_before
    if not concurrent:
        st["release"]()
    t0 = time.time()
    while w.dossier(w.ada, D)["state"] == "building":
        assert time.time() - t0 < 40
        time.sleep(0.2)
    final = w.dossier(w.ada, D)
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=6000)
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(final["spent_units"]))
    st["release"]()
    pg.wait_for_timeout(1200)
    expect(t(pg, "dossier-state")).to_have_text("ready")
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(final["spent_units"]))


# ============================================================================ refresh
def test_refresh_follows_the_build_and_shows_the_new_data_without_reload(ui):
    """S2-RF-1 S2-RF-5 (POST refresh with an Idempotency-Key; building, then ready with new spend)"""
    w = ui.w
    b0 = api_ready(w, D)
    slow_providers(w, 2)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
    reqs = record_posts(pg, rf"^/dossiers/{re.escape(D)}/refresh$")
    t(pg, "dossier-refresh").click()
    expect(t(pg, "dossier-state")).to_have_text("building", timeout=TO)
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=30000)
    assert len(reqs) == 1 and reqs[0]["key"], reqs
    after = w.dossier(w.ada, D)
    assert after["spent_units"] > b0["spent_units"]
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(after["spent_units"]))
    expect(t(pg, "refresh-error")).to_have_count(0)
    expect(t(pg, "refresh-uncertain")).to_have_count(0)
    assert builds_started(w, D) == 2


def test_a_refused_refresh_shows_refresh_error(ui):
    """S2-RF-2 (a 4xx from the server: refresh-error with text, not refresh-uncertain)"""
    api_ready(ui.w, D)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
    expect(t(pg, "refresh-error")).to_have_count(0)
    pg.route(re.compile(r"/refresh$"), lambda route, req: route.fulfill(
        status=422, content_type="application/json; charset=utf-8",
        body=json.dumps({"error": {"code": "validation_failed", "message": "refused"}})))
    t(pg, "dossier-refresh").click()
    expect(t(pg, "refresh-error")).to_be_visible(timeout=TO)
    assert text(t(pg, "refresh-error"))
    expect(t(pg, "refresh-uncertain")).to_have_count(0)


@pytest.mark.parametrize("commit", [True, False], ids=["committed-then-lost", "never-arrived"])
def test_refresh_with_a_lost_response_is_uncertain_and_retries_with_the_same_key(ui, commit):
    """S2-RF-3 S2-RF-4 S2-RF-6 (refresh-uncertain, then the same key and body; at most one build; the screen follows it)"""
    w = ui.w
    api_ready(w, D)
    slow_providers(w, 2)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
    reqs = record_posts(pg, rf"^/dossiers/{re.escape(D)}/refresh$")
    lose_next(pg, r"/refresh$", "POST", commit=commit)
    t(pg, "dossier-refresh").click()
    expect(t(pg, "refresh-uncertain")).to_be_visible(timeout=TO)
    assert text(t(pg, "refresh-uncertain"))
    expect(t(pg, "refresh-error")).to_have_count(0)
    t(pg, "dossier-refresh").click()
    expect(t(pg, "refresh-uncertain")).to_have_count(0, timeout=TO)
    expect(t(pg, "refresh-error")).to_have_count(0)
    time.sleep(0.5)
    w.wait(w.ada, D, 30)
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=30000)
    same_request(reqs)
    time.sleep(1)
    assert builds_started(w, D) == 2, ("the first build plus exactly one refresh", search_log(w, D))
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(w.dossier(w.ada, D)["spent_units"]))


def test_refreshing_while_another_client_refreshes_follows_the_running_build(ui):
    """S2-RF-7 (the build another client started is the one the screen follows; 202, no error, one build)"""
    w = ui.w
    api_ready(w, D)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
    slow_providers(w, 3)
    assert_status(w.bob.post(f"/dossiers/{D}/refresh", key=new_key()), 202)
    t(pg, "dossier-refresh").click()
    expect(t(pg, "dossier-state")).to_have_text("building", timeout=TO)
    expect(t(pg, "refresh-error")).to_have_count(0)
    expect(t(pg, "refresh-uncertain")).to_have_count(0)
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=30000)
    time.sleep(1)
    assert builds_started(w, D) == 2, search_log(w, D)
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(w.dossier(w.ada, D)["spent_units"]))


# ============================================================================ upgrade
def export_import(w):
    exp = w.anon.get("/_test/export")
    assert exp.status_code == 200
    assert_status(w.anon.post("/_test/import", body=exp.json(), timeout=10), 204)


def test_a_signed_in_browser_stays_signed_in_across_an_export_import(ui):
    """S2-UP-11 (no page reload: the next read works, same user, same dossier)"""
    w = ui.w
    b0 = api_ready(w, A)
    pg = ui.page()
    goto(pg, f"/dossiers/{A}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
    export_import(w)
    t(pg, "dossier-reload").click()
    expect(t(pg, "dossier-domain")).to_have_text(A)
    expect(t(pg, "current-user")).to_contain_text("Ada")
    expect(t(pg, "dossier-spent")).to_have_attribute("data-units", str(b0["spent_units"]))
    expect(t(pg, "field-ceo")).to_have_attribute("data-status", "contested")
    assert urlparse(pg.url).path == f"/dossiers/{A}"
    pg.goto("/")
    expect(t(pg, f"dossier-item-{A}")).to_be_visible(timeout=TO)
    expect(t(pg, "current-user")).to_be_visible()
    pg.goto(f"/dossiers/{A}/evidence")
    expect(t(pg, "candidate-ceo-1")).to_be_visible(timeout=TO)


@pytest.mark.parametrize("what", ["refresh", "research"])
def test_a_request_lost_before_an_export_is_recovered_after_the_import(ui, what):
    """S2-UP-12 (response lost, export, import, retry with the same key and body: the original response, no new build, dossier shown)"""
    w = ui.w
    pg = ui.page()
    if what == "refresh":
        api_ready(w, D)
        goto(pg, f"/dossiers/{D}", "dossier-domain")
        expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
        reqs = record_posts(pg, rf"^/dossiers/{re.escape(D)}/refresh$")
        lose_next(pg, r"/refresh$")
        t(pg, "dossier-refresh").click()
        expect(t(pg, "refresh-uncertain")).to_be_visible(timeout=TO)
        w.wait(w.ada, D, 30)
        export_import(w)
        t(pg, "dossier-refresh").click()
        expect(t(pg, "refresh-uncertain")).to_have_count(0, timeout=TO)
        expect(t(pg, "refresh-error")).to_have_count(0)
        expect(t(pg, "dossier-state")).to_have_text("ready", timeout=20000)
        expect(t(pg, "dossier-domain")).to_have_text(D)
        want = 2
    else:
        goto(pg, "/", "research-domain")
        reqs = record_posts(pg, r"^/dossiers$")
        lose_next(pg, r"/dossiers$")
        t(pg, "research-domain").fill(D)
        t(pg, "research-submit").click()
        expect(t(pg, "research-uncertain")).to_be_visible(timeout=TO)
        w.wait(w.ada, D, 30)
        export_import(w)
        t(pg, "research-submit").click()
        pg.wait_for_url(f"**/dossiers/{D}", timeout=TO)
        expect(t(pg, "dossier-state")).to_have_text("ready", timeout=20000)
        expect(t(pg, "research-uncertain")).to_have_count(0)
        want = 1
    same_request(reqs)
    time.sleep(1)
    assert builds_started(w, D) == want
    expect(t(pg, "current-user")).to_be_visible()


# ============================================================================ product quality
ROUTES = [("/", "research-domain"), (f"/dossiers/{A}", "dossier-domain"),
          (f"/dossiers/{A}/evidence", "evidence-legal_name"), ("/contested", "contested-list|empty-contested"),
          ("/signup", "signup-submit"), ("/login", "login-submit")]


@pytest.mark.parametrize("width,height", [(375, 812), (1280, 800)], ids=["375px", "desktop"])
def test_no_horizontal_page_scroll(ui, width, height):
    """S2-PQ-1 (every route, long excerpts and a six-field dossier included)"""
    build_many(ui.w, A, D)
    pg = ui.page(width, height)
    for path, anchor in ROUTES + [(f"/dossiers/{D}", "dossier-domain"), (f"/dossiers/{D}/evidence", "evidence-legal_name")]:
        goto(pg, path, anchor)
        pg.wait_for_timeout(300)
        over = pg.evaluate("() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, "
                           "bw: document.body.scrollWidth})")
        assert max(over["sw"], over["bw"]) <= over["cw"] + 1, f"{path} at {width}px scrolls horizontally: {over}"


def test_primary_actions_are_reachable_on_a_phone(ui):
    """S2-PQ-1 S2-PQ-10 (research and refresh are visible, tappable buttons at 375px)"""
    build_many(ui.w, A)
    pg = ui.page(375, 812)
    goto(pg, "/", "research-submit")
    goto(pg, f"/dossiers/{A}", "dossier-refresh")
    for tid in ("dossier-refresh", "dossier-reload"):
        box = t(pg, tid).bounding_box()
        assert box and box["height"] >= 32 and box["width"] >= 44, (tid, box)
        assert 0 <= box["x"] and box["x"] + box["width"] <= 376
    goto(pg, "/", "research-submit")
    box = t(pg, "research-submit").bounding_box()
    assert box["height"] >= 32 and box["width"] >= 44 and box["x"] + box["width"] <= 376


def test_inputs_have_visible_labels(ui):
    """S2-PQ-2 (research, search, signup and login inputs: a visible <label>, not only a placeholder)"""
    build_many(ui.w, A)
    pg = ui.page(signed=False)
    js = """() => Array.from(document.querySelectorAll('input, textarea, select')).filter(e => e.type !== 'hidden'
        && e.getClientRects().length).map(e => {
          const labels = Array.from(e.labels || []).filter(l => l.getClientRects().length && l.textContent.trim());
          return {id: e.getAttribute('data-testid'), n: labels.length}; })"""
    for path in ("/login", "/signup"):
        pg.goto(path)
        pg.wait_for_load_state()
        got = pg.evaluate(js)
        assert got and all(g["n"] >= 1 for g in got), (path, got)
    ui.sign_in(pg)
    goto(pg, "/", "research-domain")
    got = pg.evaluate(js)
    assert {g["id"] for g in got} >= {"research-domain", "dossier-search"} and all(g["n"] >= 1 for g in got), got


def test_keyboard_focus_is_apparent(ui):
    """S2-PQ-3 (inputs, buttons and links show a focus indicator when focused with the keyboard)"""
    build_many(ui.w, A)
    pg = ui.page(signed=False)
    snap = """el => { const s = getComputedStyle(el); return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow,
        s.borderTopColor, s.borderTopWidth, s.backgroundColor, s.color, s.textDecorationLine].join('|') }"""
    def check(pg, tid):
        el = t(pg, tid)
        el.evaluate("el => el.blur()")
        before = el.evaluate(snap)
        pg.keyboard.press("Tab")           # keyboard modality, so :focus-visible applies
        el.focus()
        after = el.evaluate(snap)
        s = el.evaluate("el => { const s = getComputedStyle(el); return {os: s.outlineStyle, ow: parseFloat(s.outlineWidth), sh: s.boxShadow} }")
        assert after != before, f"{tid}: focusing changes nothing visible"
        assert (s["os"] not in ("none", "hidden") and s["ow"] > 0) or s["sh"] != "none" or after.split("|")[4:6] != before.split("|")[4:6] \
            or after.split("|")[6] != before.split("|")[6], f"{tid}: no focus indicator {after}"
        el.blur()
    pg.goto("/login")
    for tid in ("login-email", "login-password", "login-submit"):
        check(pg, tid)
    ui.sign_in(pg)
    goto(pg, "/", "research-domain")
    for tid in ("research-domain", "research-submit", "dossier-search"):
        check(pg, tid)
    goto(pg, f"/dossiers/{A}", "dossier-refresh")
    for tid in ("dossier-refresh", "dossier-reload", "dossier-evidence-link"):
        check(pg, tid)


CONTRAST_JS = """() => {
  const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  const blend = (fg, bg) => ({r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1});
  const bgOf = el => { const chain = [];
    for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.backgroundImage !== 'none') return null;
      const c = parse(cs.backgroundColor); if (c && c.a > 0) { chain.push(c); if (c.a >= 1) break; } }
    let base = {r: 255, g: 255, b: 255, a: 1}; for (const c of chain.reverse()) base = blend(c, base); return base; };
  const bad = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (!el.getClientRects().length) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || el.disabled) continue;
    const own = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());
    const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) && el.type !== 'hidden' && el.type !== 'checkbox' && el.type !== 'radio';
    if (!own && !(isInput && (el.value || el.type === 'submit'))) continue;
    const bg = bgOf(el); if (!bg) continue;
    let fg = parse(cs.color); if (!fg) continue;
    let op = 1; for (let e = el; e; e = e.parentElement) op *= parseFloat(getComputedStyle(e).opacity);
    fg = blend({r: fg.r, g: fg.g, b: fg.b, a: fg.a * op}, bg);
    const l1 = lum(fg), l2 = lum(bg); const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const fs = parseFloat(cs.fontSize), fw = parseInt(cs.fontWeight) || 400;
    const need = (fs >= 24 || (fs >= 18.66 && fw >= 700)) ? 3 : 4.5;
    if (ratio < need) bad.push({id: el.getAttribute('data-testid') || el.tagName, text: (el.textContent || el.value || '').trim().slice(0, 30), ratio: Math.round(ratio * 100) / 100, need});
  }
  return bad; }"""


def test_text_and_controls_have_sufficient_contrast(ui):
    """S2-PQ-4 (every visible text and control on every route: WCAG AA ratio against its background)"""
    w = ui.w
    build_many(w, A, D)
    pg = ui.page()
    for path, anchor in ROUTES + [(f"/dossiers/{D}", "dossier-domain"), (f"/dossiers/{D}/evidence", "evidence-legal_name")]:
        goto(pg, path, anchor)
        pg.wait_for_timeout(300)
        bad = pg.evaluate(CONTRAST_JS)
        assert not bad, f"{path}: {bad[:6]}"


SIG_JS = """el => { const sig = e => { const s = getComputedStyle(e); return [s.color, s.backgroundColor, s.borderTopColor,
    s.borderLeftColor, s.borderTopWidth, s.outlineColor, s.fontWeight, s.textDecorationLine].join('|') };
  return [el, ...el.querySelectorAll('*')].map(sig) }"""


def test_known_contested_and_unknown_fields_look_different(ui):
    """S2-PQ-5 (driftwood: one field of each status; their computed colours/borders/weights differ pairwise)"""
    api_ready(ui.w, D)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    sig = {s: tuple(sorted(set(t(pg, f"field-{n}").evaluate(SIG_JS))))
           for s, n in (("unknown", "legal_name"), ("contested", "ceo"), ("known", "founded_year"))}
    assert len({sig["unknown"], sig["contested"], sig["known"]}) == 3, \
        "known, contested and unknown fields must not share one visual treatment"


def test_building_failed_and_ready_look_different(ui):
    """S2-PQ-5 (dossier-state: building, failed, ready are distinct as well as worded)"""
    w = ui.w
    api_ready(w, D)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    expect(t(pg, "dossier-state")).to_have_text("ready", timeout=TO)
    sig = {"ready": tuple(t(pg, "dossier-state").evaluate(SIG_JS))}
    slow_providers(w, 6)
    assert_status(w.ada.post(f"/dossiers/{D}/refresh", key=new_key()), 202)
    pg.reload()
    expect(t(pg, "dossier-state")).to_have_text("building", timeout=TO)
    sig["building"] = tuple(t(pg, "dossier-state").evaluate(SIG_JS))
    w.wait(w.ada, D, 40)
    w.mock.clear()
    w.mock.break_all()
    w.request(w.ada, A)
    assert w.wait(w.ada, A, 30)["state"] == "failed"
    pg.goto(f"/dossiers/{A}")
    expect(t(pg, "dossier-state")).to_have_text("failed", timeout=TO)
    sig["failed"] = tuple(t(pg, "dossier-state").evaluate(SIG_JS))
    assert len(set(sig.values())) == 3, sig


def test_refused_and_uncertain_look_different(ui):
    """S2-PQ-5 (research-error vs research-uncertain: distinct treatment)"""
    pg = ui.page()
    goto(pg, "/", "research-domain")
    t(pg, "research-domain").fill("not a domain")
    t(pg, "research-submit").click()
    expect(t(pg, "research-error")).to_be_visible(timeout=TO)
    err_sig = tuple(t(pg, "research-error").evaluate(SIG_JS))
    lose_next(pg, r"/dossiers$", "POST", commit=False)
    t(pg, "research-domain").fill(D)
    t(pg, "research-submit").click()
    expect(t(pg, "research-uncertain")).to_be_visible(timeout=TO)
    unc_sig = tuple(t(pg, "research-uncertain").evaluate(SIG_JS))
    assert err_sig != unc_sig, "a refusal and an unknown outcome must not look the same"
    expect(t(pg, "research-error")).to_have_count(0)


def test_navigation_is_consistent_across_the_routes(ui):
    """S2-PQ-6 (every signed-in route has navigation with links to the list and to /contested; same links on all)"""
    build_many(ui.w, A)
    pg = ui.page()
    sets = {}
    for path, anchor in ROUTES:
        goto(pg, path, anchor)
        hrefs = pg.evaluate("""() => { const n = document.querySelector('nav, header, [role=navigation]');
            return n ? Array.from(n.querySelectorAll('a[href]')).map(a => new URL(a.getAttribute('href'), location.href).pathname) : null }""")
        assert hrefs is not None, f"{path}: no <nav>/<header> navigation"
        assert "/" in hrefs and "/contested" in hrefs, (path, hrefs)
        sets[path] = frozenset(hrefs)
    assert len(set(sets.values())) == 1, f"navigation differs between screens: {sets}"
    goto(pg, "/", "research-domain")
    pg.locator("nav a[href='/contested'], header a[href='/contested']").first.click()
    pg.wait_for_url("**/contested", timeout=TO)


def test_screens_have_no_script_errors(ui):
    """S2-PQ-11 (visiting every route and acting on the list/dossier raises no page error)"""
    build_many(ui.w, A, D)
    pg = ui.page()
    for path, anchor in ROUTES:
        goto(pg, path, anchor)
    pg.goto("/")
    t(pg, "dossier-search").fill("ash")
    t(pg, "dossier-search").fill("")
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    t(pg, "dossier-reload").click()
    pg.wait_for_timeout(500)
    assert ui.errors == [], ui.errors


def test_values_are_formatted_for_people(ui):
    """S2-PQ-8 (years plain, money and headcount readable, timestamps not raw RFC 3339, no raw nulls)"""
    api_ready(ui.w, D)
    pg = ui.page()
    goto(pg, f"/dossiers/{D}", "dossier-domain")
    fy = text(t(pg, "field-value-founded_year"))
    assert "2012" in fy and "2,012" not in fy, fy
    money = text(t(pg, "field-value-funding_total"))
    assert money != "12000000" and re.search(r"\$|USD|million|M\b|12,000,000", money), money
    hc = text(t(pg, "field-value-headcount_range"))
    assert "51" in hc and "200" in hc, hc
    body = text(pg.locator("body"))
    assert not ISO.search(body), "no raw RFC 3339 timestamps on the screen"
    assert not re.search(r"\bnull\b|\bundefined\b|\[object|NaN", body), body[:300]
