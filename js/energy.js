function renderEnergy(){
  const root = document.getElementById('energy-root');
  if(!root) return;
  const st = energyStatus();
  if(!ENERGY || !ENERGY.series){
    root.innerHTML = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Stocks</span>${provMark(['Source: EIA','Release: not available','Last fetch: not available'], null)}</div><p class="legend-line">not available</p></div>`;
    return;
  }
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Weekly stocks</span>${provMark(['EIA Weekly Petroleum Status Report Tables 1 and 4, and the Weekly Natural Gas Storage Report.', ...st.parts, 'Natural gas 5-year average and percent are the numbers WNGSR prints. These petroleum tables do not print a 5-year average.'], st.stale)}</div>`;
  html += `<table class="term-table bal-table">${fitColgroup([1.7,1,0.8,1,0.9,0.8,1])}<thead><tr><th>Item</th><th>Latest</th><th>w/w</th><th>Year ago</th><th>5-yr avg</th><th>vs 5-yr</th><th>Week</th></tr></thead><tbody>`;
  ENERGY.series.forEach(s=>{
    if(!s || s.ok===false && s.value==null){
      html += `<tr><td>${s.label||s.key}</td><td colspan="6">not available</td></tr>`;
      return;
    }
    const d = s.decimals||0;
    const fmt = v => v==null ? na() : Number(v).toLocaleString(undefined,{minimumFractionDigits:d, maximumFractionDigits:d});
    html += `<tr class="jump" data-key="${s.key}"><td>${s.label}</td><td class="latest">${fmt(s.value)}</td><td class="${dir(s.change)}">${s.change==null?na():signed(s.change,d)}</td><td>${fmt(s.year_ago)}</td><td>${s.avg5==null?na():Number(s.avg5).toLocaleString()}</td><td class="${dir(s.vs_avg5_pct)}">${s.vs_avg5_pct==null?na():signed(s.vs_avg5_pct,1)+'%'}</td><td>${s.period||na()}</td></tr>`;
  });
  html += `</tbody></table></div>`;
  html += `<div class="panel"><div class="panel-hdr"><span class="panel-title" id="en-title">Level</span>${provMark(['History is the published weekly stock level. No 5-year average is drawn, because EIA does not publish that history in these files.'], st.stale)}</div><div id="en-chart"></div></div>`;
  root.innerHTML = html;
  const first = (ENERGY.series.find(s=>s.key===window._enKey) || ENERGY.series[0]);
  drawEnergy(first);
  root.querySelectorAll('tr.jump').forEach(tr=>tr.addEventListener('click', ()=>{
    window._enKey = tr.dataset.key;
    drawEnergy(ENERGY.series.find(s=>s.key===tr.dataset.key));
  }));
}
function drawEnergy(s){
  const box = document.getElementById('en-chart');
  const title = document.getElementById('en-title');
  if(!box || !s) return;
  if(title) title.textContent = s.label + ' level';
  const h = (s.history||[]).slice(-260);
  if(h.length<2){ box.innerHTML = `<p class="legend-line">not available</p>`; return; }
  const vals = h.map(p=>p[1]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi-lo)*0.08 || 1; lo -= pad; hi += pad;
  const W=1000, H=280, M={l:58,r:12,t:12,b:28};
  const x = i => M.l + i/(h.length-1)*(W-M.l-M.r);
  const y = v => M.t + (hi-v)/(hi-lo)*(H-M.t-M.b);
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img">`;
  svg += `<polyline fill="none" stroke="var(--amber)" stroke-width="2" points="${h.map((p,i)=>x(i).toFixed(1)+','+y(p[1]).toFixed(1)).join(' ')}"/>`;
  svg += `<text x="${M.l}" y="${H-6}" style="fill:var(--text3);font-size:12px">${h[0][0]}</text>`;
  svg += `<text x="${W-M.r}" y="${H-6}" text-anchor="end" style="fill:var(--text3);font-size:12px">${h[h.length-1][0]}</text>`;
  svg += `</svg>`;
  box.innerHTML = svg;
}
function ensureEnergy(){
  if(ENERGY){ renderEnergy(); return; }
  fetch('data/energy.json').then(r=>r.json()).then(d=>{ ENERGY=d; renderEnergy(); }).catch(()=>renderEnergy());
}
