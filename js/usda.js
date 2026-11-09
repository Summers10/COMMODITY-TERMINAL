/* USDA balances. World rows are only what the file carries from WASDE. */
let usdaSource = 'usda';
const PAST = 5;

function yearList(comm, country){
  const bag = DATA && DATA[comm] && DATA[comm][country];
  if(!bag) return [];
  return Object.keys(bag).filter(y=>/^\d{4}$/.test(y)).sort().slice(-(PAST+1));
}
function allYears(comm){
  const countries = DATA && DATA[comm];
  if(!countries) return [];
  const s = new Set();
  Object.values(countries).forEach(yrs=>Object.keys(yrs).forEach(y=>{ if(/^\d{4}$/.test(y)) s.add(y); }));
  return [...s].sort();
}
function showYears(comm){
  const ys = allYears(comm);
  return ys.slice(-(PAST+1));
}
function numOr(v){ return (v===undefined || v===null || v==='') ? null : v; }
function areaAc(rec, comm){
  if(!rec) return null;
  if(rec.ah_ac!=null) return rec.ah_ac;
  return acresK(numOr(rec.ah));
}
function yieldShown(rec, comm){
  if(!rec) return null;
  if(rec.yl_bu!=null) return rec.yl_bu;
  const yl = numOr(rec.yl);
  if(yl==null) return null;
  if(comm==='Cotton') return null;
  if(NO_BUSHEL_COMMS.has(comm)) return yl;
  return yl * (BU_PER_MT[comm]||36.7437) / ACRES_PER_HA;
}
function vol(rec, key, comm){
  if(!rec) return null;
  return convertVal(numOr(rec[key]), currentUnit, comm);
}
function balanceRows(comm){
  const cotton = comm==='Cotton';
  const lb = NO_BUSHEL_COMMS.has(comm);
  return [
    {k:'area', label: cotton?'Area (1000 ac)':'Area (1000 ac)'},
    {k:'yield', label: cotton?'Yield':(lb?'Yield (lb/ac)':'Yield (bu/ac)'), dec:1},
    {k:'pr', label:'Production'},
    {k:'ts', label:'Total supply'},
    {k:'dc', label: cotton?'Mill use':'Domestic use'},
    {k:'ex', label:'Exports'},
    {k:'es', label:'Ending stocks', cls:'row-ending'},
    {k:'stu', label:'Stocks / use', cls:'row-stu', dec:1},
  ];
}
function rowVal(row, rec, comm, world){
  if(row.k==='area') return areaAc(rec, comm);
  if(row.k==='yield') return yieldShown(rec, comm);
  if(row.k==='stu') return stuOf(rec, world);
  return vol(rec, row.k, comm);
}
function paint(v, dec){
  if(v==null || isNaN(v)) return na();
  if(dec) return Number(v).toFixed(dec) + (dec===1 && arguments[2] ? '%' : '');
  return Math.round(v).toLocaleString();
}
function balanceTable(comm, country, world){
  const years = showYears(comm);
  if(!years.length) return `<p class="legend-line">not available</p>`;
  const latest = years[years.length-1];
  const rows = balanceRows(comm);
  const colW = [2.4, ...years.map(()=>1), 1.15, 0.85];
  let html = `<table class="term-table bal-table">${fitColgroup(colW)}<thead><tr><th>Item</th>`;
  years.forEach(y=>{ html += `<th class="${y===latest?'latest':''}">${y}</th>`; });
  html += `<th>${priorHeader()}</th><th>MoM</th></tr></thead><tbody>`;
  rows.forEach(row=>{
    html += `<tr class="${row.cls||''}"><td>${row.label}</td>`;
    years.forEach(y=>{
      const recd = rec(comm, country, y);
      let v = rowVal(row, recd, comm, world);
      if(row.k==='stu') html += `<td class="${y===latest?'latest':''}">${v==null?na():v.toFixed(1)+'%'}</td>`;
      else html += `<td class="${y===latest?'latest':''}">${paint(v, row.dec||0)}</td>`;
    });
    const curRec = rec(comm, country, latest);
    const p = curRec && curRec._p;
    const cv = rowVal(row, curRec, comm, world);
    const pv = rowVal(row, p, comm, world);
    const ch = (cv!=null && pv!=null) ? cv-pv : null;
    const dec = row.k==='stu' || row.dec ? 1 : 0;
    const ptxt = row.k==='stu' ? (pv==null?na():pv.toFixed(1)+'%') : paint(pv, dec);
    const ctxt = ch==null ? na() : (signed(ch, dec) + (row.k==='stu' && Number(ch.toFixed(1))!==0 ? 'pp' : ''));
    html += `<td class="prior">${ptxt}</td><td class="${dir(ch)}">${ctxt}</td></tr>`;
  });
  html += `</tbody></table>`;
  return html;
}
function exporterTable(comm){
  const countries = DATA[comm] || {};
  const list = (EXPORTERS[comm]||[]).filter(c=>countries[c]);
  const ordered = [...list.filter(c=>c==='United States'), ...list.filter(c=>c!=='United States')];
  if(!ordered.length) return '';
  const years = showYears(comm);
  const latest = years[years.length-1];
  const metrics = [
    {k:'pr', label:'Production'},
    {k:'ex', label:'Exports'},
    {k:'es', label:'Ending stocks'},
    {k:'stu', label:'Stocks / use'},
  ];
  const colW = [2.2, ...years.map(()=>1), 1.1, 0.8];
  let html = `<table class="term-table bal-table">${fitColgroup(colW)}<thead><tr><th>Origin</th>`;
  years.forEach(y=>html += `<th class="${y===latest?'latest':''}">${y}</th>`);
  html += `<th>${priorHeader()}</th><th>MoM</th></tr></thead><tbody>`;
  metrics.forEach(metric=>{
    html += `<tr class="row-section"><td colspan="${years.length+3}">${metric.label}</td></tr>`;
    const names = ordered.concat(['__total']);
    names.forEach(name=>{
      const label = name==='__total' ? 'Listed origins' : name;
      html += `<tr class="${name==='__total'?'row-total':''}"><td>${label}</td>`;
      const vals = years.map(y=>{
        if(name!=='__total'){
          const r = rec(comm, name, y);
          return metric.k==='stu' ? stuOf(r, false) : vol(r, metric.k, comm);
        }
        if(metric.k==='stu') return null;
        let s=0, any=false, miss=false;
        ordered.forEach(c=>{
          const v = vol(rec(comm,c,y), metric.k, comm);
          if(v==null) miss=true; else { s+=v; any=true; }
        });
        return (any && !miss) ? s : null;
      });
      vals.forEach((v,i)=>{
        const txt = metric.k==='stu' ? (v==null?na():v.toFixed(1)+'%') : paint(v,0);
        html += `<td class="${years[i]===latest?'latest':''}">${txt}</td>`;
      });
      html += `<td class="prior">${na()}</td><td>${na()}</td></tr>`;
    });
  });
  html += `</tbody></table>`;
  return html;
}
function importRow(comm){
  const spec = {
    Wheat:['China','im','China imports'],
    Corn:['China','im','China imports'],
    Soybeans:['China','im','China imports'],
    'Rapeseed/Canola':['China','im','China imports'],
    Cotton:['China','im','China imports'],
    Coffee:['European Union','im','EU imports'],
    Sugar:['China','im','China imports'],
  }[comm];
  if(!spec) return '';
  const [country, key, label] = spec;
  const years = showYears(comm);
  if(!years.length || !(DATA[comm]||{})[country]) return '';
  const latest = years[years.length-1];
  let html = `<table class="term-table bal-table">${fitColgroup([2.2,...years.map(()=>1)])}<thead><tr><th>${label}</th>`;
  years.forEach(y=>html += `<th class="${y===latest?'latest':''}">${y}</th>`);
  html += `</tr></thead><tbody><tr><td>${country}</td>`;
  years.forEach(y=>{
    html += `<td class="${y===latest?'latest':''}">${paint(vol(rec(comm,country,y), key, comm),0)}</td>`;
  });
  html += `</tr></tbody></table>`;
  return html;
}
function sheet(title, sub, inner){
  return `<div class="panel"><div class="panel-hdr"><span class="panel-title">${title}</span>${sub?`<span class="panel-sub">${sub}</span>`:''}${usdaProv()}</div>${inner}</div>`;
}

