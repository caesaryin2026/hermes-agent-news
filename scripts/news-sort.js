// Hermes News - sorting, filtering & valuable marking
(function(){
var sk='date',od='desc',cc='all';
var VK='hermes_news_valuable'; // localStorage key

// Load valuable set from localStorage
function loadV(){
  try{ return new Set(JSON.parse(localStorage.getItem(VK)||'[]')); }catch(e){ return new Set(); }
}
function saveV(s){
  localStorage.setItem(VK, JSON.stringify([...s]));
}

// Toggle valuable state for a card
window._newsToggleValuable=function(url){
  var s=loadV();
  if(s.has(url)) s.delete(url); else s.add(url);
  saveV(s);
  // Update visual
  document.querySelectorAll('.card').forEach(function(c){
    var u=c.dataset.url;
    c.classList.toggle('valuable', s.has(u));
    c.querySelector('.vb').textContent=s.has(u)?'\u2B50':'\u2606';
  });
};

// Sort/filter
window._newsSort=function(k){
  document.querySelectorAll('.sb').forEach(function(b){b.classList.remove('a');});
  document.querySelector('.sb[data-k="'+k+'"]').classList.add('a');
  sk=k;r();
};
window._newsToggle=function(){
  od=od==='desc'?'asc':'desc';
  document.getElementById('ob').innerHTML=od==='desc'?'\u25bc \u964d\u5e8f':'\u25b2 \u5347\u5e8f';
  r();
};
window._newsFilter=function(c){
  document.querySelectorAll('.fb').forEach(function(b){b.classList.remove('a');});
  var btn=document.querySelector('.fb[data-c="'+c+'"]');
  if(btn) btn.classList.add('a');
  cc=c;r();
};
function r(){
  var cards=[].slice.call(document.getElementById('c').children).filter(function(c){return c.classList.contains('card');});
  var val=loadV();
  // Apply valuable visual
  cards.forEach(function(c){c.classList.toggle('valuable', val.has(c.dataset.url));});

  if(cc==='valuable'){
    // Show only valuable cards
    cards.forEach(function(c){c.style.display=val.has(c.dataset.url)?'':'none';});
    var f=cards.filter(function(c){return val.has(c.dataset.url);});
  }else{
    cards.forEach(function(c){c.style.display=cc==='all'||c.dataset.cat===cc?'':'none';});
    var f=cc==='all'?cards:cards.filter(function(c){return c.dataset.cat===cc;});
  }
  var o=od==='desc'?-1:1;
  f.sort(function(a,b){
    var va,vb;
    if(sk==='date'){va=new Date(a.dataset.date).getTime();vb=new Date(b.dataset.date).getTime();}
    else{va=parseInt(a.dataset[sk])||0;vb=parseInt(b.dataset[sk])||0;}
    return (va-vb)*o;
  });
  var p=document.getElementById('c');
  f.forEach(function(c){p.appendChild(c);});
  var n=document.getElementById('nc');
  if(n)n.textContent='\u663e\u793a '+f.length+' \u7bc7\u62a5\u9053';
  // Update valuable count
  var vc=document.getElementById('vc');
  if(vc) vc.textContent=val.size;
}

// Init: apply valuable visual on load
(function init(){
  var val=loadV();
  document.querySelectorAll('.card').forEach(function(c){
    var u=c.dataset.url;
    if(val.has(u)) c.classList.add('valuable');
    c.querySelector('.vb').textContent=val.has(u)?'\u2B50':'\u2606';
  });
})();

var ftd=document.getElementById('ftd');
if(ftd)ftd.textContent='\u66f4\u65b0\u4e8e '+new Date().toLocaleString('zh-CN');
})();
