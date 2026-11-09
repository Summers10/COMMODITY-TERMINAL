const CP_COUNTRIES = [
  {code:'us', name:'United States'},
  {code:'br', name:'Brazil'},
  {code:'ar', name:'Argentina'},
  {code:'fr', name:'France'},
];
let CP = {}, CP_STATUS = {}, cpHide = false;
function cpGroup(name){
  const c = String(name||'').toLowerCase();
  if(/silage|sweet/.test(c)) return null;
  if(/wheat|blé|trigo/.test(c)) return 'Wheat';
  if(/corn|maize|maïs|maiz|milho/.test(c)) return 'Corn';
  if(/canola|rapeseed|colza/.test(c)) return 'Canola';
  if(/soybean|soja/.test(c)) return 'Soybeans';
  if(/cotton|algod/.test(c)) return 'Cotton';
  if(/rice|arroz/.test(c)) return 'Rice';
  if(/sunflower|girasol/.test(c)) return 'Sunflower';
  if(/peanut|mani/.test(c)) return 'Peanuts';
  return null;
}
function cpLabel(name){
  const n = String(name).replace(/,\s*(Grain|Upland)$/i,'');
  const m = n.match(/^Wheat,\s*(\w+)$/i);
  return m ? m[1][0].toUpperCase()+m[1].slice(1).toLowerCase()+' wheat' : n;
}
function cpShown(r, field){
  const q = r.quality && r.quality[field];
  const mark = q==='interpolated' || q==='estimated' ? q : null;
  if(cpHide && mark){
    if(field==='avg5' && r.avg5_observed!=null) return {v:r.avg5_observed, mark:null, n:r.avg5_observed_n};
    return {v:null, mark:null, n:null};
  }
  return {v:r[field]==null?null:r[field], mark, n:null};
}
function cpNum(v){
  if(v==null) return na();
  const n = Math.round(v*10)/10;
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
function renderProgress(){
  const root = document.getElementById('progress-root');
  if(!root) return;
  let html = `<p class="legend-line"><button type="button" class="tbtn" id="cp-hide">${cpHide?'Show †‡':'Hide †‡'}</button> † interpolated week. ‡ estimated (carried or not yet started).  The count after an average is observed years only.</p>`;
  CP_COUNTRIES.forEach(c=>{
    const d = CP[c.code];
    const age = d && d.report_date ? (Date.now()-new Date(d.report_date+'T12:00:00Z'))/86400000 : null;
    const stale = age!=null && age>10;
    const lines = [
      (d&&d.source)||'Source: not available',
      'Week ending: '+(d&&d.report_date||'not available'),
      'Last fetch: '+fmtStamp(d&&d.fetched_at),
      'Last year and the 5-year average are the ones carried in the file for that week.'
    ];
    html += `<div class="panel"><div class="panel-hdr"><span class="panel-title">${c.name}</span>${provMark(lines, d?stale:null)}</div>`;
    if(!d || !d.rows){ html += `<p class="legend-line">not available</p></div>`; return; }
    const rows = d.rows.map(r=>({...r, g:cpGroup(r.crop), label:cpLabel(r.crop)})).filter(r=>r.g);
    html += `<table class="term-table bal-table">${fitColgroup([2.2,1,1,1,1])}<thead><tr><th>Stage</th><th>This week</th><th>Prior week</th><th>Last year</th><th>5-yr avg</th></tr></thead><tbody>`;
    let last = '';
    rows.forEach(r=>{
      if(r.label!==last){
        html += `<tr class="row-section"><td colspan="5">${r.label}</td></tr>`;
        last = r.label;
      }
      const cols = ['current','prev_week','last_year','avg5'].map(f=>cpShown(r,f));
      html += `<tr><td>${r.metric.replace('_',' ')}</td>`;
      cols.forEach(s=>{
        const mark = s.mark==='estimated'?'‡':(s.mark==='interpolated'?'†':'');
        const yrs = s.n?`<span class="cftc-ref-sub">${s.n}y</span>`:'';
        html += `<td>${cpNum(s.v)}${mark}${yrs}</td>`;
      });
      html += `</tr>`;
    });
    html += `</tbody></table></div>`;
  });
  root.innerHTML = html;
  const btn = document.getElementById('cp-hide');
  if(btn) btn.addEventListener('click', ()=>{ cpHide=!cpHide; renderProgress(); });
}
function ensureProgress(){
  if(CP.us || CP.br){ renderProgress(); return; }
  const grab = p => fetch(p).then(r=>r.ok?r.json():null).catch(()=>null);
  Promise.all([
    grab('data/status.json'),
    ...CP_COUNTRIES.map(c=>grab('data/'+c.code+'.json')),
  ]).then(([st, ...rows])=>{
    CP_STATUS = st || {};
    CP_COUNTRIES.forEach((c,i)=>{ if(rows[i]) CP[c.code]=rows[i]; });
    renderProgress();
  });
}
