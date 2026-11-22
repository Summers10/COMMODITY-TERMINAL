function renderCattle(box){
  const root = box || document.getElementById('cattle-root');
  if(!root) return;
  const C = CATTLE || {};
  const lines = [
    'On feed and inventory: USDA NASS. Percents are the ones printed in the report.',
    'The federal slaughter weights table is not shown. The AMS report does not print a year-ago head count.',
    '5-area steer: USDA AMS LM_CT150, live FOB steer weighted average. Boxed beef: USDA AMS LM_XB403.',
    'Beef supply: USDA WASDE. The CME Feeder Cattle Index is not on a keyless feed, so it is not shown.',
    'Live and feeder cattle positioning is on the CFTC page.'
  ];
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Cattle on feed</span>${provMark(lines, cattleStale())}</div>`;
  const hist = C.on_feed || [];
  const latest = hist[hist.length-1];
  if(!latest){
    html += `<p class="legend-line">${na()}</p></div>`;
  } else {
    const items = [
      ['On feed', latest.on_feed],
      ['Placements', latest.placements],
      ['Marketings', latest.marketings],
      ['Other disappearance', latest.other_disappearance],
    ];
    html += `<table class="term-table bal-table">${fitColgroup([2,1,1,0.8])}<thead><tr><th>${latest.as_of}</th><th>000 head</th><th>Year ago</th><th>% of yr ago</th></tr></thead><tbody>`;
    items.forEach(([name, r])=>{
      const d = r ? r.pct_of_year_ago-100 : null;
      html += `<tr><td>${name}</td><td class="latest">${r?r.current.toLocaleString():na()}</td><td>${r?r.year_ago.toLocaleString():na()}</td><td class="${dir(d)}">${r?r.pct_of_year_ago:na()}</td></tr>`;
    });
    html += `</tbody></table><div id="cof-chart"></div></div>`;
  }
  html += inventoryBlock(C.inventory);
  html += priceBlock(C);
  html += wasdeBeefBlock(C.wasde);
  root.innerHTML = html;
  if(latest) drawCof(hist);
}
function inventoryBlock(rows){
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Cattle inventory</span><span class="panel-sub">January and July</span></div>`;
  if(!rows || !rows.length){ return html+`<p class="legend-line">${na()}</p></div>`; }
  rows.slice().reverse().forEach(rep=>{
    html += `<table class="term-table bal-table">${fitColgroup([2,1.2,1,0.8])}<thead><tr><th>${rep.as_of}</th><th>000 head</th><th>Year ago</th><th>%</th></tr></thead><tbody>`;
    [['All cattle','all_cattle'],['Beef cows','beef_cows'],['Heifers retained','heifers_retained'],['Calf crop','calf_crop']].forEach(([label,k])=>{
      const r = rep.rows[k] || {};
      const d = r.pct_of_year_ago!=null ? r.pct_of_year_ago-100 : null;
      html += `<tr><td>${label}</td><td>${r.current==null?na():Number(r.current).toLocaleString()}</td><td>${r.year_ago==null?na():Number(r.year_ago).toLocaleString()}</td><td class="${dir(d)}">${r.pct_of_year_ago==null?na():r.pct_of_year_ago}</td></tr>`;
    });
    html += `</tbody></table>`;
  });
  return html+`</div>`;
}
function slaughterBlock(s){
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Federally inspected slaughter</span></div>`;
  if(!s) return html+`<p class="legend-line">${na()}</p></div>`;
  html += `<table class="term-table bal-table">${fitColgroup([2,1,1,1])}<thead><tr><th>${s.week_end||''}</th><th>Head</th><th>Year ago</th><th>5-yr avg</th></tr></thead><tbody>`;
  html += `<tr><td>Cattle</td><td class="latest">${s.cattle_head.toLocaleString()}</td><td>${s.year_ago_head==null?na():s.year_ago_head}</td><td>${s.avg5_head==null?na():s.avg5_head}</td></tr>`;
  const d = s.dressed_lbs||{};
  html += `<tr><td>Dressed wt, cattle</td><td>${d.cattle==null?na():d.cattle+' lb'}</td><td>${na()}</td><td>${na()}</td></tr>`;
  html += `<tr><td>Dressed wt, steers</td><td>${d.steers==null?na():d.steers+' lb'}</td><td>${na()}</td><td>${na()}</td></tr>`;
  html += `<tr><td>Dressed wt, heifers</td><td>${d.heifers==null?na():d.heifers+' lb'}</td><td>${na()}</td><td>${na()}</td></tr>`;
  html += `</tbody></table></div>`;
  return html;
}
function priceBlock(C){
  const s = C.steer, c = C.cutout;
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Cash and wholesale</span></div>`;
  html += `<table class="term-table bal-table">${fitColgroup([2,1,1,1])}<thead><tr><th>Item</th><th>Latest</th><th>Week ago</th><th>Year ago</th></tr></thead><tbody>`;
  if(s && s.live_fob_steer){
    const a=s.live_fob_steer, b=s.live_fob_steer_week_ago, y=s.live_fob_steer_year_ago;
    html += `<tr><td>5-area live FOB steer</td><td class="latest">${a.price.toFixed(2)}</td><td class="${dir(a.price-(b&&b.price))}">${b?b.price.toFixed(2):na()}</td><td class="${dir(a.price-(y&&y.price))}">${y?y.price.toFixed(2):na()}</td></tr>`;
  } else html += `<tr><td>5-area live FOB steer</td><td colspan="3">${na()}</td></tr>`;
  html += `<tr><td>Feeder cattle index</td><td colspan="3">${na()}</td></tr>`;
  if(c){
    html += `<tr><td>Choice cutout</td><td class="latest">${c.choice.toFixed(2)}</td><td class="${dir(c.choice_change)}">${signed(c.choice_change,2)} d/d</td><td>${na()}</td></tr>`;
    html += `<tr><td>Select cutout</td><td class="latest">${c.select.toFixed(2)}</td><td class="${dir(c.select_change)}">${signed(c.select_change,2)} d/d</td><td>${na()}</td></tr>`;
  } else html += `<tr><td>Boxed beef</td><td colspan="3">${na()}</td></tr>`;
  html += `</tbody></table></div>`;
  return html;
}
function wasdeBeefBlock(w){
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">WASDE beef</span><span class="panel-sub">million pounds</span></div>`;
  if(!w || !w.beef_current) return html+`<p class="legend-line">${na()}</p></div>`;
  const cur = w.beef_current, pri = w.beef_prior || {};
  html += `<table class="term-table bal-table">${fitColgroup([1.6,1,1,1])}<thead><tr><th>2026</th><th>Current</th><th>Prior month</th><th>MoM</th></tr></thead><tbody>`;
  [['Production','pr'],['Imports','im'],['Exports','ex'],['Total supply','ts'],['Ending stocks','es'],['Total use','dc']].forEach(([label,k])=>{
    const a=cur[k], b=pri[k];
    const ch=(a!=null&&b!=null)?a-b:null;
    html += `<tr><td>${label}</td><td class="latest">${a==null?na():a.toLocaleString()}</td><td>${b==null?na():b.toLocaleString()}</td><td class="${dir(ch)}">${ch==null?na():signed(ch,0)}</td></tr>`;
  });
  const sp = w.steer_price;
  if(sp){
    const curP = sp.current!=null ? sp.current : sp.oct;
    const priP = sp.prior!=null ? sp.prior : sp.sep;
    const ch = curP-priP;
    html += `<tr><td>Steer price, $/cwt</td><td class="latest">${curP.toFixed(2)}</td><td>${priP.toFixed(2)}</td><td class="${dir(ch)}">${signed(ch,2)}</td></tr>`;
  }
  html += `</tbody></table></div>`;
  return html;
}
function cofTicks(lo, hi, n){
  const span = (hi - lo) || 1, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const ticks = [];
  for(let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) ticks.push(v);
  return ticks;
}
function drawCof(hist){
  const box = document.getElementById('cof-chart');
  if(!box) return;
  const byYear = {};
  (hist || []).forEach(r=>{
    if(!r || !r.as_of || !r.on_feed || r.on_feed.current==null) return;
    const [y, m] = r.as_of.split('-').map(Number);
    (byYear[y] = byYear[y] || {})[m] = r.on_feed.current;
  });
  const years = Object.keys(byYear).map(Number).sort((a, b)=>a - b);
  if(!years.length){ box.innerHTML = ''; return; }
  const current = years[years.length - 1];
  const last = current - 1;
  const bandYears = [];
  for(let y = current - 5; y < current; y++) if(byYear[y]) bandYears.push(y);
  const months = [];
  for(let m = 1; m <= 12; m++){
    const vals = bandYears.map(y=>byYear[y][m]).filter(v=>v!=null);
    months.push(vals.length ? {m, lo:Math.min(...vals), hi:Math.max(...vals)} : {m});
  }
  const seriesVals = [];
  months.forEach(p=>{ if(p.lo!=null) seriesVals.push(p.lo, p.hi); });
  [last, current].forEach(y=>{
    const row = byYear[y] || {};
    for(let m = 1; m <= 12; m++) if(row[m]!=null) seriesVals.push(row[m]);
  });
  if(!seriesVals.length){ box.innerHTML = ''; return; }
  let lo = Math.min(...seriesVals), hi = Math.max(...seriesVals);
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad; hi += pad;
  const W = 1000, H = 340, M = {l:86, r:14, t:10, b:32};
  const plotW = W - M.l - M.r, plotH = H - M.t - M.b;
  const x = m => M.l + (m - 1) / 11 * plotW;
  const yOf = v => M.t + (hi - v) / (hi - lo) * plotH;
  const bandLabel = bandYears.length ? `${bandYears[0]}–${bandYears[bandYears.length - 1]} min–max` : 'No prior years';
  let html = `<div class="cof-chart"><div class="cof-hd">Cattle on feed, first of the month</div><div class="cof-src">USDA NASS Cattle on Feed · on-feed headcount · 000 head · a month with no report is left blank</div><div class="cof-legend"><span><i class="cof-sw-band"></i>${bandLabel}</span>${byYear[last] ? `<span><i class="cof-sw-ly"></i>${last}</span>` : ''}<span><i class="cof-sw-cy"></i>${current}</span></div>`;
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="USDA NASS Cattle on Feed, cattle on feed, 000 head">`;
  cofTicks(lo, hi, 5).forEach(t=>{
    svg += `<line x1="${M.l}" x2="${M.l + plotW}" y1="${yOf(t)}" y2="${yOf(t)}" style="stroke:var(--border);stroke-width:1"/>`;
    svg += `<text x="${M.l - 8}" y="${yOf(t) + 4}" text-anchor="end" style="fill:var(--text3);font-size:13px">${Math.round(t).toLocaleString()}</text>`;
  });
  svg += `<text transform="rotate(-90)" x="${-(M.t + plotH / 2)}" y="16" text-anchor="middle" style="fill:var(--text3);font-size:13px">000 head</text>`;
  let run = [];
  const flush = ()=>{
    if(!run.length) return;
    if(run.length === 1){
      const p = run[0], w = 16, top = yOf(p.hi), bot = yOf(p.lo);
      svg += `<rect x="${(x(p.m) - w / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${w}" height="${Math.max(2, bot - top).toFixed(1)}" fill="rgba(91,111,148,.35)" stroke="#5b6f94" stroke-width="1"/>`;
    } else {
      const upper = run.map(p=>`${x(p.m).toFixed(1)},${yOf(p.hi).toFixed(1)}`);
      const lower = run.slice().reverse().map(p=>`${x(p.m).toFixed(1)},${yOf(p.lo).toFixed(1)}`);
      svg += `<polygon points="${upper.concat(lower).join(' ')}" fill="rgba(91,111,148,.35)" stroke="#5b6f94" stroke-width="1"/>`;
    }
    run = [];
  };
  months.forEach(p=>{ if(p.lo==null) flush(); else run.push(p); });
  flush();
  const stroke = (year, color, width)=>{
    const row = byYear[year];
    if(!row) return;
    let seg = [];
    const draw = ()=>{
      if(seg.length >= 2) svg += `<polyline fill="none" stroke="${color}" stroke-width="${width}" points="${seg.join(' ')}"/>`;
      else if(seg.length === 1){
        const [px, py] = seg[0].split(',');
        svg += `<circle cx="${px}" cy="${py}" r="3.5" fill="${color}"/>`;
      }
      seg = [];
    };
    for(let m = 1; m <= 12; m++){
      if(row[m]==null) draw();
      else seg.push(`${x(m).toFixed(1)},${yOf(row[m]).toFixed(1)}`);
    }
    draw();
  };
  stroke(last, 'var(--text2)', 1.8);
  stroke(current, 'var(--amber)', 2.6);
  ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].forEach((name, i)=>{
    svg += `<text x="${x(i + 1)}" y="${H - 10}" text-anchor="middle" style="fill:var(--text3);font-size:13px">${name}</text>`;
  });
  svg += `</svg></div>`;
  box.innerHTML = html + svg;
}
function ensureCattle(box){
  const go = ()=>renderCattle(box);
  if(CATTLE){ go(); return; }
  fetch('data/cattle.json').then(r=>r.ok?r.json():null).then(d=>{ CATTLE=d; go(); }).catch(go);
}
