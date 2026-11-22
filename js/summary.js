/* Landing page: one glance per market. Figures are read from the official files. */
let ENERGY = null, CATTLE = null, PROGRESS = null, CGC = null;

function signed(v, d){
  if(v===null || v===undefined || isNaN(v)) return na();
  const n = Number(v.toFixed(d));
  if(n===0) return (0).toFixed(d);
  return (n>0?'+':'') + n.toFixed(d);
}
function dir(v){
  if(v===null || v===undefined || isNaN(v) || Number(v.toFixed(1))===0) return '';
  return v>0 ? 'up' : 'dn';
}
function cell(text, cls){ return `<td class="${cls||''}">${text}</td>`; }

function latestYear(comm, country){
  const c = DATA && DATA[comm] && DATA[comm][country];
  if(!c) return null;
  const ys = Object.keys(c).filter(y=>/^\d{4}$/.test(y)).sort();
  return ys.length ? ys[ys.length-1] : null;
}
function rec(comm, country, year){
  const c = DATA && DATA[comm] && DATA[comm][country];
  return (c && year) ? c[year] : null;
}
function stuOf(r, world){
  if(!r || r.es==null || r.dc==null) return null;
  let den = r.dc;
  if(!world){
    if(r.ex==null) return null;
    den = r.dc + r.ex;
  }
  return den>0 ? (r.es/den)*100 : null;
}
function stuPair(comm, country, world){
  const y = latestYear(comm, country);
  if(!y) return {cur:null, yoy:null, mom:null};
  const ys = Object.keys(DATA[comm][country]).filter(k=>/^\d{4}$/.test(k)).sort();
  const prev = ys.length>1 ? ys[ys.length-2] : null;
  const cur = stuOf(rec(comm, country, y), world);
  const ly = prev ? stuOf(rec(comm, country, prev), world) : null;
  const p = rec(comm, country, y) && rec(comm, country, y)._p;
  const prior = p ? stuOf(p, world) : null;
  return {
    cur: cur,
    yoy: (cur!=null && ly!=null) ? cur-ly : null,
    mom: (cur!=null && prior!=null) ? cur-prior : null
  };
}
function pct1(v){ return v==null ? na() : v.toFixed(1)+'%'; }

const SUM_ROWS = [
  {label:'Wheat', page:'usda', comm:'Wheat', flow:'ALL WHEAT', crop:'Wheat'},
  {label:'Corn', page:'usda', comm:'Corn', flow:'CORN - UNMILLED', crop:'Corn'},
  {label:'Soybeans', page:'usda', comm:'Soybeans', flow:'SOYBEANS', crop:'Soybeans'},
  {label:'Canola', page:'usda', comm:'Rapeseed/Canola', flow:null, crop:'Canola', cgc:true},
  {label:'Soybean oil', page:'usda', comm:'Soybean Oil', flow:'SOYBEAN OIL', crop:null},
  {label:'Soybean meal', page:'usda', comm:'Soybean Meal', flow:'SOYBEAN CAKE AND MEAL', crop:null},
];

function flowYoY(name){
  const t = name && EXPORTS_DATA && EXPORTS_DATA.commodities && EXPORTS_DATA.commodities[name] && EXPORTS_DATA.commodities[name].total;
  return t ? t.yoy_total_commitment_pct : null;
}
function cgcFlow(){
  const h = CGC && CGC.headline && CGC.headline.grains && CGC.headline.grains.canola;
  if(!h || h.exp_cy==null || h.exp_ya==null || !h.exp_ya) return null;
  return (h.exp_cy/h.exp_ya - 1) * 100;
}
function cropDelta(group){
  const us = PROGRESS && PROGRESS.us;
  if(!us || !us.rows) return null;
  const rows = us.rows.filter(r => cropGroupName(r.crop)===group);
  if(!rows.length) return null;
  const harvested = rows.find(r => r.metric==='harvested' && r.current>5 && r.current<99);
  const cond = rows.find(r => r.metric==='condition_ge');
  const planted = rows.find(r => r.metric==='planted' && r.current>1 && r.current<99);
  const row = [harvested, cond, planted].find(r => r && r.current!=null && r.avg5!=null) || null;
  if(!row) return null;
  const label = row.metric==='condition_ge' ? 'cond' : row.metric.slice(0,4);
  return {text: label+' '+(row.current-row.avg5>=0?'+':'')+(Math.round((row.current-row.avg5)*10)/10), v: row.current-row.avg5};
}
function cropGroupName(name){
  const c = String(name||'').toLowerCase();
  if(/wheat/.test(c)) return 'Wheat';
  if(/corn/.test(c)) return 'Corn';
  if(/soy/.test(c)) return 'Soybeans';
  if(/canola|rapeseed/.test(c)) return 'Canola';
  return null;
}

