const $=id=>document.getElementById(id);
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtWind=w=>w?`${w.direction}／${w.speed_kt} kt${w.gust_kt?'，陣風 '+w.gust_kt+' kt':''}`:'未提供';
const cloudNames={FEW:'少雲',SCT:'疏雲',BKN:'裂雲',OVC:'密雲',VV:'垂直能見度',SKC:'晴空',CLR:'無雲'};
const cloudTypes={CB:'積雨雲',TCU:'塔狀積雲'};
const fmtCloud=cs=>Array.isArray(cs)&&cs.length?cs.map(c=>{
 const cover=cloudNames[c.cover]||c.cover||'未知雲量';
 const height=Number.isFinite(Number(c.height_ft))?`${Number(c.height_ft).toLocaleString('zh-TW')} 英尺`:'高度未提供';
 const type=c.type?`（${cloudTypes[c.type]||c.type}）`:'';
 return `${cover} ${height}${type}`;
}).join('、'):'未提供';
const metric=(label,value)=>`<div class="metric"><small>${escapeHTML(label)}</small><strong>${escapeHTML(value)}</strong></div>`;
let airports=[],currentIcao='RCKH',loadId=0;
const aircraftTypes=[
 ['C-130 運輸機','大型運輸機','風況、能見度、雲底、雷暴及跑道相關氣象'],
 ['福克 50 行政機','雙發渦輪螺旋槳飛機','風況、能見度、雲底、降水與機場氣象變化'],
 ['幻象 2000 戰鬥機','噴射戰鬥機','風況、能見度、低雲、雷暴與顯著天氣'],
 ['20 公斤以下無人機','小型遙控無人機','陣風、降水、雷暴、能見度與現地風況；須查製造商限制']
];
function aircraftPanel(d){
 const m=d.metar,c=m?.conditions;
 const signals=[];
 if(!m){signals.push('METAR 缺漏');}
 else{
  if(c?.wind)signals.push('風 '+fmtWind(c.wind));else signals.push('風況未提供');
  if(c?.visibility_m!=null)signals.push('能見度 '+(c.visibility_m>=10000?'≥10 km':c.visibility_m+' m'));else signals.push('能見度未提供');
  if(m.hazards?.length)signals.push('已辨識：'+m.hazards.join('、'));else signals.push('未觸發本站通用警示規則（不等於安全）');
 }
 $('aircraft').innerHTML=aircraftTypes.map(([name,type,focus])=>`<article class="aircraft-card"><div class="aircraft-head"><h4>${escapeHTML(name)}</h4><span class="undetermined">起飛資格未判定</span></div><small>${escapeHTML(type)}</small><p><strong>氣象關注：</strong>${escapeHTML(focus)}</p><p><strong>觀測摘要：</strong>${escapeHTML(signals.join('；'))}</p><p class="note">尚需核准飛行手冊、操作規範、跑道／任務條件與即時現地資料。</p></article>`).join('');
}
function render(d){
 $('airport-title').textContent=`${d.name}（${d.icao}）`;
 const m=d.metar,c=m?.conditions;
 $('metrics').innerHTML=metric('飛行條件',m?.category||'未知')+metric('風向／風速',fmtWind(c?.wind))+metric('能見度',c?.visibility_m==null?'未知':c.visibility_m>=10000?'≥10 km':c.visibility_m+' m')+metric('雲層',c?fmtCloud(c.clouds):'未知');
 $('metar').innerHTML=m?`<p>警示：<span class="${m.hazards.length?'warn':'ok'}">${escapeHTML(m.hazards.join('、')||'未觸發設定門檻')}</span></p><p>天氣現象：${escapeHTML(c.weather.join('、')||'未明示')}</p><pre>${escapeHTML(m.raw)}</pre>`:'<p>目前沒有 METAR 資料。</p>';
 $('taf').innerHTML=d.taf?`<p><strong>有效期：</strong>${escapeHTML(d.taf.validity)}</p>${d.taf.groups.map(g=>`<div class="group"><strong>${escapeHTML(g.title)}</strong><p>風：${escapeHTML(fmtWind(g.conditions.wind))}</p><p>能見度：${escapeHTML(g.conditions.visibility_m==null?'未在本段明示':g.conditions.visibility_m>=10000?'≥10 km':g.conditions.visibility_m+' m')}</p><p>雲：${escapeHTML(fmtCloud(g.conditions.clouds))}</p><p>本段明示警示：${escapeHTML(g.hazards.join('、')||'無')}</p></div>`).join('')}<details><summary>TAF 原文</summary><pre>${escapeHTML(d.taf.raw)}</pre></details>`:'<p>目前沒有 TAF 資料。</p>';
 $('summary').textContent=d.summary;
 aircraftPanel(d);
 $('status').textContent=`資料更新：${new Date(d.fetched_at).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'})}`;
}
// Single raster image, not a tile layer. The map never repositions or resizes tiles.
// Geographic extent in WGS84 degrees; the ArcGIS export service renders the same bounding box.
const mapBounds={west:117.55,east:122.55,south:21.35,north:26.60};
const labelOffsets={
 RCTP:[-125,-34],RCSS:[15,-31],RCMQ:[-120,-31],RCKH:[-125,12],
 RCNN:[-126,-31],RCYU:[15,-30],RCFN:[15,12],RCQC:[-120,12],
 RCBS:[-115,12],RCFG:[-122,12],RCMT:[15,-31],RCLY:[-120,12],RCLM:[15,-31]
};
let airportMarkers={};
function highlight(){
 Object.entries(airportMarkers).forEach(([icao,el])=>el.classList.toggle('active-airport',icao===currentIcao));
}
function drawMap(){
 const mapEl=$('map');
 mapEl.replaceChildren();
 mapEl.classList.add('single-image-map');
 const image=document.createElement('img');
 image.className='taiwan-satellite-image';
 image.alt='台灣與離島衛星影像';
 image.draggable=false;
 // One server-rendered image, no 256px tile grid and no Leaflet dependency.
 const bbox=[mapBounds.west,mapBounds.south,mapBounds.east,mapBounds.north].join(',');
 image.src='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?'+
  new URLSearchParams({bbox,bboxSR:'4326',imageSR:'4326',size:'1200,1260',format:'jpg',transparent:'false',f:'image'}).toString();
 image.onerror=()=>{
  $('map-error').hidden=false;
  $('map-error').textContent='衛星影像服務暫時無法提供完整圖片。機場標記與天氣查詢仍可使用；請檢查網路或稍後重試。';
  mapEl.classList.add('satellite-unavailable');
 };
 image.onload=()=>{$('map-error').hidden=true;mapEl.classList.remove('satellite-unavailable');};
 mapEl.append(image);
 const layer=document.createElement('div');
 layer.className='airport-marker-layer';
 layer.setAttribute('aria-label','台灣13座機場互動標記');
 mapEl.append(layer);
 airports.forEach(a=>{
  const lon=Number(a.lon),lat=Number(a.lat);
  if(!Number.isFinite(lon)||!Number.isFinite(lat))return;
  const x=(lon-mapBounds.west)/(mapBounds.east-mapBounds.west)*100;
  const y=(mapBounds.north-lat)/(mapBounds.north-mapBounds.south)*100;
  const pin=document.createElement('button');
  pin.type='button';pin.className='sat-pin';pin.style.left=x+'%';pin.style.top=y+'%';
  pin.title=`${a.name} (${a.icao})`;pin.setAttribute('aria-label',pin.title);
  const dot=document.createElement('span');dot.className='sat-pin-dot';
  const label=document.createElement('span');label.className='sat-pin-label';
  label.append(document.createTextNode(a.name+' '));
  const small=document.createElement('small');small.textContent=a.icao;label.append(small);
  const [dx,dy]=labelOffsets[a.icao]||[15,-30];
  label.style.left=dx+'px';label.style.top=dy+'px';
  pin.append(dot,label);
  pin.addEventListener('click',()=>{
   $('airport').value=a.icao;load(a.icao);
   $('airport-title').scrollIntoView({behavior:'smooth',block:'start'});
  });
  layer.append(pin);airportMarkers[a.icao]=pin;
 });
 highlight();
}
async function load(icao){currentIcao=icao;highlight();const id=++loadId;$('status').textContent='正在取得氣象資料…';$('refresh').disabled=true;
 try{const r=await fetch(`/api/weather/${encodeURIComponent(icao)}`);const d=await r.json();if(!r.ok)throw Error(d.error||'查詢失敗');if(id===loadId)render(d);}catch(e){if(id===loadId)$('status').textContent='❌ '+e.message;}finally{if(id===loadId)$('refresh').disabled=false;}}
(async()=>{try{const r=await fetch('/api/airports');if(!r.ok)throw Error();airports=await r.json();airports.forEach(a=>{const o=document.createElement('option');o.value=a.icao;o.textContent=`${a.name} (${a.icao})`;$('airport').append(o)});drawMap();$('airport').value=currentIcao;load(currentIcao);}catch(e){$('status').textContent='機場清單載入失敗';}})();
$('airport').addEventListener('change',e=>load(e.target.value));$('refresh').addEventListener('click',()=>load($('airport').value));
