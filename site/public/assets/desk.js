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
var NAV=[
  {href:"/desk",        key:"market",  label:"MARKET"},
  {href:"/props",       key:"props",   label:"PROPS"},
  {href:"/edges",       key:"movement",label:"MOVEMENT"},
  {href:"/research",    key:"research",label:"RESEARCH"},
  {href:"/trust",       key:"ledger",  label:"LEDGER"},
  {href:"/methodology", key:"method",  label:"METHODOLOGY"}
];
function header(page){
  return '<header class="hd"><div class="wrap">'
    +'<div class="hd-r1">'
    +'<a class="brand" href="/desk"><span class="mk"></span><b>SOOTH</b>'
    +'<span class="sb">Sports Intelligence</span></a>'
    +'<span class="hd-spacer"></span>'
    +'<nav class="hd-links" aria-label="Sections">'
    +NAV.map(function(n){return '<a href="'+n.href+'"'
      +(n.key===page?' aria-current="page"':'')+'>'+n.label+'</a>';}).join("")
    +'</nav>'
    +'<a class="hd-cta" href="/subscribe">PRO</a>'
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
    +'<div class="links"><a href="/methodology">Methodology</a>'
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
  el.innerHTML=SPORTS.map(function(s){
    var on=!!live[s.k];
    return '<button class="sp" role="tab" data-sp="'+s.k+'"'
      +(s.k===active?' aria-selected="true"':' aria-selected="false"')+'>'
      +'<span class="d'+(on?"":" off")+'"></span>'+s.l
      +(on?'<span class="c n">'+counts[s.k]+'</span>':'')
      +'</button>';}).join("");
  el.addEventListener("click",function(e){
    var b=e.target.closest(".sp"); if(b&&onpick) onpick(b.dataset.sp);});
}
function mount(page){
  document.body.insertAdjacentHTML("afterbegin",header(page));
  document.body.insertAdjacentHTML("beforeend",footer());
}

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
  var W=opts.width||860, H=88, PAD=44, TR=52;
  function X(p){return PAD+((p-lo)/(hi-lo))*(W-2*PAD);}
  var out='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'
    +esc(opts.label||"Sportsbook prices on one scale")+'">';
  out+='<line class="track" x1="'+PAD+'" y1="'+TR+'" x2="'+(W-PAD)+'" y2="'+TR+'"/>';
  /* fair anchor */
  if(opts.fairProb!=null){
    var fx=X(opts.fairProb);
    out+='<line class="fair" x1="'+fx+'" y1="'+(TR-30)+'" x2="'+fx+'" y2="'+(TR+22)+'"/>'
      +'<text class="fair-lb" x="'+fx+'" y="'+(TR-36)+'" text-anchor="middle">FAIR</text>'
      +(opts.fairPrice!=null?'<text class="fair-pr" x="'+fx+'" y="'+(TR+38)
        +'" text-anchor="middle">'+esc(am(opts.fairPrice))+'</text>':'');
  }
  /* markers — lowest implied = biggest payout = the best number */
  var bestIp=cl[0].ip, lastX=-999, lvl=0;
  cl.forEach(function(c){
    var x=X(c.ip), best=c.ip===bestIp && cl.length>1;
    lvl=(x-lastX<46)?(1-lvl):0; lastX=x;           /* stagger tight labels */
    var yPr=lvl? TR-30 : TR-16, yBk=lvl? TR+30 : TR+18;
    var books=c.books.slice(0,2).join("·")+(c.books.length>2?" +"+(c.books.length-2):"");
    out+='<g'+(best?' class="g-best"':'')+'>'
      +'<rect class="bk'+(best?" best":"")+'" x="'+(x-2.5)+'" y="'+(TR-5)
        +'" width="5" height="10" rx="1"/>'
      +'<text class="bk-pr" x="'+x+'" y="'+yPr+'" text-anchor="middle">'
        +esc(am(c.price))+'</text>'
      +'<text class="bk-lb" x="'+x+'" y="'+yBk+'" text-anchor="middle">'
        +esc(books)+'</text></g>';
  });
  out+='</svg>';
  var range=(cl.length>1)?((cl[cl.length-1].ip-cl[0].ip)*100):0;
  var capL=opts.caption!=null?opts.caption:
    (cl.length>1
      ?'<span class="tl">RANGE <b>'+range.toFixed(2)+' PTS IMPLIED</b> ACROSS <b>'
        +quotes.length+' BOOKS</b></span>'
      :'<span class="tl">SINGLE BOOK — NO MARKET WIDTH TO SHOW</span>');
  return '<div class="spec"><div class="spec-scroll">'+out+'</div>'
    +'<div class="spec-cap">'+capL
    +'<span class="tl">'+esc(opts.right||"")+'</span></div></div>';
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

/* ---------- ago ticker ---------- */
function tick(){
  [].forEach.call(document.querySelectorAll("[data-ago]"),function(el){
    el.textContent=ago(el.getAttribute("data-ago"));});
}
setInterval(tick,15000);

window.Desk={esc:esc,am:am,implied:implied,pct:pct,pts:pts,ago:ago,when:when,
  bk:bk,mount:mount,sportRail:sportRail,load:load,feedState:feedState,
  connecting:connecting,spectrum:spectrum,feedRow:feedRow,tick:tick};
})();
