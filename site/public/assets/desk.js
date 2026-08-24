/* SOOTH DESK — shared shell + instrument primitives.
   One file mounts the app shell on every desk page and exposes the
   components the design language is built from: the price spectrum,
   the ranked feed row, the intelligence table, and the data states.
   No framework, no dependencies — the whole product is numbers and SVG. */
(function(){
"use strict";

/* ---------- helpers ---------- */
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function am(n){return n==null?"·":(n>0?"+"+n:String(n));}
function implied(p){p=Number(p);return p<0? -p/(-p+100) : 100/(p+100);}
function pct(x,dp){return x==null?"·":(x*100).toFixed(dp==null?1:dp)+"%";}
function pts(x,dp){return x==null?"·":(x>0?"+":"")+Number(x).toFixed(dp==null?2:dp);}
function ago(iso){
  var t=Date.parse(iso); if(isNaN(t)) return "—";
  var s=Math.max(0,Math.round((Date.now()-t)/1000));
  if(s<60) return s+"S AGO";
  if(s<3600) return Math.round(s/60)+"M AGO";
  if(s<172800) return (s/3600).toFixed(1).replace(/\.0$/,"")+"H AGO";
  return Math.round(s/86400)+"D AGO";
}
function when(iso){
  var t=Date.parse(iso); if(isNaN(t)) return "—";
  return new Date(t).toLocaleString([],{weekday:"short",month:"short",
    day:"numeric",hour:"numeric",minute:"2-digit"});
}
/* canonical book key -> desk abbreviation. Data is primary; books stay small. */
var BOOK={draftkings:"DK",fanduel:"FD",betmgm:"MGM",williamhill_us:"CZR",
  betrivers:"BR",bovada:"BOV",betonlineag:"BOL",lowvig:"LVG",betus:"BUS",
  mybookieag:"MYB",espnbet:"ESPN",fanatics:"FAN",
  DraftKings:"DK",FanDuel:"FD",BetMGM:"MGM",Caesars:"CZR",BetRivers:"BR",
  Bovada:"BOV",BetOnline:"BOL",LowVig:"LVG",BetUS:"BUS",MyBookie:"MYB"};
function bk(name){return BOOK[name]||String(name).slice(0,4).toUpperCase();}

/* ---------- shell ---------- */
/* Two of these were reachable only from body copy: /ask, which answers a
   question about a specific game, and /learn, the plain-English explainer.
   A newcomer was landing on a dense board with no visible route to the guide
   written for them, and the analyst was effectively hidden. Both are now
   addressable from anywhere on the site. */
var NAV=[
  {href:"/",            key:"market",  label:"MARKET"},
  {href:"/picks",       key:"picks",   label:"PICKS"},
  {href:"/props",       key:"props",   label:"PROPS"},
  {href:"/edges",       key:"movement",label:"MOVEMENT"},
  {href:"/research",    key:"research",label:"RESEARCH"},
  {href:"/ask",         key:"ask",     label:"ANALYST"},
  {href:"/trust",       key:"ledger",  label:"LEDGER"},
  {href:"/alerts",      key:"alerts",  label:"ALERTS"},
  {href:"/learn",       key:"learn",   label:"GUIDE", newcomer:true}
];
function header(page){
  return '<header class="hd"><div class="wrap">'
    +'<div class="hd-r1">'
    +'<a class="brand" href="/"><span class="mk"></span><b>sooth<i>.bet</i></b>'
    +'<span class="sb">Market intelligence. Honest edge.</span></a>'
    +'<span class="hd-spacer"></span>'
    +'<nav class="hd-links" aria-label="Sections">'
    +NAV.map(function(n){return '<a href="'+n.href+'"'
      +(n.newcomer?' class="hd-new" title="New to betting? Start here"':'')
      +(n.key===page?' aria-current="page"':'')+'>'+n.label+'</a>';}).join("")
    +'</nav>'
    +'</div>'
    +'<div class="hd-r2" id="sportRail" role="tablist" aria-label="Sports"></div>'
    +'</div></header>';
}
/* the compliance floor travels with the shell — every desk page carries it */
function footer(){
  return '<footer class="ft"><div class="wrap">'
    +'<p><b>Entertainment and analysis only. We do not accept, place, or '
    +'facilitate wagers</b>, and we hold no customer funds. Not affiliated with '
    +'any league or sportsbook. Past performance does not indicate future '
    +'results — our published backtest shows a loss against the closing market. '
    +'Nothing here is a recommendation to bet. 21+, where lawful.</p>'
    +'<p>If gambling is causing harm, the National Problem Gambling Helpline is '
    +'<b>1-800-522-4700</b>, available 24/7.</p>'
    +'<div class="links"><a href="/learn">How it works</a>'
    +'<a href="/methodology">Methodology</a>'
    +'<a href="/verify">Verify</a><a href="/record">Record</a>'
    +'<a href="/ledger">Ledger</a><a href="/disclaimers">Disclaimers</a></div>'
    +'</div></footer>';
}
/* sport rail: every sport we cover, with an honest live/offseason state.
   Data decides the dot — sports_live from the board, never a hardcoded list. */
var SPORTS=[{k:"nfl",l:"NFL"},{k:"mlb",l:"MLB"},{k:"nba",l:"NBA"},
            {k:"nhl",l:"NHL"},{k:"ufc",l:"UFC"}];
function sportRail(board,active,onpick){
  var live={}; var counts={};
  ((board&&board.boards)||[]).forEach(function(b){
    live[b.sport]=true; counts[b.sport]=b.n_events;});
  var el=document.getElementById("sportRail"); if(!el) return;
  if(!el.dataset.built){
    el.innerHTML=SPORTS.map(function(s){
      return '<button class="sp" role="tab" data-sp="'+s.k+'" aria-selected="false">'
        +'<span class="d off"></span>'+s.l+'<span class="c n"></span></button>';
    }).join("")+'<span class="rail-ink" aria-hidden="true"></span>';
    el.dataset.built="1";
    el.addEventListener("click",function(e){
      var b=e.target.closest(".sp");
      if(b&&el._onpick) el._onpick(b.dataset.sp);
    });
  }
  el._onpick=onpick;
  var activeBtn=null;
  [].forEach.call(el.querySelectorAll(".sp"),function(b){
    var k=b.dataset.sp, on=!!live[k];
    b.setAttribute("aria-selected",k===active?"true":"false");
    if(k===active) activeBtn=b;
    b.querySelector(".d").className="d"+(on?"":" off");
    b.querySelector(".c").textContent=on?counts[k]:"";
  });
  /* the ink slides to the active pill — user action, --t-ui --e-out */
  var ink=el.querySelector(".rail-ink");
  if(ink&&activeBtn){
    ink.style.width=activeBtn.offsetWidth+"px";
    ink.style.transform="translateX("+activeBtn.offsetLeft+"px)";
  }
}
var EMBEDDED=/[?&]embed=1/.test(location.search);

/* Navigate keeping the embed contract: inside a monitor, every hop stays
   chromeless — EXCEPT the desk itself, which always escapes to the top
   window, because "/" inside a monitor would nest the desk inside itself.
   (/subscribe used to escape too; there is no checkout to escape to now.) */
function escapes(url){
  return url==="/";
}
function go(url){
  if(EMBEDDED && url.indexOf("://")<0){
    if(escapes(url)){
      try{ window.top.location.href=url; return; }catch(e){}
    }
    if(!/[?&]embed=1/.test(url))
      url+= (url.indexOf("?")<0?"?":"&")+"embed=1";
  }
  location.href=url;
}

/* ---------- responsive tables ----------
   Copy each column's header onto its cells as data-l, so the phone stylesheet
   can turn a row into a labelled card (see the max-width:720px block in
   desk.css). Doing it here rather than in every renderer means a table added
   later is responsive without anyone remembering to make it so.

   The FIRST cell of a row is left unlabelled on purpose and becomes the
   card's title line. In every one of these tables column one is the row's
   identity — the matchup, the game, the pick — and labelling it "MATCHUP"
   would demote the one thing that tells you which card you are reading.
   Cells spanning columns are skipped for the same reason: a colspan cell is
   structural, not a field.

   An observer rather than a one-shot call because most of these tables are
   written by fetch callbacks long after DOMContentLoaded, and several rerender
   on a sport switch. Labelling is idempotent and skipped once done. */
function labelCells(scope){
  var tables=(scope||document).querySelectorAll?
    (scope||document).querySelectorAll("table"):[];
  [].forEach.call(tables,function(t){
    var heads=t.querySelectorAll("thead th");
    if(!heads.length) return;
    var labels=[].map.call(heads,function(h){return h.textContent.trim();});
    [].forEach.call(t.querySelectorAll("tbody tr"),function(tr){
      if(tr.dataset.stacked) return;
      tr.dataset.stacked="1";
      var i=0;
      [].forEach.call(tr.children,function(td,idx){
        var span=td.colSpan||1;
        if(idx>0 && span===1 && labels[i]) td.setAttribute("data-l",labels[i]);
        i+=span;
      });
    });
  });
}
var stackQueued=false;
function stack(){
  if(stackQueued) return;
  stackQueued=true;
  /* setTimeout, not requestAnimationFrame: rAF does not run in a backgrounded
     tab, so a table rendered by a fetch callback while the tab is hidden would
     stay unlabelled until the user came back — and on a phone, "came back"
     is exactly when they look at it. */
  setTimeout(function(){ stackQueued=false; labelCells(document); },0);
}
function watchTables(){
  stack();
  if(!window.MutationObserver) return;
  new MutationObserver(stack).observe(document.body,{childList:true,subtree:true});
}

function mount(page){
  /* Before anything else, and in embedded mode too: a monitor on a phone has
     the same 760px table problem the standalone page does. */
  watchTables();
  /* Inside a desk monitor (?embed=1) the page is one screen of a
     larger instrument: no site header, no footer — the desk carries both. */
  if(EMBEDDED){
    document.documentElement.classList.add("embedded");
    /* Bare-path links would re-grow the site chrome after one click: rewrite
       same-origin navigations to carry the embed flag. */
    document.addEventListener("click",function(e){
      var a=e.target.closest("a[href]"); if(!a) return;
      var href=a.getAttribute("href");
      if(!href||href.charAt(0)==="#"||href.indexOf("://")>=0) return;
      if(/[?&]embed=1/.test(href)&&!escapes(href)) return;
      e.preventDefault(); go(href);
    });
    /* a monitor that navigated away from its workspace root needs a way
       home that isn't the browser's back button */
    var ROOTS=/^\/(market|ask|research|picks|trust)(\.html)?$/;
    if(!ROOTS.test(location.pathname)){
      document.addEventListener("DOMContentLoaded",function(){
        document.body.insertAdjacentHTML("afterbegin",
          '<button class="embed-back" aria-label="Back">← BACK</button>');
        document.querySelector(".embed-back").addEventListener("click",function(){
          if(history.length>1) history.back();
          else go(location.pathname.indexOf("game")>=0?"/market":"/market");
        });
      });
    }
    /* Keyboard relay: the desk's spatial keys keep working while a monitor
       holds focus — except while actually typing. */
    addEventListener("keydown",function(e){
      var t=e.target;
      if(/INPUT|TEXTAREA|SELECT/.test(t.tagName)||t.isContentEditable) return;
      if(!/^(Escape|ArrowLeft|ArrowRight|[1-5])$/.test(e.key)) return;
      try{ parent.postMessage({soothDesk:e.key}, location.origin); }catch(err){}
    });
    return;
  }
  document.body.insertAdjacentHTML("afterbegin",header(page));
  document.body.insertAdjacentHTML("beforeend",footer()+tabs());
}

/* The bar that keeps the phone reading as an app. It lives on index.html
   already; every other screen was dropping it on arrival, so a tap on PICKS
   left the visitor on a page with no way back but the browser's button.
   Injected rather than pasted into five files: one nav, one place to fix it.
   Styles: ".m-tabs" in desk.css. Never inside a monitor (mount returns
   before this when EMBEDDED) — the desk carries its own navigation there. */
/* Fourth column is the rest of the surface that tab owns, so a visitor who
   followed "SEE ALL" off the board still sees which room they are in. Only
   pages the phone shell can actually reach through that tab are listed —
   /learn, /record and the rest hang off the fine print, belong to no tab,
   and correctly light nothing. */
var TABS=[["/","board","BOARD",["/market","/edges","/game"]],
          ["/picks","picks","PICKS",[]],
          ["/trust","ledger","LEDGER",[]],
          ["/ask","ask","ANALYST",[]],
          ["/alerts","alerts","ALERTS",[]]];
function tabs(){
  /* index.html writes its own; never stack a second one on top of it */
  if(document.querySelector(".m-tabs")) return "";
  var here=location.pathname.replace(/\.html$/,"").replace(/(.)\/$/,"$1")||"/";
  return '<nav class="m-tabs" aria-label="Main">'+TABS.map(function(t){
    var on=t[0]===here||t[3].indexOf(here)>=0;
    return '<a href="'+t[0]+'"'+(on?' aria-current="page"':'')+
      '><span class="m-ti" data-i="'+t[1]+'"></span>'+t[2]+'</a>';
  }).join("")+'</nav>';
}

/* ---------- motion machinery ----------
   CONTRACT: motion helpers fire only from (a) a user action, (b) a witnessed
   payload diff, or (c) a real clock event. prev === null NEVER animates —
   content that was already true when the page opened arrives without
   ceremony. CSS handles its own reduced-motion kill; these helpers guard the
   JS side, because the CSS kill cannot stop WAAPI or rAF. */
var _rm=null;
function reduced(){
  if(_rm===null){
    try{_rm=window.matchMedia("(prefers-reduced-motion: reduce)").matches;}
    catch(e){_rm=false;}
  }
  return _rm;
}
/* shimmer -> content handoff AND lens change: one beat, two names.
   land(el, render): fade whatever is there out over --t-view, run the
   synchronous render at the dark midpoint, fade the new content in whole —
   one unit, no stagger. The JSON arrived as one file; animating assembly
   would lie about the transport. swap() is the same beat under its
   lens-change name (sport switch, range toggle). */
function land(el,render){
  if(reduced()||!el.firstChild){ render(); if(el.style)el.style.opacity="1"; return; }
  el.style.transition="opacity var(--t-view) var(--e-out)";
  el.style.opacity="0";
  setTimeout(function(){
    render();
    requestAnimationFrame(function(){ el.style.opacity="1"; });
  },160);
}
var swap=land;

/* ---------- data machinery ---------- */
function load(url){
  return fetch(url,{cache:"no-store"}).then(function(r){
    if(!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function(d){
    var ts=d.generated_at||d.checked_at;
    var age=ts?(Date.now()-Date.parse(ts))/36e5:null;
    return {ok:true,data:d,ts:ts,ageH:age};
  }).catch(function(e){return {ok:false,err:String(e)};});
}
/* freshness is a fact about the data: content timestamp, never assumption */
function feedState(res,staleH){
  if(!res.ok) return "dead";
  if(res.ageH!=null && res.ageH>(staleH||3)) return "stale";
  return "live";
}
function connecting(el,label){
  el.innerHTML='<div class="state"><span class="tl">'+esc(label||"MARKET FEED")
    +' CONNECTING…</span></div>'
    +'<div class="shimmer"></div><div class="shimmer" style="width:70%"></div>'
    +'<div class="shimmer" style="width:85%"></div>';
}

/* ---------- THE MARKET: price spectrum ----------
   Every book positioned by its own implied probability for one side of one
   market; the de-vigged fair price anchored as a dashed line. The point of
   the instrument: you see WHERE each book sits and that they disagree,
   before you read a single number. */
function spectrum(opts){
  var quotes=(opts.quotes||[]).filter(function(q){return q.price!=null;});
  if(quotes.length<1) return '<div class="state tl">NO PRICES POSTED</div>';
  /* cluster identical prices so eleven books don't print eleven labels */
  var byP={};
  quotes.forEach(function(q){
    var k=String(q.price);
    (byP[k]=byP[k]||{price:q.price,books:[]}).books.push(bk(q.book));});
  var cl=Object.keys(byP).map(function(k){return byP[k];});
  cl.forEach(function(c){c.ip=implied(c.price);});
  cl.sort(function(a,b){return a.ip-b.ip;});
  var ips=cl.map(function(c){return c.ip;});
  if(opts.fairProb!=null) ips=ips.concat([opts.fairProb]);
  var lo=Math.min.apply(null,ips), hi=Math.max.apply(null,ips);
  /* hold a floor on the axis so a tight market LOOKS tight */
  var span=Math.max(hi-lo,0.03), mid=(hi+lo)/2;
  lo=mid-span*0.62; hi=mid+span*0.62;

  /* THE DECK — a shallow perspective plane the books stand on. The geometry
     is real (one vanishing direction, converging lanes, elliptical ground
     shadows), the palette is not decorated: depth carries the hierarchy,
     color still only marks the best number and the fair anchor. */
  var W=opts.width||860, H=130, PAD=44;
  var bY=58, fY=98;                       /* deck back / front edge */
  var bIn=26, fIn=-2;                     /* horizontal inset at each edge */
  var laneY=84, t=(laneY-bY)/(fY-bY);     /* the lane the pins stand on */
  var inn=bIn*(1-t)+fIn*t;
  function X(p){return (PAD+inn+8)+((p-lo)/(hi-lo))*(W-2*(PAD+inn+8));}
  function edge(y){var i=bIn*(1-(y-bY)/(fY-bY))+fIn*((y-bY)/(fY-bY));
    return [PAD+i,W-PAD-i];}

  var out='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'
    +esc(opts.label||"Sportsbook prices on one scale")+'">'
  +'<defs>'
  +'<linearGradient id="mkN" x1="0" y1="0" x2="0" y2="1">'
    +'<stop offset="0" stop-color="#C7CDD8"/><stop offset=".45" stop-color="#8A919D"/>'
    +'<stop offset="1" stop-color="#565C68"/></linearGradient>'
  +'<linearGradient id="mkB" x1="0" y1="0" x2="0" y2="1">'
    +'<stop offset="0" stop-color="#8CF6DC"/><stop offset=".45" stop-color="#2DD4A7"/>'
    +'<stop offset="1" stop-color="#1B8A66"/></linearGradient>'
  +'<linearGradient id="deck" x1="0" y1="0" x2="0" y2="1">'
    +'<stop offset="0" stop-color="rgba(255,255,255,.015)"/>'
    +'<stop offset=".55" stop-color="rgba(255,255,255,.05)"/>'
    +'<stop offset="1" stop-color="rgba(255,255,255,.085)"/></linearGradient>'
  +'<linearGradient id="rfl" x1="0" y1="0" x2="0" y2="1">'
    +'<stop offset="0" stop-color="white" stop-opacity=".35"/>'
    +'<stop offset="1" stop-color="white" stop-opacity="0"/></linearGradient>'
  +'<filter id="mkS" x="-60%" y="-60%" width="220%" height="260%">'
    +'<feDropShadow dx="0" dy="1.5" stdDeviation="1.4" flood-color="#000" flood-opacity=".6"/></filter>'
  +'<filter id="mkG" x="-120%" y="-120%" width="340%" height="340%">'
    +'<feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="#2DD4A7" flood-opacity=".5"/></filter>'
  +'</defs>';

  /* the deck itself: surface, back highlight, converging lane lines */
  var b=edge(bY), f=edge(fY);
  out+='<polygon points="'+b[0]+','+bY+' '+b[1]+','+bY+' '+f[1]+','+fY+' '+f[0]+','+fY
    +'" fill="url(#deck)"/>'
    +'<line x1="'+b[0]+'" y1="'+bY+'" x2="'+b[1]+'" y2="'+bY
      +'" stroke="rgba(255,255,255,.14)" stroke-width="1"/>'
    +'<line x1="'+f[0]+'" y1="'+fY+'" x2="'+f[1]+'" y2="'+fY
      +'" stroke="rgba(0,0,0,.55)" stroke-width="1.5"/>';
  [0.33,0.66].forEach(function(k){
    var y=bY+(fY-bY)*k, e=edge(y);
    out+='<line x1="'+e[0]+'" y1="'+y+'" x2="'+e[1]+'" y2="'+y
      +'" stroke="rgba(255,255,255,.035)"/>';});

  /* fair anchor: the tallest post on the deck */
  if(opts.fairProb!=null){
    var fx=X(opts.fairProb);
    out+='<ellipse cx="'+fx+'" cy="'+laneY+'" rx="9" ry="2.6" fill="rgba(0,0,0,.5)"/>'
      +'<line x1="'+fx+'" y1="'+laneY+'" x2="'+fx+'" y2="20" stroke="#B4BAC4"'
        +' stroke-width="1" stroke-dasharray="2 3"/>'
      +'<text class="fair-lb" x="'+fx+'" y="12" text-anchor="middle">FAIR'
      +(opts.fairPrice!=null?" "+esc(am(opts.fairPrice)):"")+'</text>';
  }

  /* pins — each book stands on the deck; the head is the raised indicator */
  var bestIp=cl[0].ip, lastX=-999, lvl=0;
  cl.forEach(function(c){
    var x=X(c.ip), best=c.ip===bestIp && cl.length>1;
    lvl=(x-lastX<52)?(1-lvl):0; lastX=x;
    var headY=lvl?26:34, yPr=headY-6, yBk=lvl?fY+22:fY+12;
    var books=c.books.slice(0,2).join("·")+(c.books.length>2?" +"+(c.books.length-2):"");
    out+='<g'+(best?' class="g-best"':'')+'>'
      +'<ellipse cx="'+x+'" cy="'+laneY+'" rx="7" ry="2.2" fill="rgba(0,0,0,.55)"/>'
      +'<line x1="'+x+'" y1="'+laneY+'" x2="'+x+'" y2="'+(headY+14)
        +'" stroke="'+(best?"rgba(45,212,167,.55)":"rgba(138,145,157,.45)")+'" stroke-width="1.2"/>'
      +'<rect x="'+(x-3.5)+'" y="'+headY+'" width="7" height="15" rx="1.8" '
        +'fill="url(#'+(best?"mkB":"mkN")+')" filter="url(#'+(best?"mkG":"mkS")+')"/>'
      +'<rect x="'+(x-3.5)+'" y="'+headY+'" width="7" height="3.5" rx="1.6" fill="url(#rfl)"/>'
      +'<text class="bk-pr" x="'+x+'" y="'+yPr+'" text-anchor="middle">'
        +esc(am(c.price))+'</text>'
      +'<text class="bk-lb" x="'+x+'" y="'+(fY+12)+'" text-anchor="middle">'
        +esc(books)+'</text></g>';
  });
  out+='</svg>';
  var range=(cl.length>1)?((cl[cl.length-1].ip-cl[0].ip)*100):0;
  var capL=opts.caption!=null?opts.caption:
    (cl.length>1
      ?'<span class="tl">SAME BET · <b>'+quotes.length+' PRICES</b> · <b>'
        +range.toFixed(2)+' PTS</b> BETWEEN BEST AND WORST</span>'
      :'<span class="tl">ONLY ONE BOOK HAS POSTED THIS — NOTHING TO COMPARE YET</span>');
  return '<div class="spec"><div class="spec-scroll">'+out+'</div>'
    +'<div class="spec-cap">'+capL
    +'<span class="tl">'+esc(opts.right||"")+'</span></div></div>';
}


/* ---------- MARKET TIMELINE ----------
   Where the price has been: per-book traces over a consensus baseline, in
   points of implied probability — the one unit every instrument shares.
   The axis holds a floor so a quiet market LOOKS quiet, and each detected
   move can be pinned on the baseline as an annotation. Pure SVG. */
function timeline(mkt,opts){
  opts=opts||{};
  var traces=(mkt.books||[]).slice(0,12);
  if(!traces.length) return "";
  var winH=opts.hours||72, cut=(Date.now()/1000)-winH*3600;
  function cutpts(pts){return pts.filter(function(p){return p[0]>=cut;});}
  var cons=cutpts(mkt.consensus||[]);
  var multi=traces.length>1;
  var all=[];
  traces.forEach(function(tr){all=all.concat(cutpts(tr.pts));});
  if(cons.length) all=all.concat(cons);
  if(all.length<2) return '<div class="state tl">NOT ENOUGH HISTORY IN THIS WINDOW</div>';
  var ts=all.map(function(p){return p[0];}), vs=all.map(function(p){return p[1];});
  var t0=Math.min.apply(null,ts), t1=Math.max.apply(null,ts);
  var lo=Math.min.apply(null,vs), hi=Math.max.apply(null,vs);
  /* floor the y-span at 4 pts so a 1-pt wiggle cannot look like a crash */
  var MIN=4, midV=(hi+lo)/2, spanV=Math.max(hi-lo,MIN)*1.25;
  lo=midV-spanV/2; hi=midV+spanV/2;
  var W=860,H=170,L=46,R=14,T=12,B=26;
  function X(t){return L+((t-t0)/Math.max(t1-t0,1))*(W-L-R);}
  function Y(v){return T+(1-(v-lo)/(hi-lo))*(H-T-B);}
  function path(pts){return pts.map(function(p,i){
    return (i?"L":"M")+X(p[0]).toFixed(1)+" "+Y(p[1]).toFixed(1);}).join("");}
  var out='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'
    +esc(opts.label||"Price history")+'">';
  /* frame: three horizontal gridlines with pts labels */
  [0,.5,1].forEach(function(k){
    var v=lo+(hi-lo)*k, y=Y(v);
    out+='<line x1="'+L+'" y1="'+y+'" x2="'+(W-R)+'" y2="'+y
      +'" stroke="rgba(255,255,255,.05)"/>'
      +'<text x="'+(L-6)+'" y="'+(y+3)+'" text-anchor="end" class="bk-lb">'
      +v.toFixed(1)+'</text>';});
  /* book traces first, dim, so the baseline reads on top. End labels are
     placed greedily by vertical distance — books that converge to the same
     price would otherwise print an unreadable stack at the right edge. */
  var labelYs=[];
  traces.forEach(function(tr){
    var pts=cutpts(tr.pts); if(pts.length<2) return;
    out+='<path d="'+path(pts)+'" fill="none" stroke="rgba(138,145,157,'
      +(multi?".35":".9")+')" stroke-width="1"/>';
    var y=Y(pts[pts.length-1][1]);
    var clash=labelYs.some(function(py){return Math.abs(py-y)<9;});
    if(!clash){
      labelYs.push(y);
      out+='<text x="'+Math.min(X(pts[pts.length-1][0])+4,W-2)+'" y="'+(y+3)
        +'" class="bk-lb">'+esc(bk(tr.book))+'</text>';
    }
  });
  if(cons.length>1){
    out+='<path d="'+path(cons)+'" fill="none" stroke="#8C877E" stroke-width="1.6"/>'
      +'<text x="'+(X(cons[cons.length-1][0])+4)+'" y="'
      +(Y(cons[cons.length-1][1])-6)+'" class="fair-lb" fill="#8C877E">CONS</text>';
  }
  /* detected moves pinned where they happened */
  (opts.marks||[]).forEach(function(m){
    var t=Date.parse(m.observed_at)/1000; if(t<t0||t>t1) return;
    var ref=cons.length>1?cons:cutpts(traces[0].pts);
    var near=ref.reduce(function(a,p){
      return Math.abs(p[0]-t)<Math.abs(a[0]-t)?p:a;},ref[0]);
    out+='<g><circle cx="'+X(t)+'" cy="'+Y(near[1])+'" r="3.2" fill="#E8B04B">'
      +'<title>'+esc(m.detail||"detected move")+'</title></circle></g>';
  });
  out+='</svg>';
  function lab(t){return new Date(t*1000).toLocaleString([],
    {weekday:"short",hour:"numeric"});}
  return '<div class="tml">'+out
    +'<div class="ax"><span class="tl">'+lab(t0)+'</span>'
    +'<span class="tl">'+(mkt.unit||"implied probability, pts").toUpperCase()
    +(multi?' · <b>'+traces.length+' BOOKS</b> + CONSENSUS':' · SINGLE BOOK')+'</span>'
    +'<span class="tl">'+lab(t1)+'</span></div></div>';
}


/* ---------- analyst answer renderer ----------
   The model writes markdown-ish text; raw asterisks are not an instrument.
   Escape FIRST, then transform — the model's output is data, never markup.
   Odds and point-gains get the desk's numeric treatment so the numbers read
   the way they do everywhere else on the site. */
function answer(text){
  var t=esc(String(text||""));
  t=t.replace(/\*\*([^*\n]+)\*\*/g,"<b>$1</b>");
  /* signed 2-4 digit figures are prices; "x.xx pts" is a gain */
  t=t.replace(/([+\u2212-]\d{2,4})(?![\d.])/g,'<span class="od">$1</span>');
  /* color follows the sign — a negative edge painted green would be the
     renderer editorializing */
  t=t.replace(/((?:[+\u2212-])?\d+(?:\.\d+)?\s?(?:pts|points))/gi,function(_,g){
    return '<span class="'+(/^[\u2212-]/.test(g)?"gnd":"gn")+'">'+g+"</span>";});
  var out=[],ul=false;
  t.split(/\n/).forEach(function(ln){
    var m=ln.match(/^\s*[-\u2022]\s+(.*)$/);
    if(m){ if(!ul){out.push("<ul>");ul=true;} out.push("<li>"+m[1]+"</li>"); return; }
    if(ul){out.push("</ul>");ul=false;}
    if(ln.trim()==="") out.push('<span class="brk"></span>');
    else out.push("<p>"+ln+"</p>");
  });
  if(ul) out.push("</ul>");
  return out.join("");
}

/* An instrument readout for one board event: per-side price rows and the
   deck spectrum for the side with the widest gap. Deterministic — built from
   board.json, so the visual half of an answer can never be hallucinated. */
function eventCard(ev,label){
  var best=ev.sides.slice().sort(function(a,b){return (b.gain_pts||0)-(a.gain_pts||0);})[0];
  var single=(ev.n_books||0)<2;
  var rows=ev.sides.map(function(sd){
    return '<div class="kv"><span class="k">'+esc(sd.name)+'</span>'
      +'<span class="v n">'+(single?"":'<span class="up">')+am(sd.best_price)
      +(single?"":"</span>")+' <span style="color:var(--dim);font-size:10.5px">'
      +bk(sd.best_book)+'</span>'
      +' <span style="color:var(--dim)">· FAIR '+am(sd.fair_price)+'</span>'
      +(sd.gain_pts!=null&&!single?' <span class="up">'+pts(sd.gain_pts)+' PTS</span>':"")
      +'</span></div>';
  }).join("");
  return '<div class="ans-card">'
    +'<div class="sec-h" style="margin-bottom:6px"><span class="tl">'
    +esc(label||"THE NUMBERS")+' · '+esc(ev.away).toUpperCase()+' AT '
    +esc(ev.home).toUpperCase()+'</span>'
    +'<a class="more tl" href="/game?e='+encodeURIComponent(ev.id)+'">FULL ANALYSIS →</a></div>'
    +rows
    +spectrum({quotes:best.quotes,fairProb:best.fair_prob,fairPrice:best.fair_price,
      label:"Prices for "+best.name})
    +'</div>';
}

/* ---------- ranked feed row ---------- */
function feedRow(i,hl,sub,meta,href){
  var tag=href?'a href="'+esc(href)+'"':'div';
  return '<'+tag+' class="mv-row"><span class="mv-rank n">'
    +String(i+1).padStart(2,"0")+'</span>'
    +'<span><span class="mv-hl">'+hl+'</span>'
    +'<span class="mv-sub">'+sub+'</span></span>'
    +'<span class="mv-meta">'+meta+'</span></'+(href?'a':'div')+'>';
}


/* ---------- pick-engine helpers ---------- */
/* entitlement probe; resolves {pro:bool}. Never throws, fails to not-pro.
   Nothing grants that entitlement any more — the checkout was removed on
   2026-08-22 — so this answers false for everyone. Kept because /api/picks
   still honours a comped cookie and this is the only way to read one. */
function me(){
  return fetch("/api/me",{cache:"no-store"}).then(function(r){return r.json();})
    .catch(function(){return {pro:false};});
}
/* a CLV chip: green beat the close, red lost to it, dim n/a with a reason */
function clvChip(v,reason){
  if(v==null) return '<span class="clv na" title="'+esc(reason||"no verified close")
    +'">CLV ·</span>';
  var cls=v>0?"pos":v<0?"neg":"na";
  return '<span class="clv '+cls+'">CLV '+pts(v)+'</span>';
}


/* ---------- the populations block ----------
   Three DIFFERENT samples get quoted on this site and they must never be
   allowed to blur into one headline number — that blur is the exact flaw
   that makes a competitor's "1,297 tracked / 175 published" unanswerable.
   Each row states its own n, its own date range, and its own provenance. */
function populations(el){
  Promise.all([
    fetch("/data/figures.json",{cache:"no-store"}).then(function(r){return r.json();}),
    fetch("/data/pickengine-record.json",{cache:"no-store"})
      .then(function(r){return r.ok?r.json():null;}).catch(function(){return null;})
  ]).then(function(x){
    var f=x[0], rec=x[1];
    var be=(f.breakeven_ats*100).toFixed(2)+"%";
    function row(name,prov,res,note){
      if(!res) return "";
      var pct=(res.ats_pct*100).toFixed(1)+"%";
      var beats=res.ats_pct>=f.breakeven_ats;
      return '<tr><td class="l"><b>'+esc(name)+'</b><small>'+esc(prov)+'</small></td>'
        +'<td>'+res.n+'</td><td>'+esc(res.ats_record)+'</td>'
        +'<td class="'+(beats?"up":"dn")+'">'+pct+'</td>'
        +'<td class="dim">'+esc(note||"")+'</td></tr>';
    }
    var live=rec&&rec.independent_record?rec.independent_record:null;
    var liveN=0;
    if(rec) (rec.weeks||[]).forEach(function(w){ if(!w.rehearsal) liveN+=(w.n_settled||0); });
    var html='<table><thead><tr><th class="l">SAMPLE</th><th>N</th>'
      +'<th>RECORD</th><th>ATS</th><th class="l">WHAT IT IS</th></tr></thead><tbody>'
      +row("Backtest A", f.evaluation_a.provenance,
           f.evaluation_a.results.independent, "walk-forward, weaker line source")
      +row("Backtest B", f.evaluation_b.provenance,
           f.evaluation_b.results.independent, "walk-forward, real consensus closes")
      +'<tr><td class="l"><b>Live sealed slates</b><small>committed before kickoff, '
      +'graded in public</small></td><td>'+liveN+'</td><td>'+(live||"·")+'</td>'
      +'<td class="dim">'+(live?"":"·")+'</td>'
      +'<td class="dim">'+(liveN?"the only sample that was pre-committed"
        :"nothing settled yet — first grade lands after Week 1")+'</td></tr>'
      +'</tbody></table>';
    el.innerHTML='<div class="itab"><div class="scr">'+html+'</div></div>'
      +'<p class="note">Three different samples, three different denominators. '
      +'Break-even is '+be+'; no sample clears it. The backtests are historical '
      +'and were never wagered; the live slates are pre-committed and unfiltered '
      +'— every game on the slate, no star tier, no edge threshold, no betting '
      +'card. Ask any service showing you a record which bets are in their '
      +'tracker but not in their published picks, and when that filter was chosen.</p>';
  }).catch(function(){ el.innerHTML='<p class="note">Figures unavailable.</p>'; });
}

/* ---------- ago ticker ---------- */
function tick(){
  [].forEach.call(document.querySelectorAll("[data-ago]"),function(el){
    el.textContent=ago(el.getAttribute("data-ago"));});
}
setInterval(function(){
  if(document.querySelector("[data-ago]")) tick();
},15000);

window.Desk={tabs:tabs,esc:esc,timeline:timeline,answer:answer,eventCard:eventCard,me:me,populations:populations,clvChip:clvChip,reduced:reduced,land:land,swap:swap,go:go,embedded:EMBEDDED,am:am,implied:implied,pct:pct,pts:pts,ago:ago,when:when,
  bk:bk,mount:mount,stack:stack,sportRail:sportRail,load:load,feedState:feedState,
  connecting:connecting,spectrum:spectrum,feedRow:feedRow,tick:tick};
})();
