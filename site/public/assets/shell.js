/* sooth shared shell — injects header + compliant footer, exposes helpers.
   Each page: <body data-page="board"> and <script src="/assets/shell.js" defer></script>.
   One include so nav + legal never drift across pages. */
(function(){
  "use strict";

  // One canonical nav for the whole site — mirror this exact set + order in the
  // static shellnav pages (edges/props/tools/trust/engine). Board, Props, Edges
  // are the data views; Predictor + Ask AI the tools; Tools and Trust are hubs
  // that reach the rest (Record/Method/Verify/Guide/Ledger/Gamelog + calculators).
  var NAV=[
    {href:"/",          key:"board",     label:"Board"},
    {href:"/props",     key:"props",     label:"Props"},
    {href:"/edges",     key:"edges",     label:"Edges"},
    {href:"/predictor", key:"predictor", label:"Predictor"},
    {href:"/ask",       key:"ask",       label:"Ask AI"},
    {href:"/tools",     key:"tools",     label:"Tools"},
    {href:"/trust",     key:"trust",     label:"Trust"}
  ];

  var MARK=
    '<svg viewBox="0 0 32 32" aria-hidden="true">'
    +'<circle cx="16" cy="16" r="13" fill="none" stroke="#333B4D" stroke-width="2.5"/>'
    +'<path d="M16 6 A10 10 0 0 1 26 16" fill="none" stroke="#22E5A0" stroke-width="2.5" stroke-linecap="round"/>'
    +'<circle cx="16" cy="16" r="2.6" fill="#22E5A0"/></svg>';

  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}

  // signed american-odds / points: +130, -155, 0 as "0"
  function sig(n,dp){
    if(n==null||isNaN(n))return "·";
    var v=dp==null?n:Number(n).toFixed(dp);
    return (Number(n)>0?"+":"")+v;
  }

  // "41s ago" / "3m ago" / "2h ago" from an ISO string
  function since(iso){
    var t=Date.parse(iso); if(isNaN(t))return "—";
    var s=Math.max(0,Math.round((Date.now()-t)/1000));
    if(s<60)return s+"s ago";
    if(s<3600)return Math.floor(s/60)+"m ago";
    if(s<86400)return Math.floor(s/3600)+"h ago";
    return Math.floor(s/86400)+"d ago";
  }

  function two(n){return (n<10?"0":"")+n;}
  // live UTC clock into an element, ticking each second
  function startClock(el){
    if(!el)return;
    function tick(){
      var d=new Date();
      el.textContent=two(d.getUTCHours())+":"+two(d.getUTCMinutes())+":"+two(d.getUTCSeconds())+" UTC";
    }
    tick(); setInterval(tick,1000);
  }
  // live "updated Xs ago" into an element from a fixed ISO timestamp
  function startAgo(el,iso){
    if(!el)return;
    function tick(){el.textContent=since(iso);}
    tick(); setInterval(tick,1000);
  }

  function header(active){
    var nav=NAV.map(function(n){
      var cur=n.key===active?' aria-current="page"':"";
      return '<a href="'+n.href+'"'+cur+'>'+esc(n.label)+'</a>';
    }).join("");
    return '<header class="hd"><div class="hd-in">'
      +'<a class="brand" href="/"><span>'+MARK+'</span><b>sooth<span class="tld">.bet</span></b></a>'
      +'<nav class="hd-nav" aria-label="Primary">'+nav+'</nav>'
      +'<a class="hd-cta" href="/subscribe.html">Subscribe</a>'
      +'</div></header>';
  }

  function footer(){
    return '<footer class="ft"><div class="wrap">'
      +'<p><b>Sooth is an odds analysis tool. Not advice. Not a sportsbook.</b> '
      +'We do not take, place or facilitate wagers, and we hold no customer funds. '
      +'We are not affiliated with any league, team or sportsbook. Prices are what '
      +'books showed when last read and move constantly.</p>'
      +'<p>Past results do not indicate future results. 21+, where lawful. '
      +'If gambling is causing harm, call the National Problem Gambling Helpline '
      +'<b class="help">1-800-522-4700</b>, available 24 hours.</p>'
      +'<div class="links">'
      +'<a href="/record.html">Record</a>'
      +'<a href="/verify.html">Verify</a>'
      +'<a href="/methodology.html">Methodology</a>'
      +'<a href="/disclaimers.html">Disclaimers</a>'
      +'</div></div></footer>';
  }

  // ponytail: favicon + theme-color injected here so all pages get it from one
  // file. SVG favicon is browser-fetched, not needed by link-unfurlers (those
  // read the static og:image); add a .ico only if legacy Safari ever matters.
  function headTags(){
    if(document.querySelector('link[rel="icon"]'))return;
    document.head.insertAdjacentHTML("beforeend",
      '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">'
      +'<meta name="theme-color" content="#08090D">');
  }

  // limited-time promo: everything is free until Sept 1. One line, all pages.
  function promoBar(){
    return '<div class="promo" role="note">Everything is <b>free until September 1</b>'
      +' — every tool, no card needed. <a href="/">Open the board →</a></div>';
  }

  function mount(){
    headTags();
    var page=document.body.getAttribute("data-page")||"";
    // header first, unless a page opts out with data-shell="footer-only"
    var mode=document.body.getAttribute("data-shell")||"full";
    if(mode!=="footer-only"){
      document.body.insertAdjacentHTML("afterbegin",header(page));
      document.body.insertAdjacentHTML("afterbegin",promoBar()); // sits above header
    }
    document.body.insertAdjacentHTML("beforeend",footer());
  }

  // public helpers
  window.sooth={esc:esc,sig:sig,since:since,startClock:startClock,startAgo:startAgo};

  if(document.readyState==="loading"){
    document.addEventListener("DOMContentLoaded",mount);
  }else{mount();}
})();