function renderCgc(){
  const h = CGC && CGC.headline && CGC.headline.grains && CGC.headline.grains.canola;
  const g = CGC && CGC.grains && CGC.grains.canola;
  const cur = CGC && CGC.current;
  const ly = CGC && CGC.years && CGC.years[1];
  const lines = [
    'Canadian Grain Commission Grain Statistics Weekly, Summary tab, canola only.',
    'Week, crop-year and year-ago cells are the published Summary figures. Crush is the Process sheet.',
    h ? `Week ${CGC.latest_week} ending ${CGC.latest_date}.` : 'Release: not available',
    'Last fetch: '+fmtStamp(CGC && CGC.updated)
  ];
  let inner;
  if(!h){
    inner = `<p class="legend-line">not available</p>`;
  } else {
    const rows = [
      ['Producer deliveries', h.del_wk, h.del_cy, h.del_ya],
      ['Domestic disappearance', h.dom_wk, h.dom_cy, h.dom_ya],
      ['Exports', h.exp_wk, h.exp_cy, h.exp_ya],
      ['Commercial stocks', h.stk, null, null],
    ];
    inner = `<table class="term-table bal-table">${fitColgroup([2.2,1,1.2,1.2,1])}<thead><tr><th>Canola, kt</th><th>Week</th><th>Crop year</th><th>Year ago</th><th>vs yr ago</th></tr></thead><tbody>`;
    rows.forEach(r=>{
      const ch = (r[2]!=null && r[3]) ? (r[2]/r[3]-1)*100 : null;
      inner += `<tr><td>${r[0]}</td><td>${r[1]==null?na():r[1].toLocaleString()}</td><td>${r[2]==null?na():r[2].toLocaleString()}</td><td>${r[3]==null?na():r[3].toLocaleString()}</td><td class="${dir(ch)}">${ch==null?na():signed(ch,1)+'%'}</td></tr>`;
    });
    inner += `</tbody></table>`;
    const series = (g && g[cur]) || {};
    const lyS = g && ly && g[ly];
    const n = CGC.latest_week || 0;
    const start = Math.max(1, n-7);
    inner += `<table class="term-table bal-table" style="margin-top:8px">${fitColgroup([1.4,1,1,1,1,1])}<thead><tr><th>Week ending</th><th>Deliv wk</th><th>Deliv CY</th><th>Exp wk</th><th>Exp CY</th><th>Stocks</th></tr></thead><tbody>`;
    for(let w=n; w>=start; w--){
      const i=w-1;
      const dt = (CGC.dates[cur]||[])[i] || na();
      const at = (arr)=> (arr && arr[i]!=null) ? arr[i].toLocaleString() : na();
      inner += `<tr class="${w===n?'row-ending':''}"><td>${dt}</td><td>${at(series.del_wk)}</td><td>${at(series.del_cy)}</td><td>${at(series.exp_wk)}</td><td>${at(series.exp_cy)}</td><td>${at(series.stk)}</td></tr>`;
    }
    inner += `</tbody></table>`;
  }
  return `<div class="panel"><div class="panel-hdr"><span class="panel-title">CGC canola</span>${provMark(lines, null)}</div>${inner}</div>`;
}

