/* Landing page: one glance per market. Figures are read from the official files. */
let ENERGY = null, CATTLE = null, PROGRESS = null, CGC = null;

function na(){ return 'not available'; }
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
  const row = harvested || cond || planted || null;
  if(!row || row.current==null || row.avg5==null) return null;
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

function renderSummary(){
  const root = document.getElementById('summary-root');
  if(!root) return;
  const meta = document.getElementById('summary-meta');
  if(meta) meta.textContent = '';
  const stale = summarySourceStale();
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Grains and oilseeds</span><span class="panel-sub">stocks-to-use, percent</span>${summaryProv()}</div>`;
  html += `<table class="term-table summary-table">${fitColgroup([1.6,1,0.7,0.7,1,0.7,0.7,0.9,0.9])}<thead><tr>
    <th>Market</th><th>US S/U</th><th>yr</th><th>mo</th><th>World S/U</th><th>yr</th><th>mo</th><th>Flow yr</th><th>Season</th>
    </tr></thead><tbody>`;
  SUM_ROWS.forEach(row=>{
    const us = stuPair(row.comm, 'United States', false);
    const worldCountry = row.comm==='Rapeseed/Canola' ? null : 'World';
    const w = worldCountry ? stuPair(row.comm, 'World', true) : {cur:null,yoy:null,mom:null};
    let flow = row.cgc ? cgcFlow() : flowYoY(row.flow);
    const season = row.crop ? cropDelta(row.crop) : null;
    html += `<tr class="jump" data-page="${row.page}" data-comm="${row.comm}"><td>${row.label}</td>`;
    html += cell(pct1(us.cur));
    html += cell(us.yoy==null?na():signed(us.yoy,1)+'pp', dir(us.yoy));
    html += cell(us.mom==null?na():signed(us.mom,1)+'pp', dir(us.mom));
    html += cell(pct1(w.cur));
    html += cell(w.yoy==null?na():signed(w.yoy,1)+'pp', dir(w.yoy));
    html += cell(w.mom==null?na():signed(w.mom,1)+'pp', dir(w.mom));
    html += cell(flow==null?na():signed(flow,1)+'%', dir(flow));
    html += cell(season?season.text:na(), season?dir(season.v):'');
    html += `</tr>`;
  });
  html += `</tbody></table></div>`;

  html += energySummary();
  html += cattleSummary();
  root.innerHTML = html;
  root.querySelectorAll('tr.jump').forEach(tr=>{
    tr.addEventListener('click', ()=>openPage(tr.dataset.page, tr.dataset.comm));
  });
}

function energySummary(){
  const st = energyStatus();
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Energy stocks</span>${provMark(['EIA WPSR Table 1 and Table 4, and the Weekly Natural Gas Storage Report.', ...st.parts, 'The natural gas 5-year average is the figure WNGSR prints. Petroleum 5-year averages are not in these WPSR tables, so they read not available.'], st.stale)}</div>`;
  html += `<table class="term-table summary-table">${fitColgroup([1.8,1.1,0.9,1.1,1,1])}<thead><tr>
    <th>Market</th><th>Stocks</th><th>w/w</th><th>Year ago</th><th>5-yr avg</th><th>vs 5-yr</th></tr></thead><tbody>`;
  const order = ['crude_stocks','gas_stocks','dist_stocks','ng_storage'];
  order.forEach(key=>{
    const s = (ENERGY && ENERGY.series || []).find(x=>x.key===key) || {};
    const d = s.decimals==null?0:s.decimals;
    const vs = s.vs_avg5_pct;
    html += `<tr class="jump" data-page="energy" data-comm="${key}"><td>${s.label||key}</td>`;
    html += cell(s.value==null?na():Number(s.value).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}));
    html += cell(s.change==null?na():signed(s.change,d), dir(s.change));
    html += cell(s.year_ago==null?na():Number(s.year_ago).toLocaleString(undefined,{maximumFractionDigits:d}));
    html += cell(s.avg5==null?na():Number(s.avg5).toLocaleString());
    html += cell(vs==null?na():signed(vs,1)+'%', dir(vs));
    html += `</tr>`;
  });
  html += `</tbody></table></div>`;
  return html;
}

function cattleSummary(){
  const of = CATTLE && CATTLE.on_feed && CATTLE.on_feed[CATTLE.on_feed.length-1];
  const steer = CATTLE && CATTLE.steer;
  const cut = CATTLE && CATTLE.cutout;
  const sl = CATTLE && CATTLE.slaughter;
  const lines = [
    'Cattle on Feed: USDA NASS. Year-ago percent is the percent printed in the report.',
    '5-area live FOB steer and boxed beef: USDA AMS. Slaughter is AMS Actual Slaughter Under Federal Inspection; that report does not print a year-ago or a 5-year average.',
    'Positioning for live cattle and feeder cattle is on the CFTC page.'
  ];
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Cattle</span>${provMark(lines, cattleStale())}</div>`;
  html += `<table class="term-table summary-table">${fitColgroup([1.6,1.3,1.2,1.2])}<thead><tr><th>Reading</th><th>Latest</th><th>Comparison</th><th></th></tr></thead><tbody>`;
  const feed = of && of.on_feed;
  html += cattleRow('On feed', feed?feed.current.toLocaleString()+' (000)':na(), feed?feed.pct_of_year_ago+'% of yr ago':na(), feed?feed.pct_of_year_ago-100:null);
  const pl = of && of.placements;
  html += cattleRow('Placements', pl?pl.current.toLocaleString()+' (000)':na(), pl?pl.pct_of_year_ago+'% of yr ago':na(), pl?pl.pct_of_year_ago-100:null);
  html += cattleRow('FI slaughter', sl?sl.cattle_head.toLocaleString()+' hd':na(), 'year ago not available', null);
  const px = steer && steer.live_fob_steer;
  const pxYa = steer && steer.live_fob_steer_year_ago;
  html += cattleRow('Live FOB steer', px?px.price.toFixed(2):na(), (px&&pxYa)?signed(px.price-pxYa.price,2)+' vs yr ago':na(), (px&&pxYa)?px.price-pxYa.price:null);
  html += cattleRow('Choice cutout', cut?cut.choice.toFixed(2):na(), cut?signed(cut.choice_change,2)+' d/d':na(), cut?cut.choice_change:null);
  html += `</tbody></table></div>`;
  return html;
}
function cattleRow(name, latest, cmp, dirV){
  return `<tr class="jump" data-page="cattle" data-comm=""><td>${name}</td><td>${latest}</td><td class="${dir(dirV)}">${cmp}</td><td></td></tr>`;
}
function cattleStale(){
  const of = CATTLE && CATTLE.on_feed && CATTLE.on_feed[CATTLE.on_feed.length-1];
  if(!of || !of.as_of) return null;
  const age = (Date.now() - new Date(of.as_of+'T00:00:00Z'))/86400000;
  return age > 45;
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
