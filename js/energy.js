function renderEnergy(){
  const root = document.getElementById('energy-root');
  if(!root) return;
  const st = energyStatus();
  if(!ENERGY || !ENERGY.series){
    root.innerHTML = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Stocks</span>${provMark(['Source: EIA','Release: —','Last fetch: —'], null)}</div><p class="legend-line">${na()}</p></div>`;
    return;
  }
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Weekly stocks</span>${provMark(['EIA Weekly Petroleum Status Report Tables 1 and 4, and the Weekly Natural Gas Storage Report.', ...st.parts, 'Natural gas 5-year average and percent are the numbers WNGSR prints. Petroleum 5-year averages are computed from EIA weekly levels.'], st.stale)}</div>`;
  html += `<table class="term-table bal-table">${fitColgroup([1.7,1,0.8,1,0.9,0.8,1])}<thead><tr><th>Item</th><th>Latest</th><th>w/w</th><th>Year ago</th><th title="computed from EIA weekly levels">5-yr avg</th><th>vs 5-yr</th><th>Week</th></tr></thead><tbody>`;
  ENERGY.series.forEach(s=>{
    if(!s || s.ok===false && s.value==null){
      html += `<tr><td>${s.label||s.key}</td><td colspan="6">${na()}</td></tr>`;
      return;
    }
    const d = s.decimals||0;
    const fmt = v => v==null ? na() : Number(v).toLocaleString(undefined,{minimumFractionDigits:d, maximumFractionDigits:d});
    html += `<tr class="jump" data-key="${s.key}"><td>${s.label}</td><td class="latest">${fmt(s.value)}</td><td class="${dir(s.change)}">${s.change==null?na():signed(s.change,d)}</td><td>${fmt(s.year_ago)}</td><td>${s.avg5==null?na():Number(s.avg5).toLocaleString()}</td><td class="${dir(s.vs_avg5_pct)}">${s.vs_avg5_pct==null?na():signed(s.vs_avg5_pct,1)+'%'}</td><td>${s.period||na()}</td></tr>`;
  });
  html += `</tbody></table></div>`;
  html += `<div class="panel"><div class="panel-hdr"><span class="panel-title" id="en-title">Level</span>${provMark(['5-yr range and avg from EIA weekly levels. Natural gas in the table is the WNGSR published average.'], st.stale)}</div><div id="en-chart"></div><p class="legend-line">Level / year ago / 5-yr avg / 5-yr range. 5-yr range and avg from EIA weekly levels.</p></div>`;
  root.innerHTML = html;
  if(!window._enKey){
    const asked = new URLSearchParams(location.search).get('en');
    if(asked) window._enKey = asked;
  }
  const first = (ENERGY.series.find(s=>s.key===window._enKey) || ENERGY.series[0]);
  drawEnergy(first);
  root.querySelectorAll('tr.jump').forEach(tr=>tr.addEventListener('click', ()=>{
    window._enKey = tr.dataset.key;
    drawEnergy(ENERGY.series.find(s=>s.key===tr.dataset.key));
  }));
}
function isoWeek(iso){
  const d = new Date(iso+'T00:00:00Z');
  const target = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((target - yearStart) / 86400000) + 1) / 7);
  return {year: target.getUTCFullYear(), week};
}
function seasonalBand(history){
  const by = {};
  history.forEach(([day, v])=>{
    const w = isoWeek(day);
    (by[w.year] = by[w.year] || {})[w.week] = v;
  });
  const years = Object.keys(by).map(Number).sort();
  if(years.length < 6) return [];
  const cur = years[years.length-1];
  const prior = [];
  for(let y=cur-5; y<cur; y++) if(by[y]) prior.push(y);
  if(prior.length < 5) return [];
  const rows = [];
  for(let w=1; w<=53; w++){
    const vals = prior.map(y=>by[y][w]).filter(v=>v!=null);
    if(vals.length < 5) continue;
    rows.push({
      w,
      min: Math.min(...vals),
      max: Math.max(...vals),
      avg: vals.reduce((a,b)=>a+b,0)/vals.length,
      cur: by[cur] ? by[cur][w] : null,
      ya: by[cur-1] ? by[cur-1][w] : null
    });
  }
  return rows;
}
function drawEnergy(s){
  const box = document.getElementById('en-chart');
  const title = document.getElementById('en-title');
  if(!box || !s) return;
  if(title) title.textContent = s.label + ' level';
  const rows = seasonalBand(s.history||[]);
  if(rows.length<8){ box.innerHTML = `<p class="legend-line">${na()}</p>`; return; }
  const vals = [];
  rows.forEach(r=>{ vals.push(r.min, r.max); if(r.cur!=null) vals.push(r.cur); if(r.ya!=null) vals.push(r.ya); });
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi-lo)*0.08 || 1; lo -= pad; hi += pad;
  const W=1000, H=280, M={l:58,r:16,t:16,b:28};
  const x = i => M.l + i/(rows.length-1)*(W-M.l-M.r);
  const y = v => M.t + (hi-v)/(hi-lo)*(H-M.t-M.b);
  const line = (pick, color, width, dash) => {
    const pts = [];
    rows.forEach((r,i)=>{ if(pick(r)!=null) pts.push(x(i).toFixed(1)+','+y(pick(r)).toFixed(1)); });
    return `<polyline fill="none" stroke="${color}" stroke-width="${width}" ${dash?`stroke-dasharray="${dash}"`:''} points="${pts.join(' ')}"/>`;
  };
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img">`;
  const band = rows.map((r,i)=>x(i).toFixed(1)+','+y(r.max).toFixed(1)).concat(rows.slice().reverse().map((r,i)=>x(rows.length-1-i).toFixed(1)+','+y(r.min).toFixed(1)));
  svg += `<polygon class="band" points="${band.join(' ')}" fill="var(--amber)" fill-opacity="0.16" stroke="none"/>`;
  svg += line(r=>r.avg, 'var(--text2)', 1.5, '5 4');
  svg += line(r=>r.ya, 'var(--text3)', 1.4, '');
  svg += line(r=>r.cur, 'var(--amber)', 2.2, '');
  svg += `<text x="${M.l}" y="${H-6}" style="fill:var(--text3);font-size:12px">week ${rows[0].w}</text>`;
  svg += `<text x="${W-M.r}" y="${H-6}" text-anchor="end" style="fill:var(--text3);font-size:12px">week ${rows[rows.length-1].w}</text>`;
  svg += `</svg>`;
  box.innerHTML = svg;
}
function ensureEnergy(){
  if(ENERGY){ renderEnergy(); return; }
  fetch('data/energy.json').then(r=>r.json()).then(d=>{ ENERGY=d; renderEnergy(); }).catch(()=>renderEnergy());
}