let SIGNALS = null;
function renderSummary(){
  const root = document.getElementById('summary-root');
  if(!root) return;
  const draw = ()=>{
    if(!SIGNALS || !SIGNALS.sections){
      root.innerHTML = `<p class="legend-line">${na()}</p>`;
      return;
    }
    const meta = document.getElementById('summary-meta');
    if(meta) meta.textContent = '';
    let html = freshnessPanel(SIGNALS.freshness || []);
    SIGNALS.sections.forEach(section=>{
      html += `<div class="sec-hdr"><span>${section.title}</span></div>`;
      html += signalTable(section);
      html += figureStrip(section);
    });
    html += rulesBlock(SIGNALS.rules || []);
    root.innerHTML = html;
    bindSignals(root);
  };
  if(SIGNALS){ draw(); return; }
  fetch('data/signals.json').then(r=>r.ok?r.json():null).then(d=>{ SIGNALS = d; draw(); }).catch(()=>draw());
}
function freshnessPanel(rows){
  if(!rows.length) return '';
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Freshness</span></div>`;
  html += `<table class="term-table summary-table"><thead><tr><th>Feed</th><th>As of</th><th>Last run</th><th>Status</th></tr></thead><tbody>`;
  rows.forEach(row=>{
    const asOf = row.as_of || na();
    let status = 'OK';
    let cls = 'up';
    if(!row.as_of){ status = 'stale'; cls = 'dn'; }
    else if(row.cadence_days!=null){
      const age = (Date.now() - Date.parse(row.as_of+'T00:00:00Z'))/86400000;
      if(age > row.cadence_days){ status = 'stale'; cls = 'dn'; }
    }
    html += `<tr><td>${row.feed}</td><td>${asOf}</td><td>${row.last_run || na()}</td><td class="${cls}">${status}</td></tr>`;
  });
  html += `</tbody></table></div>`;
  return html;
}
function signalTable(section){
  const cols = section.columns || [];
  const groups = section.groups || [];
  const widths = [1.6, ...cols.map(()=>1)];
  let html = `<div class="panel"><table class="term-table summary-table sig-table">${fitColgroup(widths)}<thead>`;
  if(groups.length){
    html += `<tr><th rowspan="2">Market</th>`;
    groups.forEach(g=>{ html += `<th colspan="${g.ids.length}">${g.label}</th>`; });
    html += `</tr><tr>`;
    cols.forEach(col=>{ html += `<th>${col.label}</th>`; });
    html += `</tr>`;
  } else {
    html += `<tr><th>Market</th>`;
    cols.forEach(col=>{ html += `<th>${col.label}</th>`; });
    html += `</tr>`;
  }
  html += `</thead><tbody>`;
  (section.rows||[]).forEach(row=>{
    html += `<tr><td class="jump" data-page="${row.page||''}" data-comm="${row.comm||''}">${row.label}</td>`;
    cols.forEach(col=>{
      const sig = (row.signals||{})[col.id] || {};
      const cls = sig.state ? `sig sig-${sig.state}` : 'sig';
      const text = sig.text || na();
      html += `<td class="${cls}"><button type="button" class="sig-hit" data-detail="${escapeAttr(sig.detail||sig.reason||'')}" data-rule="${escapeAttr(ruleText(sig.rule_id))}" data-asof="${escapeAttr(sig.as_of||'')}">${text}</button></td>`;
    });
    html += `</tr>`;
  });
  html += `</tbody></table></div>`;
  return html;
}
function figureStrip(section){
  const rows = section.rows || [];
  const labels = [];
  rows.forEach(row=>{ (row.figures||[]).forEach(fig=>{ if(!labels.includes(fig.label)) labels.push(fig.label); }); });
  const sectionFigs = section.figures || [];
  if(!labels.length && !sectionFigs.length) return '';
  let html = `<details class="rules"><summary>Key figures</summary><table class="term-table summary-table"><thead><tr><th>Market</th>`;
  if(labels.length){
    labels.forEach(label=>{ html += `<th>${label}</th>`; });
    html += `</tr></thead><tbody>`;
    rows.forEach(row=>{
      html += `<tr><td>${row.label}</td>`;
      labels.forEach(label=>{
        const fig = (row.figures||[]).find(f=>f.label===label);
        html += `<td>${fig?fig.value:na()}</td>`;
      });
      html += `</tr>`;
    });
  } else {
    sectionFigs.forEach(fig=>{ html += `<th>${fig.label}</th>`; });
    html += `</tr></thead><tbody><tr><td>${section.title}</td>`;
    sectionFigs.forEach(fig=>{ html += `<td>${fig.value}</td>`; });
    html += `</tr>`;
  }
  html += `</tbody></table></details>`;
  return html;
}
function rulesBlock(rules){
  let html = `<details class="rules"><summary>Rules</summary>`;
  rules.forEach(rule=>{ html += `<p><b>${rule.id}</b> ${rule.text}</p>`; });
  html += `</details>`;
  return html;
}
function ruleText(id){
  const rule = (SIGNALS && SIGNALS.rules || []).find(r=>r.id===id);
  return rule ? rule.text : '';
}
function escapeAttr(value){
  return String(value||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
}
function bindSignals(root){
  let pop = document.getElementById('sig-pop');
  if(!pop){
    pop = document.createElement('div');
    pop.id = 'sig-pop';
    pop.hidden = true;
    document.body.appendChild(pop);
  }
  const close = ()=>{ pop.hidden = true; };
  root.querySelectorAll('button.sig-hit').forEach(btn=>{
    const show = ()=>{
      const asof = btn.dataset.asof ? `As of ${btn.dataset.asof}. ` : '';
      pop.innerHTML = `<div>${btn.dataset.detail||na()}</div><div class="legend-line">${asof}${btn.dataset.rule||''}</div>`;
      pop.hidden = false;
      const rect = btn.getBoundingClientRect();
      const width = Math.min(280, window.innerWidth - 16);
      pop.style.width = width + 'px';
      let left = rect.left;
      if(left + width > window.innerWidth - 8) left = window.innerWidth - width - 8;
      pop.style.left = Math.max(8, left) + 'px';
      pop.style.top = Math.min(rect.bottom + 6, window.innerHeight - 8) + 'px';
    };
    btn.addEventListener('mouseenter', show);
    btn.addEventListener('mouseleave', close);
    btn.addEventListener('focus', show);
    btn.addEventListener('blur', close);
    btn.addEventListener('click', ev=>{ ev.stopPropagation(); if(pop.hidden) show(); else close(); });
  });
  root.querySelectorAll('td.jump').forEach(td=>{
    td.addEventListener('click', ()=>{ if(td.dataset.page) openPage(td.dataset.page, td.dataset.comm||undefined); });
  });
  if(!pop.dataset.bound){
    pop.dataset.bound = '1';
    pop.addEventListener('mouseleave', close);
    document.addEventListener('keydown', ev=>{ if(ev.key==='Escape') close(); });
    document.addEventListener('click', ev=>{ if(!pop.contains(ev.target)) close(); });
  }
}

function cattleStale(){
  const of = CATTLE && CATTLE.on_feed && CATTLE.on_feed[CATTLE.on_feed.length-1];
  if(!of) return null;
  const stamp = of.released ? Date.parse(of.released) : (of.as_of ? Date.parse(of.as_of+'T00:00:00Z') : NaN);
  if(!isFinite(stamp)) return null;
  // The report is monthly. Forty days from the release is past the next one.
  return (Date.now()-stamp)/86400000 > 40;
}
function energyStatus(){
  const gen = ENERGY && ENERGY.generated_at;
  const d = gen ? parseStamp(gen) : null;
  const stale = d ? (Date.now()-d.getTime())/86400000 > 10 : null;
  return {parts:['Last fetch: '+fmtStamp(gen)], stale: stale};
}

function loadGlance(){
  const grab = p => fetch(p).then(r=>r.ok?r.json():null).catch(()=>null);
  Promise.all([
    grab('data/energy.json'),
    grab('data/cattle.json'),
    grab('data/us.json'),
    grab('data/cgc.json'),
  ]).then(([e,c,u,g])=>{
    ENERGY = e; CATTLE = c; CGC = g;
    PROGRESS = PROGRESS || {};
    if(u) PROGRESS.us = u;
    if(typeof renderSummary==='function' && usdaReady && cftcReady && exportsReady) renderSummary();
  });
}
loadGlance();
