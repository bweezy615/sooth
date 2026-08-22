/* Team crests, keyed by the full team names the board already publishes.
   Deliberately its own file rather than an addition to desk.js: pages opt in,
   and a page that never calls it pays nothing.

   Everything here fails silent. A crest is an aid to scanning, never the
   carrier of a fact — every row states its teams in text with or without one,
   so a missing map, a 404 or a blocked CDN degrades to exactly the board we
   shipped before, and never to a broken image or an empty column. */
(function () {
  var MAP = null, PENDING = null;

  /* The helper carries its own presentation so adding crests to a page is one
     script tag, and so no shared stylesheet has to be touched to do it. */
  (function styles() {
    var css = ".crest{vertical-align:-3px;object-fit:contain}"
      + ".tm-c{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}"
      + ".mu .tm-c,.match .tm-c,.radar-mu .tm-c{gap:4px}";
    var el = document.createElement("style");
    el.textContent = css;
    document.head.appendChild(el);
  })();

  function norm(s) {
    return String(s == null ? "" : s)
      .normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .toLowerCase().replace(/[^a-z0-9]+/g, "");
  }

  /* team-logos.json is keyed by full team name ("arizonacardinals"), which is
     what board.json publishes. The sealed slate does NOT: the pick engine
     works in schedule abbreviations ("MIA", "LV"), so every crest lookup on
     /picks missed and the whole slate rendered without a single logo. Index
     the abbreviations too, once, at load.

     Collisions are real and must not be silently resolved: ATL is both the
     Braves and the Falcons, and several more overlap across leagues. An
     ambiguous abbreviation resolves to NOTHING rather than to a coin flip —
     a wrong crest beside a matchup is worse than no crest, because it looks
     authoritative. Callers that know their sport can pass {sport:"nfl"}. */
  var ABBR = null;
  function indexAbbrs() {
    ABBR = {};
    var seen = {};
    Object.keys(MAP || {}).forEach(function (k) {
      var t = MAP[k];
      if (!t || !t.abbr) return;
      var a = norm(t.abbr);
      /* team-logos.json carries an explicit `sport` on every entry; prefer it
         and only fall back to sniffing the CDN path, so a logo host change
         cannot quietly break the scoped lookup. */
      var league = /espncdn\.com\/i\/teamlogos\/(\w+)\//.exec(t.logo || "");
      var sport = norm(t.sport || "")
        || (league ? league[1] : (/mlbstatic/.test(t.logo || "") ? "mlb" : ""));
      if (sport) ABBR[sport + ":" + a] = t;          // unambiguous, always safe
      if (seen[a]) { ABBR[a] = null; return; }        // ambiguous -> no crest
      seen[a] = 1;
      ABBR[a] = t;
    });
  }

  function load() {
    if (MAP) return Promise.resolve(MAP);
    if (PENDING) return PENDING;
    PENDING = fetch("/data/team-logos.json", { cache: "force-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { MAP = (d && d.teams) || {}; indexAbbrs(); hydrate(); return MAP; })
      .catch(function () { MAP = {}; ABBR = {}; return MAP; });
    return PENDING;
  }

  /* get("Boston Red Sox") · get("MIA") · get("MIA", "nfl") */
  function get(team, sport) {
    var k = norm(team);
    var direct = (MAP || {})[k];
    if (direct) return direct;
    if (!ABBR) return null;
    if (sport) {
      var scoped = ABBR[norm(sport) + ":" + k];
      if (scoped) return scoped;
    }
    return ABBR[k] || null;
  }

  /* Markup for one crest. Width and height are set so the row does not reflow
     when the image lands — a board that twitches as 20 logos resolve is worse
     than one with no logos at all. */
  function img(team, size, sport) {
    var t = get(team, sport);
    if (!t) return "";
    var s = size || 16;
    return '<img class="crest" src="' + t.logo + '" width="' + s + '" height="' + s
      + '" loading="lazy" decoding="async" alt=""'
      + ' onerror="this.style.display=\'none\'">';
  }

  /* Crest + label as one non-breaking unit, so a wrap never orphans the mark
     from the name it belongs to. */
  function team(name, opts) {
    opts = opts || {};
    var t = get(name, opts.sport);
    var abbr = opts.abbr && t;
    var label = abbr ? t.abbr : name;
    // When the label is shortened the full name must stay recoverable. "BOS"
    // is obvious to someone who already follows the sport and opaque to the
    // person we are trying not to lose.
    return '<span class="tm-c" data-crest="' + esc(name) + '"'
      + (opts.size ? ' data-size="' + (opts.size | 0) + '"' : "")
      + (opts.sport ? ' data-sport="' + esc(opts.sport) + '"' : "")
      + (abbr ? ' title="' + esc(name) + '"' : "") + '>'
      + img(name, opts.size, opts.sport) + '<span>' + esc(label) + '</span></span>';
  }

  /* Pages render whenever their own data lands, which may be before or after
     the crest map. Rather than make every caller await us, mark each spot and
     fill in the ones that were written early. Idempotent, so calling it again
     after a re-render costs nothing. */
  function hydrate(root) {
    if (!MAP) return;
    var spots = (root || document).querySelectorAll("[data-crest]");
    for (var i = 0; i < spots.length; i++) {
      var el = spots[i];
      if (el.querySelector("img.crest")) continue;
      var html = img(el.getAttribute("data-crest"),
                     parseInt(el.getAttribute("data-size"), 10) || 16,
                     el.getAttribute("data-sport") || "");
      if (html) el.insertAdjacentHTML("afterbegin", html);
    }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  window.Crest = { load: load, get: get, img: img, team: team, hydrate: hydrate };

  /* Start fetching as soon as the script parses, and sweep once more after the
     page settles so rows written by a late render still get their crest. */
  load();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { hydrate(); });
  }
  window.addEventListener("load", function () { hydrate(); });
})();
