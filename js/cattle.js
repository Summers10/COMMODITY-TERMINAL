function renderCattle(){
  const root = document.getElementById('cattle-root');
  if(!root) return;
  const C = CATTLE || {};
  const lines = [
    'On feed and inventory: USDA NASS. Percents are the ones printed in the report.',
    'Slaughter and dressed weights: USDA AMS Actual Slaughter Under Federal Inspection. Year-ago and the 5-year average are not printed in that report.',
    '5-area steer: USDA AMS LM_CT150, live FOB steer weighted average. Boxed beef: USDA AMS LM_XB403.',
    'Beef supply: USDA WASDE. The CME Feeder Cattle Index is not on a keyless feed, so it is not shown.',
    'Live and feeder cattle positioning is on the CFTC page.'
  ];
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Cattle on feed</span>${provMark(lines, cattleStale())}</div>`;
  const hist = C.on_feed || [];
  const latest = hist[hist.length-1];
  if(!latest){
    html += `<p class="legend-line">not available</p></div>`;
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
  html += slaughterBlock(C.slaughter);
  html += priceBlock(C);
  html += wasdeBeefBlock(C.wasde);
  root.innerHTML = html;
  if(latest) drawCof(hist);
}
function inventoryBlock(rows){
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">Cattle inventory</span><span class="panel-sub">January and July</span></div>`;
  if(!rows || !rows.length){ return html+`<p class="legend-line">not available</p></div>`; }
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
  if(!s) return html+`<p class="legend-line">not available</p></div>`;
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
  } else html += `<tr><td>5-area live FOB steer</td><td colspan="3">not available</td></tr>`;
  html += `<tr><td>Feeder cattle index</td><td colspan="3">not available</td></tr>`;
  if(c){
    html += `<tr><td>Choice cutout</td><td class="latest">${c.choice.toFixed(2)}</td><td class="${dir(c.choice_change)}">${signed(c.choice_change,2)} d/d</td><td>${na()}</td></tr>`;
    html += `<tr><td>Select cutout</td><td class="latest">${c.select.toFixed(2)}</td><td class="${dir(c.select_change)}">${signed(c.select_change,2)} d/d</td><td>${na()}</td></tr>`;
  } else html += `<tr><td>Boxed beef</td><td colspan="3">not available</td></tr>`;
  html += `</tbody></table></div>`;
  return html;
}
function wasdeBeefBlock(w){
  let html = `<div class="panel"><div class="panel-hdr"><span class="panel-title">WASDE beef</span><span class="panel-sub">million pounds</span></div>`;
  if(!w || !w.beef_current) return html+`<p class="legend-line">not available</p></div>`;
  const cur = w.beef_current, pri = w.beef_prior || {};
  html += `<table class="term-table bal-table">${fitColgroup([1.6,1,1,1])}<thead><tr><th>2026</th><th>Oct</th><th>Sep</th><th>MoM</th></tr></thead><tbody>`;
  [['Production','pr'],['Imports','im'],['Exports','ex'],['Total supply','ts'],['Ending stocks','es'],['Total use','dc']].forEach(([label,k])=>{
    const a=cur[k], b=pri[k];
    const ch=(a!=null&&b!=null)?a-b:null;
    html += `<tr><td>${label}</td><td class="latest">${a==null?na():a.toLocaleString()}</td><td>${b==null?na():b.toLocaleString()}</td><td class="${dir(ch)}">${ch==null?na():signed(ch,0)}</td></tr>`;
  });
  const sp = w.steer_price;
  if(sp){
    const ch = sp.oct-sp.sep;
    html += `<tr><td>Steer price, $/cwt</td><td class="latest">${sp.oct.toFixed(2)}</td><td>${sp.sep.toFixed(2)}</td><td class="${dir(ch)}">${signed(ch,2)}</td></tr>`;
  }
  html += `</tbody></table></div>`;
  return html;
}
function drawCof(hist){
  const box = document.getElementById('cof-chart');
  if(!box) return;
  const byYear = {};
  hist.forEach(r=>{
    const [y,m] = r.as_of.split('-').map(Number);
    (byYear[y] = byYear[y] || {})[m] = r.on_feed.current;
  });
  const years = Object.keys(byYear).map(Number).sort().slice(-6);
  const vals = [];
  years.forEach(y=>Object.values(byYear[y]).forEach(v=>vals.push(v)));
  if(vals.length<2){ box.innerHTML=''; return; }
  let lo=Math.min(...vals), hi=Math.max(...vals);
  const pad=(hi-lo)*0.08||1; lo-=pad; hi+=pad;
  const W=1000,H=260,M={l:54,r:10,t:16,b:26};
  const x=m=>M.l+(m-1)/11*(W-M.l-M.r);
  const y=v=>M.t+(hi-v)/(hi-lo)*(H-M.t-M.b);
  const colors=['#8a7a68','#5b6f94','#6B7280','#0E7A3A','#C4302B','#B8720A'];
  let svg=`<svg viewBox="0 0 ${W} ${H}" width="100%" role="img">`;
  years.forEach((yr,idx)=>{
    const pts=[];
    for(let m=1;m<=12;m++) if(byYear[yr][m]!=null) pts.push(x(m).toFixed(1)+','+y(byYear[yr][m]).toFixed(1));
    svg += `<polyline fill="none" stroke="${colors[idx%colors.length]}" stroke-width="${idx===years.length-1?2.4:1.2}" points="${pts.join(' ')}"/>`;
  });
  years.forEach((yr,idx)=>{
    const x0 = M.l + idx*70;
    svg += `<text x="${x0}" y="12" style="fill:${colors[idx%colors.length]};font-size:12px;font-weight:700">${yr}</text>`;
  });
  svg += `<text x="${M.l}" y="${H-6}" style="fill:var(--text3);font-size:12px">Jan</text><text x="${W-M.r}" y="${H-6}" text-anchor="end" style="fill:var(--text3);font-size:12px">Dec</text>`;
  svg += `</svg>`;
  box.innerHTML = svg;
}
function ensureCattle(){
  const go = ()=>renderCattle();
  if(CATTLE){ go(); return; }
  fetch('data/cattle.json').then(r=>r.ok?r.json():null).then(d=>{ CATTLE=d; go(); }).catch(go);
}