function render(){
  const root = document.getElementById('root');
  if(!root) return;
  updateUsdaMeta();
  const comm = currentComm;
  const unitToggleEl = document.getElementById('unit-toggle');
  const convLabel = document.getElementById('conv-label');
  if(unitToggleEl) unitToggleEl.style.display = (usdaSource==='cgc' || NO_BUSHEL_COMMS.has(comm)) ? 'none' : '';
  if(convLabel){
    if(usdaSource==='cgc') convLabel.textContent = 'CGC Grain Statistics Weekly, thousand tonnes';
    else if(comm==='Cotton') convLabel.textContent = '1000 bales (480 lb)';
    else if(NO_BUSHEL_COMMS.has(comm)) convLabel.textContent = '1000 MT';
    else convLabel.textContent = currentUnit==='bu' ? 'Million bushels' : '1000 MT';
  }
  if(comm==='Rapeseed/Canola' && usdaSource==='cgc'){
    root.innerHTML = renderCgc();
    return;
  }
  const oils = comm==='Vegoils';
  const meals = comm==='Meal';
  const base = oils ? 'Soybean Oil' : meals ? 'Soybean Meal' : comm;
  if(!DATA || !DATA[base]){
    root.innerHTML = `<div id="err">not available</div>`;
    return;
  }
  let html = '';
  const places = oils || meals
    ? [['World', true], ['United States', false], ['Argentina', false], ['Brazil', false]]
    : [['United States', false], ['World', true]];
  places.forEach(([country, world])=>{
    html += sheet(country==='World'?'World':country, '', balanceTable(base, country, world));
  });
  if(!(oils||meals)){
    html += sheet('Exporters', 'Listed origins are a sum of these rows, not the World total', exporterTable(base));
    const imp = importRow(base);
    if(imp) html += sheet('Imports', '', imp);
  }
  root.innerHTML = html;
}

function ensureSourceToggle(){
  let el = document.getElementById('src-toggle');
  if(el) return;
  const bar = document.getElementById('topbar');
  if(!bar) return;
  el = document.createElement('div');
  el.className = 'toggle';
  el.id = 'src-toggle';
  el.innerHTML = `<button class="tbtn active" data-s="usda">USDA</button><button class="tbtn" data-s="cgc">CGC</button>`;
  const unit = document.getElementById('unit-toggle');
  bar.insertBefore(el, unit || bar.querySelector('#meta'));
  el.querySelectorAll('.tbtn').forEach(b=>b.addEventListener('click', ()=>{
    usdaSource = b.dataset.s;
    el.querySelectorAll('.tbtn').forEach(x=>x.classList.toggle('active', x===b));
    render();
  }));
}
const _initToggles = initToggles;
initToggles = function(){
  _initToggles();
  ensureSourceToggle();
  const src = document.getElementById('src-toggle');
  const show = ()=>{ if(src) src.style.display = currentComm==='Rapeseed/Canola' ? '' : 'none'; if(currentComm!=='Rapeseed/Canola') usdaSource='usda'; };
  document.getElementById('comm-toggle').addEventListener('click', ()=>setTimeout(show,0));
  show();
};
