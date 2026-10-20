(()=>{
const d=document,r=d.documentElement,$=(s,p=d)=>p.querySelector(s),$$=(s,p=d)=>[...p.querySelectorAll(s)],
el=(t,p,...k)=>{const e=d.createElement(t);Object.assign(e,p);e.append(...k);return e},
N="http://www.w3.org/2000/svg",u=$("use"),sp=u?u.getAttribute("href"):"",
ic=n=>{if(!sp)return"";const s=d.createElementNS(N,"svg"),e=d.createElementNS(N,"use");s.setAttribute("class","i");s.setAttribute("aria-hidden","true");e.setAttribute("href",sp.split("#")[0]+"#"+n);s.append(e);return s},
live=$("#live"),say=t=>{live.textContent="";setTimeout(()=>{live.textContent=t},60)},
store=(k,v)=>{try{return v===undefined?localStorage.getItem(k):localStorage.setItem(k,v)}catch{}};

/* theme: system, light, dark */
const V=["","light","dark"],I=["monitor","sun","moon"],tb=el("button",{className:"theme",type:"button"});
let ti=Math.max(0,V.indexOf(r.dataset.theme||""));
const paint=()=>{const n="Theme: "+(V[ti]||"system");tb.replaceChildren(ic(I[ti]));tb.title=n;tb.setAttribute("aria-label",n);return n};
paint();
tb.onclick=()=>{ti=(ti+1)%3;V[ti]?r.dataset.theme=V[ti]:delete r.dataset.theme;store("tk-theme",V[ti]);say(paint())};
const slot=$("[data-theme-slot]");slot&&slot.replaceWith(tb);

/* copy, link and share buttons */
const btn=(label,icon,fn)=>{const b=el("button",{type:"button",className:"btn"},ic(icon),ic("check"),label);b.onclick=()=>fn(b);return b},
copy=(b,t,ok)=>navigator.clipboard.writeText(t).then(()=>{b.dataset.state="done";say(ok);setTimeout(()=>delete b.dataset.state,1800)},()=>say("Copy failed")),
canon=$("link[rel=canonical]"),tools=$("[data-tools]");
if(tools){
const q=$$(".hero blockquote span").map(s=>s.textContent),sha=$("#sha"),m=location.pathname.match(/kural\/(\d+)/);
if(q.length)tools.append(btn("Copy kural","copy",b=>copy(b,q.join("\n")+"\n— Thirukkural "+m[1],"Kural copied")));
canon&&tools.append(btn("Copy link","link",b=>copy(b,canon.href,"Link copied")));
sha&&tools.append(btn("Copy hash","copy",b=>copy(b,sha.textContent,"Hash copied")));
navigator.share&&canon&&tools.append(btn("Share","share-2",()=>navigator.share({title:d.title,url:canon.href}).catch(()=>0)));
}
$$("[data-copy]").forEach(w=>w.append(btn("Copy","copy",b=>copy(b,$("code",w).textContent,"Copied"))));
{const m=location.pathname.match(/kural\/(\d+)/);m&&store("tk-last",m[1])}

/* translations as tabs; every one is shown without scripts */
const fg=$$(".tr figure");
if(fg.length>1){
const bar=el("div",{className:"seg",role:"tablist"}),tabs=fg.map((f,i)=>{
const t=el("button",{type:"button",role:"tab",id:"t-"+f.id},f.dataset.t);t.setAttribute("aria-controls",f.id);
t.onclick=()=>{pick(i);history.replaceState(null,"","#"+f.id)};
t.onkeydown=e=>{const j=e.key=="ArrowRight"?i+1:e.key=="ArrowLeft"?i-1:-1;if(j>=0&&j<tabs.length){e.preventDefault();pick(j);tabs[j].focus()}};
f.setAttribute("role","tabpanel");f.setAttribute("aria-labelledby",t.id);return t}),
pick=i=>{tabs.forEach((t,j)=>{t.setAttribute("aria-selected",j==i);t.tabIndex=j==i?0:-1;fg[j].hidden=j!=i})},
hash=()=>{const i=fg.findIndex(f=>"#"+f.id==location.hash);pick(i<0?0:i)};
bar.append(...tabs);fg[0].before(bar);hash();addEventListener("hashchange",hash);
}

/* today's kural, or where you stopped */
const td=$("[data-today]");
if(td){const l=+store("tk-last"),n=l>0&&l<=1330?l:Math.floor((Date.now()-new Date().getTimezoneOffset()*6e4)/864e5)%1330+1;
td.append(el("a",{className:"btn",href:"kural/"+n+"/"},(l>0?"Continue at kural ":"Today’s kural ")+n,ic("arrow-right")))}

/* keyboard */
let hd;
const help=()=>{if(!hd){hd=el("dialog",{className:"dlg"},el("h2",{},"Keyboard shortcuts"),...[["← k","Previous page"],["→ j","Next page"],["/","Search"],["?","This help"],["Esc","Close"]].map(([a,b])=>el("p",{},el("kbd",{},a)," "+b)),el("button",{className:"btn",type:"button",onclick:()=>hd.close()},"Close"));d.body.append(hd)}hd.showModal()};
d.addEventListener("keydown",e=>{
if(e.metaKey||e.ctrlKey||e.altKey||e.target.closest("input,textarea,select,[role=tab],[contenteditable]"))return;
const k=e.key,n=k=="ArrowLeft"||k=="k"?"prev":k=="ArrowRight"||k=="j"?"next":"";
if(n){const a=$(`a[rel=${n}]`);a&&a.click()}
else if(k=="/"){const s=$("[data-search]");if(s){e.preventDefault();s.click()}}
else if(k=="?")help();
});

/* search */
const sc=$("[data-search]");
if(sc){let data,dlg,inp,ul;
const base=sc.href.split("#")[0],
run=()=>{const q=inp.value.toLowerCase().replace(/['\u2019]/g,"").replace(/[.,;:!?"()\-\u2013\u2014]/g," ").trim(),t=q.split(/\s+/),o=[],m=(a,e)=>q&&o.length<20&&t.every(w=>(" "+a+" "+e).includes(" "+w));
if(/^\d+$/.test(q)&&q>0&&q<1331)o.push(["kural/"+ +q+"/","Kural "+ +q,""]);
if(data){data.c.forEach(([n,a,e])=>m(a,e)&&o.push(["chapter/"+n+"/","Chapter "+n,a]));data.k.forEach(([n,a,e])=>m(a,e)&&o.push(["kural/"+n+"/",n,a]))}
ul.replaceChildren(...o.map(([h,x,y])=>el("li",{},el("a",{href:base+h},el("b",{},x)," "+y))))};
sc.onclick=e=>{e.preventDefault();
if(!dlg){
inp=el("input",{type:"search",placeholder:"Search kurals and chapters",autocomplete:"off",oninput:run});inp.setAttribute("aria-label","Search");
ul=el("ul",{className:"rows",onkeydown:e=>{const l=e.target.parentElement,n=e.key=="ArrowDown"?l.nextSibling:e.key=="ArrowUp"?l.previousSibling:0;if(n!==0){e.preventDefault();(n?n.firstChild:inp).focus()}}});
inp.onkeydown=e=>{const a=$("a",ul);if(a&&e.key=="Enter")location.assign(a.href);else if(a&&e.key=="ArrowDown"){e.preventDefault();a.focus()}};
dlg=el("dialog",{className:"dlg srch",onclick:e=>e.target==dlg&&dlg.close()},inp,ul);d.body.append(dlg);
fetch(sc.dataset.search).then(r=>r.json()).then(j=>{data=j;run()},()=>say("Search could not load"))}
dlg.showModal();inp.focus()}}

/* pointer glow on cards */
matchMedia("(hover:hover) and (pointer:fine)").matches&&d.addEventListener("pointermove",e=>{
const c=e.target.closest&&e.target.closest(".card");
if(c){const b=c.getBoundingClientRect();c.style.setProperty("--x",e.clientX-b.left+"px");c.style.setProperty("--y",e.clientY-b.top+"px")}
},{passive:true});
})();
