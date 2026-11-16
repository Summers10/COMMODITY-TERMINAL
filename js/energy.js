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
  html += `<div class="panel"><div class="panel-hdr"><span class="panel-title" id="en-title">Level</span>${provMark(['Petroleum 5-yr range and avg are computed from EIA weekly levels. The natural gas band is the WNGSR published average and range when ngsstats.xls matches the table.'], st.stale)}</div><div id="en-chart"></div><p class="legend-line" id="en-note">Level / year ago / 5-yr avg / 5-yr range.</p></div>`;
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
function isoWeekFriday(year, week){
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const day = jan4.getUTCDay() || 7;
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - day + 1 + (week - 1) * 7);
  const fri = new Date(monday);
  fri.setUTCDate(monday.getUTCDate() + 4);
  return fri.toISOString().slice(0, 10);
}
function seasonalBand(history){
  const by = {};
  history.forEach(([day, v])=>{
    const w = isoWeek(day);
    (by[w.year] = by[w.year] || {})[w.week] = {v, date: day};
  });
  const years = Object.keys(by).map(Number).sort();
  if(years.length < 6) return [];
  const cur = years[years.length-1];
  const prior = [];
  for(let y=cur-5; y<cur; y++) if(by[y]) prior.push(y);
  if(prior.length < 5) return [];
  const rows = [];
  for(let w=1; w<=53; w++){
    const vals = prior.map(y=>by[y][w] && by[y][w].v).filter(v=>v!=null);
    if(vals.length < 5) continue;
    const curObs = by[cur] && by[cur][w];
    const yaObs = by[cur-1] && by[cur-1][w];
    rows.push({
      date: curObs ? curObs.date : isoWeekFriday(cur, w),
      min: Math.min(...vals),
      max: Math.max(...vals),
      avg: vals.reduce((a,b)=>a+b,0)/vals.length,
      cur: curObs ? curObs.v : null,
      ya: yaObs ? yaObs.v : null
    });
  }
  return rows;
}
function publishedRows(s){
  const hist = {};
  (s.history||[]).forEach(([day, v])=>{ hist[day] = v; });
  return (s.published_band||[]).map(p=>({
    date: p[0], avg: p[1], min: p[2], max: p[3], ya: p[4],
    cur: Object.prototype.hasOwnProperty.call(hist, p[0]) ? hist[p[0]] : null
  })).filter(r=>r.avg!=null && r.min!=null && r.max!=null);
}
function axisTicks(lo, hi){
  const span = hi - lo || 1;
  const rough = span / 4;
  const pow = Math.pow(10, Math.floor(Math.log10(rough)));
  const steps = [1, 2, 2.5, 5, 10].map(m => m * pow);
  const step = steps.reduce((best, s)=> Math.abs(s - rough) < Math.abs(best - rough) ? s : best);
  const out = [];
  for(let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step){
    if(v >= lo && v <= hi) out.push(Math.round(v * 1000) / 1000);
  }
  return out;
}
function drawEnergy(s){
  const box = document.getElementById('en-chart');
  const title = document.getElementById('en-title');
  const note = document.getElementById('en-note');
  if(!box || !s) return;
  if(title) title.textContent = s.label + ' level';
  const published = Array.isArray(s.published_band) && s.published_band.length >= 40;
  const rows = published ? publishedRows(s) : seasonalBand(s.history||[]);
  if(note){
    note.textContent = published
      ? 'Level / year ago / 5-yr avg / 5-yr range. 5-yr range and avg are the figures WNGSR publishes for each week.'
      : 'Level / year ago / 5-yr avg / 5-yr range. 5-yr range and avg from EIA weekly levels.';
  }
  if(rows.length<8){ box.innerHTML = `<p class="legend-line">${na()}</p>`; return; }
  const vals = [];
  rows.forEach(r=>{ vals.push(r.min, r.max); if(r.cur!=null) vals.push(r.cur); if(r.ya!=null) vals.push(r.ya); });
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi-lo)*0.06 || 1; lo -= pad; hi += pad;
  const W=1000, H=460, M={l:72,r:18,t:28,b:36};
  const x = i => M.l + (rows.length<2 ? 0 : i/(rows.length-1))*(W-M.l-M.r);
  const y = v => M.t + (hi-v)/(hi-lo)*(H-M.t-M.b);
  const unit = (s.unit||'').toLowerCase().indexOf('bcf')>=0 ? 'Bcf' : 'million bbl';
  const dec = s.decimals||0;
  const fmt = v => v==null ? '—' : Number(v).toLocaleString(undefined,{minimumFractionDigits:dec, maximumFractionDigits:dec});
  const fmtTick = v => Number(v).toLocaleString(undefined,{maximumFractionDigits: Math.abs(v)>=100?0:1});
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const line = (pick, color, width, dash) => {
    const pts = [];
    rows.forEach((r,i)=>{ if(pick(r)!=null) pts.push(x(i).toFixed(1)+','+y(pick(r)).toFixed(1)); });
    return `<polyline fill="none" stroke="${color}" stroke-width="${width}" ${dash?`stroke-dasharray="${dash}"`:''} points="${pts.join(' ')}"/>`;
  };
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${s.label} level">`;
  svg += `<text x="${M.l}" y="16" style="fill:var(--text3);font-size:12px;font-family:Courier New,Courier,monospace">${unit}</text>`;
  axisTicks(lo, hi).forEach(v=>{
    const yy = y(v);
    svg += `<line x1="${M.l}" x2="${W-M.r}" y1="${yy.toFixed(1)}" y2="${yy.toFixed(1)}" stroke="var(--border2)" stroke-width="1"/>`;
    svg += `<text x="${M.l-8}" y="${(yy+4).toFixed(1)}" text-anchor="end" style="fill:var(--text3);font-size:12px;font-family:Courier New,Courier,monospace">${fmtTick(v)}</text>`;
  });
  const band = rows.map((r,i)=>x(i).toFixed(1)+','+y(r.max).toFixed(1)).concat(rows.slice().reverse().map((r,i)=>x(rows.length-1-i).toFixed(1)+','+y(r.min).toFixed(1)));
  svg += `<polygon class="band" points="${band.join(' ')}" fill="var(--amber)" fill-opacity="0.16" stroke="none"/>`;
  svg += line(r=>r.avg, 'var(--text2)', 1.5, '5 4');
  svg += line(r=>r.ya, 'var(--text3)', 1.4, '');
  svg += line(r=>r.cur, 'var(--amber)', 2.2, '');
  let prevMonth = -1;
  rows.forEach((r,i)=>{
    const month = Number(String(r.date).slice(5,7)) - 1;
    if(month!==prevMonth && month>=0){
      prevMonth = month;
      svg += `<text x="${x(i).toFixed(1)}" y="${H-10}" text-anchor="middle" style="fill:var(--text3);font-size:12px;font-family:Courier New,Courier,monospace">${months[month]}</text>`;
    }
  });
  svg += `<line id="en-guide" y1="${M.t}" y2="${H-M.b}" stroke="var(--amber)" stroke-width="1" visibility="hidden"/>`;
  svg += `</svg><div id="en-tip" hidden></div>`;
  box.innerHTML = svg;
  const svgEl = box.querySelector('svg');
  const guide = box.querySelector('#en-guide');
  const tip = box.querySelector('#en-tip');
  const hide = ()=>{ guide.setAttribute('visibility','hidden'); tip.hidden = true; };
  function showAt(i){
    const gx = x(i);
    const rect = svgEl.getBoundingClientRect();
    guide.setAttribute('x1', gx.toFixed(1));
    guide.setAttribute('x2', gx.toFixed(1));
    guide.setAttribute('visibility', 'visible');
    const r = rows[i];
    tip.innerHTML = `<b>${r.date}</b><br>Level ${fmt(r.cur)}<br>Year ago ${fmt(r.ya)}<br>5-yr avg ${fmt(r.avg)}<br>Range ${fmt(r.min)} – ${fmt(r.max)}`;
    tip.hidden = false;
    const tipW = tip.offsetWidth;
    let left = (gx / W) * rect.width + 12;
    if(left + tipW > rect.width - 4) left = (gx / W) * rect.width - tipW - 12;
    tip.style.left = Math.max(4, left) + 'px';
    tip.style.top = '28px';
  }
  svgEl.addEventListener('mousemove', ev=>{
    const rect = svgEl.getBoundingClientRect();
    const px = ((ev.clientX - rect.left) / rect.width) * W;
    if(px < M.l || px > W - M.r){ hide(); return; }
    let best = 0, bestD = 1e9;
    rows.forEach((_, i)=>{ const d = Math.abs(x(i) - px); if(d < bestD){ bestD = d; best = i; } });
    showAt(best);
  });
  svgEl.addEventListener('mouseleave', hide);
  const probe = new URLSearchParams(location.search).get('probe');
  if(probe){
    const i = probe === '1' ? rows.reduce((a, r, idx)=> r.cur!=null ? idx : a, 0) : Math.max(0, rows.findIndex(r=>r.date===probe));
    requestAnimationFrame(()=>showAt(i));
  }
}
function ensureEnergy(){
  if(ENERGY){ renderEnergy(); return; }
  fetch('data/energy.json').then(r=>r.json()).then(d=>{ ENERGY=d; renderEnergy(); }).catch(()=>renderEnergy());
}
