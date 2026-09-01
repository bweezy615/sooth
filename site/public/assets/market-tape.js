(function(){
"use strict";
if(/[?&]embed=1/.test(location.search)) return;
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function am(n){return n==null?"·":(n>0?"+"+n:String(n));}
function short(name){var p=String(name).split(" ");return p[p.length-1];}
function mount(after,kind){
  if(!after||after.nextElementSibling&&after.nextElementSibling.classList.contains("sooth-tape")) return;
  var host=document.createElement("div");
  host.className="sooth-tape"+(kind?" "+kind:"");
  host.setAttribute("aria-label","Live market tape");
  host.innerHTML='<div class="sooth-tape-empty">READING CURRENT MARKET…</div>';
  after.insertAdjacentElement("afterend",host);
  fetch("/data/board.json",{cache:"no-store"}).then(function(r){if(!r.ok)throw Error(r.status);return r.json();})
    .then(function(board){
      var now=Date.now(), markets=[];
      (board.boards||[]).forEach(function(b){(b.events||[]).forEach(function(e){
        if(Date.parse(e.starts)<=now||!e.sides||!e.sides.length)return;
        var side=e.sides.slice().sort(function(a,c){return(c.gain_pts||0)-(a.gain_pts||0);})[0];
        markets.push({sport:b.sport,e:e,side:side});
      });});
      markets.sort(function(a,b){return(b.side.gain_pts||0)-(a.side.gain_pts||0);});
      host.innerHTML=markets.length?'<nav class="sooth-tape-track">'+markets.slice(0,12).map(function(x){
        return '<a class="sooth-tape-item" href="/game?e='+encodeURIComponent(x.e.id)+'&s='+esc(x.sport)+'">'
          +'<span class="sooth-tape-match"><b>'+esc(short(x.e.away))+' @ '+esc(short(x.e.home))+'</b>'
          +'<span>'+esc(short(x.side.name))+' ML</span></span>'
          +'<span class="sooth-tape-fact"><b>'+esc(am(x.side.fair_price))+'</b><i>Fair</i></span>'
          +'<span class="sooth-tape-fact best"><b>'+esc(am(x.side.best_price))+'</b><i>Best</i></span>'
          +'<span class="sooth-tape-fact gap"><b>'+esc((x.side.gain_pts||0).toFixed(2))+'</b><i>Gap pts</i></span></a>';
      }).join("")+'</nav>':'<div class="sooth-tape-empty">NO UPCOMING MARKET IN THE CURRENT PRICING WINDOW</div>';
    }).catch(function(){host.innerHTML='<div class="sooth-tape-empty">MARKET TAPE UNAVAILABLE</div>';});
}
setTimeout(function(){
  var hd=document.querySelector(".hd"); if(hd) mount(hd,"standard-tape");
  var tb=document.querySelector(".tb"); if(tb) mount(tb,"desktop-tape");
  var mt=document.querySelector(".m-top"); if(mt) mount(mt,"mobile-tape");
},0);
})();
