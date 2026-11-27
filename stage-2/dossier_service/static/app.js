/* Dossier browser UI. One shell, rendered by route; every read goes through the JSON API. */
(() => {
  "use strict";

  const FIELDS = [
    ["legal_name", "Legal name"],
    ["hq_city", "Headquarters"],
    ["ceo", "Chief executive"],
    ["founded_year", "Founded"],
    ["headcount_range", "Headcount"],
    ["funding_total", "Total funding"],
  ];
  const FIELD_LABELS = Object.fromEntries(FIELDS);
  const KIND_LABELS = { own: "Company site", filing: "Filing", news: "News", aggregator: "Aggregator" };
  const PROVIDER_LABELS = { nimble: "Nimble", tavily: "Tavily", kernel: "Kernel", browserbase: "Browserbase" };
  const TOKEN_KEY = "dossier.token";
  const USER_KEY = "dossier.user";
  const REQUEST_TIMEOUT_MS = 8000;
  const POLL_MS = 1000;
  const FAILED_TEXT = "Not researched: the build failed";
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // ------------------------------------------------------------------ session

  const store = {
    get(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } },
    set(key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* storage unavailable */ } },
    remove(key) { try { window.localStorage.removeItem(key); } catch (e) { /* storage unavailable */ } },
  };
  const session = {
    token: () => store.get(TOKEN_KEY),
    name: () => store.get(USER_KEY),
    save(reply) { store.set(TOKEN_KEY, reply.token); store.set(USER_KEY, reply.display_name); },
    clear() { store.remove(TOKEN_KEY); store.remove(USER_KEY); },
  };

  // ------------------------------------------------------------------ requests

  class NetworkError extends Error {}
  class Redirecting extends Error {}

  async function api(method, path, { body, key } = {}) {
    const headers = { Accept: "application/json" };
    const token = session.token();
    if (token) headers.Authorization = "Bearer " + token;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (key) headers["Idempotency-Key"] = key;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let response;
    let data = null;
    try {
      response = await fetch(path, {
        method, headers, signal: controller.signal,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      data = await response.json().catch(() => null);
    } catch (error) {
      throw new NetworkError(String(error));
    } finally {
      clearTimeout(timer);
    }
    if (response.status === 401 && !path.startsWith("/auth/")) {
      session.clear();
      window.location.assign("/login");
      throw new Redirecting();
    }
    return { status: response.status, data };
  }

  function errorText(res, fallback) {
    return (res.data && res.data.error && res.data.error.message) || fallback;
  }

  function newKey() {
    const bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes);
    else bytes.forEach((_, i) => { bytes[i] = Math.floor(Math.random() * 256); });
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // ------------------------------------------------------------------ small helpers

  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [name, value] of Object.entries(props || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (name === "class") el.className = value;
      else if (name === "testid") el.setAttribute("data-testid", value);
      else if (name.startsWith("on")) el.addEventListener(name.slice(2), value);
      else el.setAttribute(name, value === true ? "" : String(value));
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  function normaliseDomain(raw) {
    let domain = raw.trim().replace(/[A-Z]/g, (c) => c.toLowerCase());
    if (domain.endsWith(".")) domain = domain.slice(0, -1);
    if (domain.startsWith("www.")) domain = domain.slice(4);
    return domain;
  }

  function formatValue(field, value) {
    if (value === null || value === undefined) return "";
    if (field === "funding_total" && typeof value === "number") return "$" + value.toLocaleString("en-US");
    if (field === "headcount_range") return value + " employees";
    return String(value);
  }

  function formatMoment(iso, dateOnlyAtMidnight) {
    const m = /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?([Zz]|[+-]\d{2}:\d{2})$/.exec(iso || "");
    if (!m) return iso || "";
    const date = `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
    if (dateOnlyAtMidnight && m[4] === "00" && m[5] === "00" && (!m[6] || m[6] === "00")) return date;
    const zone = /^[Zz]$|^[+-]00:00$/.test(m[7]) ? "UTC" : "UTC" + m[7];
    return `${date}, ${m[4]}:${m[5]} ${zone}`;
  }

  function formatUnits(units) {
    return `${units.toLocaleString("en-US")} ${units === 1 ? "unit" : "units"}`;
  }

  function sourceLabel(url) {
    try {
      const parsed = new URL(url);
      const path = parsed.pathname === "/" ? "" : parsed.pathname;
      return parsed.host + path;
    } catch (e) {
      return url;
    }
  }

  function dataValue(value) {
    return String(value);
  }

  function distinctValues(candidates) {
    const seen = new Set();
    const out = [];
    for (const candidate of candidates) {
      const key = typeof candidate.value + ":" + String(candidate.value).trim();
      if (!seen.has(key)) { seen.add(key); out.push(candidate.value); }
    }
    return out;
  }

  function statePill(state, testid) {
    return h("span", { class: "pill " + state, testid }, state);
  }

  function kindChip(kind) {
    return h("span", { class: "chip kind-" + (kind || "imported"), title: kind ? "Page kind: " + kind : "Imported from an earlier export" },
      kind ? KIND_LABELS[kind] || kind : "Imported");
  }

  function providerChip(provider) {
    return h("span", { class: "chip", title: "Provider that served the text" }, PROVIDER_LABELS[provider] || provider);
  }

  function publishedText(candidate) {
    return candidate.published_at ? "Published " + formatMoment(candidate.published_at, true) : "Publication date unknown";
  }

  function notice(kind, text, testid) {
    return h("div", { class: "notice " + kind, role: kind === "error" ? "alert" : "status", testid }, h("span", {}, text));
  }

  function setBusy(button, busy, idleLabel, busyLabel) {
    button.disabled = busy;
    button.classList.toggle("busy", busy);
    button.textContent = busy ? busyLabel : idleLabel;
  }

  async function mapLimit(items, limit, work) {
    const results = new Array(items.length);
    let next = 0;
    const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) {
        const index = next++;
        results[index] = await work(items[index]);
      }
    });
    await Promise.all(runners);
    return results;
  }

  async function listDossiers(query) {
    const out = [];
    for (let offset = 0; ; offset += 200) {
      const res = await api("GET", `/dossiers?limit=200&offset=${offset}` + (query ? "&q=" + encodeURIComponent(query) : ""));
      if (res.status !== 200) throw new Error(errorText(res, "The dossier list could not be read."));
      out.push(...res.data.dossiers);
      if (!res.data.has_more) return out;
    }
  }

  // ------------------------------------------------------------------ layout

  function layout(active) {
    const app = document.getElementById("app");
    app.replaceChildren();
    const user = session.token() ? session.name() || "Signed in" : null;
    const mark = h("span", { class: "brand-mark", "aria-hidden": "true" });
    mark.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="#fff" stroke-width="1.6"><path d="M3.5 1.8h6l3 3v9.4h-9z"/><path d="M6 8h4M6 10.8h4"/></svg>';
    const link = (href, label, key) => h("a", { href, "aria-current": active === key ? "page" : null }, label);
    const header = h("header", { class: "topbar" },
      h("div", { class: "topbar-inner" },
        h("a", { class: "brand", href: "/" }, mark, "Dossier"),
        h("nav", { class: "nav", "aria-label": "Main" }, link("/", "Dossiers", "home"), link("/contested", "Contested", "contested")),
        h("div", { class: "session" },
          user
            ? [h("span", { class: "session-user", testid: "current-user" }, user),
               h("button", { class: "btn quiet", type: "button", testid: "logout-button", onclick: () => { session.clear(); window.location.assign("/login"); } }, "Log out")]
            : [link("/login", "Log in", "login"), link("/signup", "Sign up", "signup")])));
    const main = h("main", { id: "main", tabindex: "-1" });
    app.append(header, main);
    return main;
  }

  function requireSession() {
    if (session.token()) return true;
    window.location.replace("/login");
    return false;
  }

  // ------------------------------------------------------------------ auth screens

  function authPage(kind) {
    const signup = kind === "signup";
    document.title = (signup ? "Sign up" : "Log in") + " — Dossier";
    const main = layout(kind);
    const errorSlot = h("div", {});
    const email = h("input", { id: "auth-email", type: "email", required: true, autocomplete: "email", testid: signup ? "signup-email" : "login-email" });
    const password = h("input", { id: "auth-password", type: "password", required: true, autocomplete: signup ? "new-password" : "current-password", minlength: signup ? 8 : null, testid: signup ? "signup-password" : "login-password" });
    const name = signup ? h("input", { id: "auth-name", type: "text", required: true, maxlength: 100, autocomplete: "name", testid: "signup-display-name" }) : null;
    const submit = h("button", { class: "btn", type: "submit", testid: signup ? "signup-submit" : "login-submit" }, signup ? "Create account" : "Log in");
    const idle = submit.textContent;

    const form = h("form", { novalidate: true, onsubmit: async (event) => {
      event.preventDefault();
      errorSlot.replaceChildren();
      setBusy(submit, true, idle, signup ? "Creating account…" : "Logging in…");
      const body = signup
        ? { email: email.value.trim(), password: password.value, display_name: name.value.trim() }
        : { email: email.value.trim(), password: password.value };
      try {
        const res = await api("POST", signup ? "/auth/signup" : "/auth/login", { body });
        if (res.status === 200 || res.status === 201) {
          session.save(res.data);
          window.location.assign("/");
          return;
        }
        errorSlot.replaceChildren(notice("error", errorText(res, "That did not work. Check the details and try again."), "auth-error"));
      } catch (error) {
        errorSlot.replaceChildren(notice("error", "The service could not be reached. Try again in a moment.", "auth-error"));
      }
      setBusy(submit, false, idle, "");
    } },
      h("div", {}, h("label", { for: "auth-email" }, "Email"), email),
      h("div", {}, h("label", { for: "auth-password" }, "Password"), password, signup ? h("p", { class: "hint" }, "At least 8 characters.") : null),
      signup ? h("div", {}, h("label", { for: "auth-name" }, "Display name"), name) : null,
      errorSlot, submit);

    main.append(h("div", { class: "panel auth-card" },
      h("h1", {}, signup ? "Create your account" : "Welcome back"),
      h("p", { class: "lede" }, signup ? "Sign up to research companies and read their dossiers." : "Log in to read and refresh company dossiers."),
      form,
      h("p", { class: "auth-switch" }, signup ? "Already have an account? " : "New here? ",
        h("a", { href: signup ? "/login" : "/signup" }, signup ? "Log in" : "Create an account"))));
    email.focus();
  }

  // ------------------------------------------------------------------ dossier list

  function homePage() {
    if (!requireSession()) return;
    document.title = "Dossiers";
    const main = layout("home");

    // research form
    const input = h("input", { id: "research-domain", type: "text", autocomplete: "off", autocapitalize: "none", spellcheck: "false", placeholder: "acme-robotics.com", testid: "research-domain" });
    const submit = h("button", { class: "btn", type: "submit", testid: "research-submit" }, "Research");
    const messages = h("div", { "aria-live": "polite" });
    let pending = null;   // { body, key } of a request whose outcome is not known yet

    const research = async (event) => {
      event.preventDefault();
      const body = JSON.stringify({ domain: input.value });
      if (!pending || pending.body !== body) pending = { body, key: newKey() };
      messages.replaceChildren();
      setBusy(submit, true, "Research", "Researching…");
      let res;
      try {
        res = await api("POST", "/dossiers", { body: JSON.parse(body), key: pending.key });
      } catch (error) {
        if (error instanceof Redirecting) return;
        messages.replaceChildren(notice("uncertain", "We could not confirm whether this request reached the service. Press Research again: it is sent with the same request key, so at most one build starts.", "research-uncertain"));
        setBusy(submit, false, "Research", "");
        return;
      }
      if (res.status === 200 || res.status === 202) {
        pending = null;
        const domain = (res.data && res.data.domain) || normaliseDomain(input.value);
        window.location.assign("/dossiers/" + encodeURIComponent(domain));
        return;
      }
      if (res.status >= 500) {
        messages.replaceChildren(notice("uncertain", "The service answered with an error, so the outcome is unknown. Press Research again: it is sent with the same request key, so at most one build starts.", "research-uncertain"));
      } else {
        pending = null;
        messages.replaceChildren(notice("error", errorText(res, "That request was refused."), "research-error"));
      }
      setBusy(submit, false, "Research", "");
    };

    main.append(
      h("div", { class: "page-head" },
        h("h1", {}, "Company dossiers"),
        h("p", { class: "lede" }, "Research a company by its web domain. Every value in a dossier comes with the page excerpt that supports it, and sources that disagree are flagged.")),
      h("form", { class: "panel", onsubmit: research },
        h("div", { class: "form-row" },
          h("div", { class: "grow" },
            h("label", { for: "research-domain" }, "Company domain"),
            input,
            h("p", { class: "hint" }, "A bare domain such as acme-robotics.com. A leading www. is ignored.")),
          submit),
        messages));

    // list with search
    const search = h("input", { id: "dossier-search", type: "search", autocomplete: "off", placeholder: "Filter by domain or name", testid: "dossier-search" });
    const region = h("div", { "aria-live": "polite" });
    let issued = 0;
    let applied = 0;

    const itemEl = (d) => {
      const known = d.legal_name;
      return h("a", { class: "dossier-item", href: "/dossiers/" + encodeURIComponent(d.domain), role: "listitem", testid: "dossier-item-" + d.domain, "data-state": d.state },
        h("span", {}, h("span", { class: "domain" }, d.domain), known ? [" ", h("span", { class: "name" }, known)] : null),
        statePill(d.state),
        h("span", { class: "meta" },
          d.researched_at ? h("span", {}, "Researched " + formatMoment(d.researched_at)) : h("span", {}, "Not researched yet"),
          h("span", {}, formatUnits(d.spent_units) + " spent")));
    };

    const showLoading = () => region.replaceChildren(h("div", { class: "skeleton", "aria-busy": "true", testid: "list-loading" }), h("div", { class: "skeleton" }));
    const load = async () => {
      const seq = ++issued;
      const query = search.value;
      let items;
      try {
        items = await listDossiers(query);
      } catch (error) {
        if (error instanceof Redirecting || seq < applied) return;
        applied = seq;
        region.replaceChildren(h("div", { class: "notice error", role: "alert", testid: "list-error" },
          h("span", {}, "The dossier list could not be loaded. "),
          h("button", { class: "btn secondary", type: "button", onclick: () => { showLoading(); load(); } }, "Try again")));
        return;
      }
      if (seq < applied) return;
      applied = seq;
      if (items.length === 0) {
        region.replaceChildren(h("div", { class: "empty", testid: "empty-dossiers" },
          h("strong", {}, query ? "No dossier matches “" + query + "”" : "No dossiers yet"),
          query ? "Try a different domain or company name." : "Enter a company domain above to research your first one."));
      } else {
        region.replaceChildren(h("div", { class: "cards", role: "list", testid: "dossier-list" }, items.map(itemEl)));
      }
    };
    let debounce = null;
    search.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(load, 120); });

    main.append(h("h2", { class: "section-title" }, "Researched companies"),
      h("div", { class: "search-row" }, h("label", { for: "dossier-search" }, "Search dossiers"), search), region);
    showLoading();
    load();
  }

  // ------------------------------------------------------------------ one dossier

  function crumbs(href, label) {
    return h("div", { class: "crumbs" }, h("a", { href }, "← " + label));
  }

  function fieldCard(name, field, evidencePath, notResearched) {
    const candidates = field.candidates || [];
    const values = distinctValues(candidates);
    const status = field.status;
    const hasValue = field.value !== null && field.value !== undefined;
    const citations = field.citations.map((c, i) => {
      const candidate = candidates.find((x) => x.url === c.url && x.excerpt === c.excerpt && x.provider === c.provider);
      return h("figure", { class: "citation", testid: `citation-${name}-${i + 1}`, "data-provider": c.provider },
        h("blockquote", {}, c.excerpt),
        h("figcaption", { class: "source" },
          candidate ? kindChip(candidate.kind) : null, providerChip(c.provider),
          candidate ? h("span", {}, publishedText(candidate)) : null,
          h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" }, sourceLabel(c.url))));
    });
    return h("article", { class: "field", testid: "field-" + name, "data-status": status },
      h("div", { class: "field-head" },
        h("h3", { class: "field-label" }, FIELD_LABELS[name]),
        h("span", { class: "pill " + status }, status === "known" ? "Known" : status === "unknown" ? "Unknown" : "Contested"),
        status === "contested" ? h("span", { class: "chip", testid: "field-contested-" + name }, `${values.length} competing values`) : null),
      h("div", { class: "field-main" },
        hasValue
          ? h("p", { class: "field-value", testid: "field-value-" + name, "data-value": dataValue(field.value) }, formatValue(name, field.value))
          : h("p", { class: "field-none" }, notResearched || "No source supports a value"),
        status === "contested"
          ? h("p", { class: "field-note" }, "Sources disagree. Showing the value from the most authoritative, most recent source. ",
              h("a", { href: evidencePath + "#field-" + name }, "Compare all candidates"))
          : null,
        name === "headcount_range" && hasValue ? h("p", { class: "hint" }, "The range that contains the headcount the sources state.") : null,
        status === "unknown" && !notResearched ? h("p", { class: "hint" }, "No page read in the last build states this.") : null,
        status === "unknown" && notResearched === FAILED_TEXT ? h("p", { class: "hint" }, "Refresh to try again.") : null),
      h("div", { class: "citations", testid: "field-citations-" + name }, citations));
  }

  function notResearchedText(data) {
    if (data.researched_at) return null;
    if (data.state === "building") return "Waiting for the first build";
    return data.state === "failed" ? FAILED_TEXT : null;
  }

  function dossierPage(rawDomain) {
    if (!requireSession()) return;
    const domain = normaliseDomain(rawDomain);
    document.title = domain + " — Dossier";
    const main = layout("home");
    const path = "/dossiers/" + encodeURIComponent(domain);

    const meta = h("div", { class: "facts" });
    const banner = h("div", {});
    const readNotice = h("div", {});
    const fieldsRegion = h("div", { class: "fields", "aria-busy": "true" }, h("div", { class: "skeleton" }), h("div", { class: "skeleton" }), h("div", { class: "skeleton" }));
    const messages = h("div", { class: "toolbar-messages", "aria-live": "polite" });

    const refreshButton = h("button", { class: "btn", type: "button", testid: "dossier-refresh" }, "Refresh research");
    const reloadButton = h("button", { class: "btn secondary", type: "button", testid: "dossier-reload" }, "Reload");
    const evidenceLink = h("a", { class: "btn secondary", href: path + "/evidence", testid: "dossier-evidence-link" }, "View evidence");
    const titleRow = h("div", { class: "title-row" }, h("h1", { testid: "dossier-domain" }, domain));

    main.append(crumbs("/", "All dossiers"),
      h("div", { class: "dossier-head" }, titleRow, meta,
        h("div", { class: "toolbar" }, refreshButton, reloadButton, evidenceLink), messages),
      readNotice, banner, fieldsRegion);

    let issued = 0;
    let applied = 0;
    let lastPainted = null;
    let poller = null;
    let pendingKey = null;
    let refreshing = false;

    const setKnown = (known) => { refreshButton.hidden = !known; evidenceLink.hidden = !known; };
    setKnown(false);

    const paint = (data) => {
      const signature = JSON.stringify(data);
      if (signature === lastPainted) return;
      lastPainted = signature;
      fieldsRegion.removeAttribute("aria-busy");
      titleRow.querySelectorAll(".pill").forEach((el) => el.remove());
      meta.replaceChildren();
      banner.replaceChildren();
      if (data === null) {
        setKnown(false);
        fieldsRegion.replaceChildren(h("div", { class: "empty", role: "status", testid: "dossier-not-found" },
          h("strong", {}, "No dossier for " + domain),
          "Nothing has been researched for this domain yet. ", h("a", { href: "/" }, "Research it from the dossier list"), "."));
        return;
      }
      setKnown(true);
      titleRow.append(statePill(data.state, "dossier-state"));
      meta.append(
        data.researched_at
          ? h("span", {}, "Researched ", h("strong", { testid: "dossier-researched-at" }, formatMoment(data.researched_at)))
          : h("span", {}, "Not researched yet"),
        h("span", {}, "Spent ", h("strong", { testid: "dossier-spent", "data-units": data.spent_units }, formatUnits(data.spent_units))));
      if (data.state === "building") {
        banner.append(h("div", { class: "banner building", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }),
          h("span", {}, "Research in progress. This page updates by itself when the build finishes.")));
      } else if (data.state === "failed") {
        banner.append(h("div", { class: "banner failed", role: "alert" },
          h("span", {}, data.researched_at ? "The latest build failed. Showing the fields of the last successful build." : "The build failed, so nothing is known yet. Try a refresh.")));
      }
      fieldsRegion.replaceChildren(...FIELDS.map(([name]) => fieldCard(name, data.fields[name], path + "/evidence", notResearchedText(data))));
    };

    const syncPolling = (building) => {
      if (building && poller === null) poller = setInterval(read, POLL_MS);
      if (!building && poller !== null) { clearInterval(poller); poller = null; }
    };

    async function read() {
      const seq = ++issued;
      let res;
      try {
        res = await api("GET", path);
      } catch (error) {
        if (!(error instanceof Redirecting) && seq > applied) {
          readNotice.replaceChildren(notice("error", "The service could not be reached. The data below may be out of date.", "read-error"));
        }
        return;
      }
      if (seq < applied) return;          // a later read has already been shown
      if (res.status === 200) {
        applied = seq;
        readNotice.replaceChildren();
        paint(res.data);
        syncPolling(res.data.state === "building");
      } else if (res.status === 404 || res.status === 422) {
        applied = seq;
        readNotice.replaceChildren();
        paint(null);
        syncPolling(false);
      } else {
        readNotice.replaceChildren(notice("error", errorText(res, "The dossier could not be read."), "read-error"));
      }
    }

    reloadButton.addEventListener("click", async () => {
      setBusy(reloadButton, true, "Reload", "Reloading…");
      await read();
      setBusy(reloadButton, false, "Reload", "");
    });

    refreshButton.addEventListener("click", async () => {
      if (refreshing) return;
      refreshing = true;
      if (pendingKey === null) pendingKey = newKey();
      messages.replaceChildren();
      setBusy(refreshButton, true, "Refresh research", "Starting…");
      try {
        const res = await api("POST", path + "/refresh", { key: pendingKey });
        if (res.status === 200 || res.status === 202) {
          pendingKey = null;
          await read();
        } else if (res.status >= 500) {
          messages.replaceChildren(notice("uncertain", "The service answered with an error, so the outcome of the refresh is unknown. Press Refresh again: it is sent with the same request key, so at most one build starts.", "refresh-uncertain"));
        } else {
          pendingKey = null;
          messages.replaceChildren(notice("error", errorText(res, "The refresh was refused."), "refresh-error"));
        }
      } catch (error) {
        if (!(error instanceof Redirecting)) {
          messages.replaceChildren(notice("uncertain", "We could not confirm whether the refresh reached the service. Press Refresh again: it is sent with the same request key, so at most one build starts.", "refresh-uncertain"));
        }
      }
      refreshing = false;
      setBusy(refreshButton, false, "Refresh research", "");
    });

    read();
  }

  // ------------------------------------------------------------------ evidence

  function candidateCard(name, n, c) {
    return h("article", {
      class: "candidate", testid: `candidate-${name}-${n}`,
      "data-value": dataValue(c.value), "data-provider": c.provider, "data-kind": c.kind || "", "data-url": c.url,
      "data-published-at": c.published_at || "", "data-selected": c.selected ? "true" : "false",
    },
      h("div", { class: "candidate-top" },
        h("span", { class: "candidate-value" }, formatValue(name, c.value)),
        c.selected ? h("span", { class: "chip selected" }, "✓ Selected") : null,
        kindChip(c.kind), providerChip(c.provider)),
      h("blockquote", {}, c.excerpt),
      h("div", { class: "source" },
        h("span", {}, publishedText(c)),
        c.retrieved_at ? h("span", {}, "Retrieved " + formatMoment(c.retrieved_at)) : null,
        h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" }, sourceLabel(c.url))));
  }

  function evidencePage(rawDomain) {
    if (!requireSession()) return;
    const domain = normaliseDomain(rawDomain);
    document.title = "Evidence for " + domain + " — Dossier";
    const main = layout("home");
    const path = "/dossiers/" + encodeURIComponent(domain);
    const body = h("div", { "aria-busy": "true" }, h("div", { class: "skeleton" }), h("div", { class: "skeleton" }));
    const titleRow = h("div", { class: "title-row" }, h("h1", { testid: "dossier-domain" }, domain));
    const reload = h("button", { class: "btn secondary", type: "button", testid: "evidence-reload" }, "Reload");
    main.append(crumbs(path, "Back to the dossier"),
      h("div", { class: "dossier-head" }, titleRow,
        h("p", { class: "lede" }, "Every value a page supports, with the excerpt it comes from. Candidates are ranked by source authority (company site and filings, then news, then aggregators), then by recency; the first is selected."),
        h("div", { class: "toolbar" }, reload)),
      body);

    let issued = 0;
    let applied = 0;
    async function read() {
      const seq = ++issued;
      let res;
      try {
        res = await api("GET", path);
      } catch (error) {
        if (!(error instanceof Redirecting) && seq > applied) {
          body.replaceChildren(notice("error", "The service could not be reached. Use Reload to try again.", "read-error"));
        }
        return;
      }
      if (seq < applied) return;
      body.removeAttribute("aria-busy");
      if (res.status === 404 || res.status === 422) {
        applied = seq;
        body.replaceChildren(h("div", { class: "empty", role: "status", testid: "dossier-not-found" }, h("strong", {}, "No dossier for " + domain), "Nothing has been researched for this domain yet."));
        return;
      }
      if (res.status !== 200) {
        body.replaceChildren(notice("error", errorText(res, "The evidence could not be read."), "read-error"));
        return;
      }
      applied = seq;
      titleRow.querySelectorAll(".pill").forEach((el) => el.remove());
      titleRow.append(statePill(res.data.state));
      body.replaceChildren(...[
        res.data.state === "building" ? h("div", { class: "banner building", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), h("span", {}, "A build is running. This is the evidence of the last completed build; use Reload to check again.")) : null,
        ...FIELDS.map(([name, label]) => {
          const field = res.data.fields[name];
          const candidates = field.candidates || [];
          return h("section", { class: "evidence-field", id: "field-" + name },
            h("h2", {}, label, h("span", { class: "pill " + field.status }, field.status === "known" ? "Known" : field.status === "unknown" ? "Unknown" : "Contested")),
            h("div", { class: "candidates", testid: "evidence-" + name },
              candidates.length === 0
                ? h("div", { class: "empty", testid: "evidence-empty-" + name }, h("strong", {}, "No candidates"), "No page read in the last build supports a value for this field.")
                : candidates.map((c, i) => candidateCard(name, i + 1, c))));
        })].filter(Boolean));
      if (window.location.hash) {
        const target = document.getElementById(window.location.hash.slice(1));
        if (target) target.scrollIntoView();
      }
    }
    reload.addEventListener("click", async () => {
      setBusy(reload, true, "Reload", "Reloading…");
      await read();
      setBusy(reload, false, "Reload", "");
    });
    read();
  }

  // ------------------------------------------------------------------ contested

  function contestedPage() {
    if (!requireSession()) return;
    document.title = "Contested fields — Dossier";
    const main = layout("contested");
    const region = h("div", { "aria-live": "polite" });
    main.append(h("div", { class: "page-head" }, h("h1", {}, "Contested fields"),
      h("p", { class: "lede" }, "Fields where trustworthy sources give different values. Open one to compare every candidate and see which was selected.")), region);

    const loading = () => region.replaceChildren(h("div", { class: "skeleton", "aria-busy": "true" }), h("div", { class: "skeleton" }));
    const load = async () => {
      let items;
      try {
        const list = await listDossiers("");
        const dossiers = await mapLimit(list, 6, async (d) => {
          const res = await api("GET", "/dossiers/" + encodeURIComponent(d.domain));
          if (res.status === 404 || res.status === 422) return null;
          if (res.status !== 200) throw new Error("read");
          return res.data;
        });
        items = [];
        for (const dossier of dossiers.filter(Boolean).sort((a, b) => (a.domain < b.domain ? -1 : a.domain > b.domain ? 1 : 0))) {
          for (const [name] of FIELDS) {
            if (dossier.fields[name].status === "contested") items.push({ domain: dossier.domain, name, field: dossier.fields[name] });
          }
        }
      } catch (error) {
        if (error instanceof Redirecting) return;
        region.replaceChildren(h("div", { class: "notice error", role: "alert", testid: "contested-error" },
          h("span", {}, "Contested fields could not be loaded. "),
          h("button", { class: "btn secondary", type: "button", onclick: () => { loading(); load(); } }, "Try again")));
        return;
      }
      if (items.length === 0) {
        region.replaceChildren(h("div", { class: "empty", testid: "empty-contested" }, h("strong", {}, "Nothing is contested"), "Every field with evidence has a single value across its sources."));
        return;
      }
      region.replaceChildren(h("div", { class: "cards", role: "list", testid: "contested-list" }, items.map(({ domain, name, field }) =>
        h("a", { class: "contested-item", role: "listitem", href: "/dossiers/" + encodeURIComponent(domain) + "/evidence", testid: `contested-item-${domain}-${name}`, "data-value": dataValue(field.value) },
          h("span", { class: "contested-top" }, h("span", { class: "domain" }, domain), h("span", { class: "field-label" }, FIELD_LABELS[name], h("span", { class: "sr-only", "aria-hidden": "true" }, " " + name))),
          h("span", { class: "values" }, distinctValues(field.candidates).map((v) =>
            h("span", { class: "value-chip" + (String(v).trim() === String(field.value).trim() ? " selected" : "") }, formatValue(name, v)))),
          h("span", { class: "muted" }, `Selected: ${formatValue(name, field.value)} · ${field.candidates.length} candidates`)))));
    };
    loading();
    load();
  }

  // ------------------------------------------------------------------ routing

  function notFoundPage() {
    document.title = "Not found — Dossier";
    layout("").append(h("div", { class: "empty" }, h("strong", {}, "Page not found"), h("a", { href: "/" }, "Back to the dossier list")));
  }

  function route() {
    const path = window.location.pathname.replace(/\/+$/, "") || "/";
    let match;
    if (path === "/") homePage();
    else if (path === "/login") authPage("login");
    else if (path === "/signup") authPage("signup");
    else if (path === "/contested") contestedPage();
    else if ((match = /^\/dossiers\/([^/]+)\/evidence$/.exec(path))) evidencePage(decodeURIComponent(match[1]));
    else if ((match = /^\/dossiers\/([^/]+)$/.exec(path))) dossierPage(decodeURIComponent(match[1]));
    else notFoundPage();
  }

  route();
})();
