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
      + ".face{border-radius:50%;object-fit:cover;vertical-align:-8px;"
      + "background:rgba(190,222,228,.06);border:1px solid rgba(190,222,228,.16)}"
      + ".pl-c{display:inline-flex;align-items:center;gap:8px}"
      + ".tm-c{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}"
      + ".mu .tm-c,.match .tm-c,.radar-mu .tm-c{gap:4px}"
      + ".ws-head .tm-c{gap:9px}";
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
    // opts.after puts the mark AFTER the label. /game leads with a mirrored
    // two-team scoreboard, and marks on the outside of both names read as two
    // unrelated rows; facing inward they read as one matchup. The flag is on
    // the element rather than inferred, because hydrate() fills these slots
    // later and has to place the image the same way this did.
    var mark = img(name, opts.size, opts.sport);
    var text = '<span>' + esc(label) + '</span>';
    return '<span class="tm-c" data-crest="' + esc(name) + '"'
      + (opts.size ? ' data-size="' + (opts.size | 0) + '"' : "")
      + (opts.sport ? ' data-sport="' + esc(opts.sport) + '"' : "")
      + (opts.after ? ' data-crest-after="1"' : "")
      + (abbr ? ' title="' + esc(name) + '"' : "") + '>'
      + (opts.after ? text + mark : mark + text) + '</span>';
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
      if (html) el.insertAdjacentHTML(
        el.getAttribute("data-crest-after") ? "beforeend" : "afterbegin", html);
    }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---- player headshots ----
     A separate map and a separate fetch, loaded ONLY when a page asks for a
     face. The team map is ~124 rows and every board page wants it; the player
     map changes daily and only the props board wants it, so making the crest
     helper pull both would put a second request on every other page for
     nothing.

     Same failure rule as crests, and it matters more here: a wrong crest is
     embarrassing, a wrong FACE is a photograph of a real person attached to a
     claim about someone else. engine/player_headshots.py already refuses to
     resolve an ambiguous name, so a miss here means "we do not know", and the
     row falls back to the player's name in text. */
  var PMAP = null, PPENDING = null;
  function loadPlayers() {
    if (PMAP) return Promise.resolve(PMAP);
    if (PPENDING) return PPENDING;
    PPENDING = fetch("/data/player-headshots.json", { cache: "force-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { PMAP = (d && d.players) || {}; hydratePlayers(); return PMAP; })
      .catch(function () { PMAP = {}; return PMAP; });
    return PPENDING;
  }
  function player(name) { return (PMAP || {})[norm(name)] || null; }
  function face(name, size) {
    var p = player(name);
    if (!p) return "";
    var s = size || 28;
    return '<img class="face" src="' + p.img + '" width="' + s + '" height="' + s
      + '" loading="lazy" decoding="async" alt=""'
      + ' onerror="this.style.display=\'none\'">';
  }
  /* Mark the spot, fill it when the map lands — same contract as hydrate(). */
  function playerTag(name, size) {
    return '<span class="pl-c" data-face="' + esc(name) + '"'
      + (size ? ' data-size="' + (size | 0) + '"' : "") + '>'
      + face(name, size) + '</span>';
  }
  function hydratePlayers(root) {
    if (!PMAP) return;
    var spots = (root || document).querySelectorAll("[data-face]");
    for (var i = 0; i < spots.length; i++) {
      var el = spots[i];
      if (el.querySelector("img.face")) continue;
      var html = face(el.getAttribute("data-face"),
                      parseInt(el.getAttribute("data-size"), 10) || 28);
      if (html) el.insertAdjacentHTML("afterbegin", html);
    }
  }

  window.Crest = { load: load, get: get, img: img, team: team, hydrate: hydrate,
                   loadPlayers: loadPlayers, player: player, face: face,
                   playerTag: playerTag, hydratePlayers: hydratePlayers };

  /* SELF-HEALING, and it has to be.
     ------------------------------------------------------------------
     This file used to sweep exactly three times: when the map resolved, on
     DOMContentLoaded, and on window.load. Every one of those fires before a
     board page has its DATA. board.json is ~100KB and the rows are written
     from its .then(); team-logos.json is 20KB and served with force-cache, so
     in production it resolves first, all three sweeps run against an empty
     table, and every row written afterwards keeps its data-crest placeholder
     for the life of the page. Live, the whole board rendered with ZERO images
     — not one crest on any sport.

     It survived review because on localhost board.json returns in a handful of
     milliseconds and usually wins the race, so the bug is invisible exactly
     where it gets tested. It also looks sport-specific from the outside: you
     see it on whichever tab you happen to open, which is why it was reported
     as "the NBA logos are missing".

     Only index.html called hydrate() after its own render. Rather than add
     that call to the other four pages and rely on the next page remembering
     to, watch the document: any node that arrives with a crest slot in it gets
     filled, whenever it arrives and whoever wrote it.

     setTimeout, not requestAnimationFrame or requestIdleCallback: neither of
     those fires in a backgrounded tab, and a board left open in another tab is
     the normal case here. That exact mistake has already cost this codebase
     three separate bugs. */
  function watch() {
    if (!window.MutationObserver) return;       // sweeps below still apply
    var queued = false;
    new MutationObserver(function (muts) {
      if (queued) return;
      for (var i = 0; i < muts.length; i++) {
        if (muts[i].addedNodes && muts[i].addedNodes.length) {
          queued = true;
          setTimeout(function () {
            queued = false;
            hydrate();
            hydratePlayers();
          }, 0);
          return;
        }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
    /* Terminates: hydrate() inserts <img class="crest">, which is an added
       node and does queue one more pass, but that pass finds every slot
       already filled, inserts nothing, and the cycle stops. */
  }

  /* Start fetching as soon as the script parses, and sweep once more after the
     page settles so rows written by a late render still get their crest. */
  load();
  watch();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { hydrate(); });
  }
  window.addEventListener("load", function () { hydrate(); });
})();
