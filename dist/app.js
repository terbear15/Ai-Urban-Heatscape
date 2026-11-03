const cities=[{id:'nyc',name:'New York City',state:'New York',lat:40.73,lng:-73.97,base:34,canopy:22,impervious:67,icon:'▥'},{id:'philly',name:'Philadelphia',state:'Pennsylvania',lat:40,lng:-75.14,base:33,canopy:28,impervious:59,icon:'▤'},{id:'la',name:'Los Angeles region',state:'Southern California',lat:34.05,lng:-118.28,base:37,canopy:17,impervious:72,icon:'☀'}];
let current=cities[0],selected,map,overlay,labels,basemap,basemapLabels,layer='predicted';
const $=id=>document.getElementById(id),clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
function temp(c){return `${(c*9/5+32).toFixed(1)}°F / ${c.toFixed(1)}°C`;}
function delta(c){return `${(c*9/5).toFixed(1)}°F / ${c.toFixed(1)}°C`;}
function sample(c){return CITY_GRIDS[c.id].cells.map((cell,i)=>{
  // Spatially coherent synthetic examples, never measurements or model output.
  const wave=(Math.sin(cell.col*.15)+Math.cos(cell.row*.13)+Math.sin((cell.col+cell.row)*.06))/3;
  const green=clamp(c.canopy+wave*21,3,65),impervious=clamp(c.impervious-wave*18,12,91),predicted=clamp(c.base-wave*5,24,45),error=Math.sin(cell.row*.17-cell.col*.11)*1.5;
  return {...cell,id:`${c.id.toUpperCase()}-${i+1}`,green,impervious,predicted,observed:predicted-error,error};
});}
cities.forEach(c=>c.cells=sample(c));
function mean(c,key){return c.cells.reduce((s,d)=>s+d[key]*d.area_m2,0)/c.cells.reduce((s,d)=>s+d.area_m2,0);}
function color(d){
  const palette=layer==='green'?['#efefce','#c2d79c','#79a564','#2b6346']:layer==='error'?['#42799a','#bad8e3','#f0e6cf','#b8593e']:['#fff578','#ffb748','#ef703b','#bb2030'];
  const v=clamp(layer==='green'?d.green/65:layer==='error'?(d.error+2)/4:(d[layer]-24)/21,0,1)*3,index=Math.min(2,Math.floor(v)),ratio=v-index;
  const rgb=h=>h.match(/\w\w/g).map(x=>parseInt(x,16)),a=rgb(palette[index]),b=rgb(palette[index+1]);
  return `rgb(${a.map((n,i)=>Math.round(n+(b[i]-n)*ratio)).join(',')})`;
}
function tooltip(d){const title={predicted:'Predicted surface temperature',observed:'Observed surface temperature',error:'Prediction − observation',green:'Tree canopy coverage'}[layer];const value=layer==='green'?`${d.green.toFixed(0)}%`:layer==='error'?delta(d.error):temp(d[layer]);return `<div class="heat-tip-title">${title}</div><strong>${value}</strong><small>Synthetic demo · not live</small>`;}
function detail(d){selected=d;$('detail').innerHTML=`<h3>${d.id}</h3><p class="small">500 m grid · land only · synthetic values</p><div class="detail-values"><div><small>AI-predicted</small><b>${temp(d.predicted)}</b></div><div><small>Observed</small><b>${temp(d.observed)}</b></div><div><small>Tree canopy</small><b>${d.green.toFixed(0)}%</b></div><div><small>Impervious</small><b>${d.impervious.toFixed(0)}%</b></div></div><p class="small">Land area: ${(d.area_m2/1e6).toFixed(3)} km² · ${(d.area_m2/2589988.11).toFixed(3)} mi²</p><p class="small">Residual: ${delta(d.error)}</p>`;}
function draw(){if(!map)return;if(overlay){overlay.eachLayer(g=>{if(g.closeTooltip)g.closeTooltip();});overlay.remove();}overlay=L.layerGroup().addTo(map);current.cells.forEach(d=>{
  L.geoJSON({type:'Feature',geometry:d.geometry,properties:{}},{style:{color:'#fff5df',opacity:.3,weight:.25,fillColor:color(d),fillOpacity:+$('opacity').value/100}})
    .bindTooltip(tooltip(d),{sticky:true,direction:'top',offset:[0,-12],className:'heat-tooltip',opacity:1}).addTo(overlay).on('click',()=>detail(d));
});L.geoJSON(CITY_GRIDS[current.id].boundary,{style:{color:'#294c3b',weight:.8,opacity:.65,fill:false},interactive:false}).addTo(overlay);}
function setBasemap(style){if(!map)return;if(basemap)basemap.remove();if(basemapLabels)basemapLabels.remove();const sat=style==='satellite';let failures=0;$('mapStatus').hidden=true;
  basemap=L.tileLayer(sat?'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}':'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',{
    attribution:sat?'Imagery © Esri, Maxar, Earthstar Geographics, and GIS User Community':'Basemap © Esri, HERE, Garmin, OpenStreetMap contributors, and GIS User Community',maxZoom:19,referrerPolicy:'strict-origin-when-cross-origin',className:sat?'satellite-basemap':'clean-basemap'
  }).addTo(map);basemap.on('tileerror',()=>{if(++failures>=3)$('mapStatus').hidden=false;});basemap.on('tileload',()=>{$('mapStatus').hidden=true;});
  basemapLabels=L.tileLayer(sat?'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}':'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',{pane:'placeLabels',maxZoom:19,opacity:current.id==='la'?0:1,attribution:sat?'Reference labels © Esri':''}).addTo(map);
  $('map').classList.toggle('satellite-view',sat);document.querySelectorAll('[data-basemap]').forEach(b=>{b.classList.toggle('active',b.dataset.basemap===style);b.setAttribute('aria-pressed',b.dataset.basemap===style);});
}
function placeLabels(){if(!map)return;if(labels)labels.remove();labels=L.layerGroup().addTo(map);if(current.id!=='la')return;
  [['Los Angeles',34.0522,-118.2437],['Santa Monica',34.0195,-118.4912],['Pasadena',34.1478,-118.1445],['Inglewood',33.9617,-118.3531],['Compton',33.8958,-118.2201]].forEach(([name,lat,lng])=>L.marker([lat,lng],{pane:'placeLabels',interactive:false,icon:L.divIcon({className:'region-place-label',html:`<span>${name}</span>`,iconSize:[110,22],iconAnchor:[55,11]})}).addTo(labels));
}
function selectCity(id){current=cities.find(c=>c.id===id);document.querySelectorAll('.city').forEach(b=>{b.classList.toggle('active',b.dataset.city===id);b.setAttribute('aria-pressed',b.dataset.city===id);});$('mapTitle').textContent=current.name;if(basemapLabels)basemapLabels.setOpacity(id==='la'?0:1);
  $('studyAreaNote').textContent=id==='la'?'Custom LA region: Santa Monica, Pasadena, Inglewood, Compton, neighboring municipalities, and enclosed land gaps. Surface water excluded.':'City limits with mapped ocean, lakes, and rivers excluded from cells and summaries.';
  $('metrics').innerHTML=[['Mean predicted surface temperature',temp(mean(current,'predicted')),'Synthetic example · not live'],['Mean tree canopy',mean(current,'green').toFixed(0)+'%','Illustrative land cover · area-weighted'],['Mapped land area',(current.cells.reduce((s,d)=>s+d.area_m2,0)/1e6).toFixed(1)+' km²','Water excluded'],['Analysis cells',current.cells.length.toLocaleString(),'500 × 500 m · smaller at land edges']].map(d=>`<article class="metric"><span>${d[0]}</span><strong>${d[1]}</strong><small>${d[2]}</small></article>`).join('');
  if(map)map.fitBounds(L.geoJSON(CITY_GRIDS[id].boundary).getBounds(),{padding:[28,28]});draw();placeLabels();detail(current.cells[Math.floor(current.cells.length/2)]);
}
function legend(){const green=layer==='green',error=layer==='error';$('legendLabel').textContent=green?'Tree canopy · %':error?'Prediction − observation · °F / °C':'Surface temperature · °F / °C';$('legendLow').textContent=green?'0%':error?delta(-2):temp(24);$('legendMid').textContent=green?'33%':error?delta(0):temp(35);$('legendHigh').textContent=green?'65%':error?delta(2):temp(45);$('gradient').style.background=green?'linear-gradient(90deg,#efefce,#c2d79c,#79a564,#2b6346)':error?'linear-gradient(90deg,#42799a,#f0e6cf,#b8593e)':'linear-gradient(90deg,#fff578,#ffb748,#ef703b,#bb2030)';}
$('cities').innerHTML=cities.map(c=>`<button class="city" data-city="${c.id}"><span class="city-icon">${c.icon}</span><span><strong>${c.name}</strong><small>${c.state}</small></span><span class="arrow">↗</span></button>`).join('');document.querySelectorAll('.city').forEach(b=>b.onclick=()=>selectCity(b.dataset.city));
if(window.L){
  map=L.map('map',{scrollWheelZoom:true,preferCanvas:true,zoomSnap:.25,zoomDelta:.5}).setView([current.lat,current.lng],11);map.createPane('placeLabels');map.getPane('placeLabels').style.zIndex=450;map.getPane('placeLabels').style.pointerEvents='none';
  const legendControl=L.control({position:'bottomright'});legendControl.onAdd=()=>{const e=$('mapLegend');L.DomEvent.disableClickPropagation(e);L.DomEvent.disableScrollPropagation(e);return e;};legendControl.addTo(map);
  const toggleControl=L.control({position:'topright'});toggleControl.onAdd=()=>{const e=$('basemapToggle');L.DomEvent.disableClickPropagation(e);L.DomEvent.disableScrollPropagation(e);return e;};toggleControl.addTo(map);
  L.control.scale({position:'bottomleft',imperial:true,metric:true}).addTo(map);setBasemap('clean');new ResizeObserver(()=>map.invalidateSize()).observe($('map'));
}else $('mapFallback').hidden=false;
document.querySelectorAll('[data-basemap]').forEach(b=>b.onclick=()=>setBasemap(b.dataset.basemap));
$('layer').onchange=e=>{layer=e.target.value;legend();draw();};
$('opacity').oninput=()=>{$('opacityValue').textContent=$('opacity').value+'%';if(overlay)overlay.eachLayer(group=>{if(group.getLayers&&group.setStyle)group.setStyle({fillOpacity:+$('opacity').value/100});});};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(n=>n.classList.toggle('active',n===b));document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==b.dataset.view);if(b.dataset.view==='explore'&&map)requestAnimationFrame(()=>map.invalidateSize());});
$('comparison').innerHTML=cities.map(c=>`<article class="paper compare-card"><div class="eyebrow">${c.state.toUpperCase()} · DEMO</div><h2>${c.name}</h2><span class="big">${temp(mean(c,'predicted'))}</span><p>Area-weighted synthetic surface temperature · land only</p>${[['Tree canopy','green'],['Impervious cover','impervious']].map(([name,key])=>`<div class="bar-row"><div><span>${name}</span><b>${mean(c,key).toFixed(0)}%</b></div><div class="bar"><i style="width:${mean(c,key)}%"></i></div></div>`).join('')}<p class="small">${c.cells.length.toLocaleString()} land-clipped cells · ${c.id==='la'?'custom study region':'city limits'}</p></article>`).join('');
$('download').onclick=()=>{const rows=['data_status,observation_period,study_area,cell_id,latitude,longitude,land_area_m2,predicted_surface_f,predicted_surface_c,observed_surface_f,observed_surface_c,residual_f,residual_c,tree_canopy_pct,impervious_pct',...current.cells.map(d=>['SYNTHETIC_DEMO','NOT_APPLICABLE_NO_OBSERVATIONS',current.name,d.id,d.lat,d.lng,d.area_m2,(d.predicted*9/5+32).toFixed(2),d.predicted.toFixed(2),(d.observed*9/5+32).toFixed(2),d.observed.toFixed(2),(d.error*9/5).toFixed(2),d.error.toFixed(2),d.green.toFixed(2),d.impervious.toFixed(2)].join(','))];const u=URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'})),a=document.createElement('a');a.href=u;a.download=`heatscape-${current.id}-SYNTHETIC-DEMO.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
legend();selectCity('nyc');




