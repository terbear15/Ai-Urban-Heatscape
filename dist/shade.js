/* HeatScape city shade map. CITY (from cities/views.json) and CITYDATA (dist/data/<slug>.js) are set by shade.html. */
const $=id=>document.getElementById(id),fc=features=>({type:'FeatureCollection',features});
const engine=HeatEngine.create(CITYDATA);let ready=false,picking=null,result=null,selected='shade',timer;
const empty=fc([]),bounds=[[CITYDATA.meta.bounds[0],CITYDATA.meta.bounds[1]],[CITYDATA.meta.bounds[2],CITYDATA.meta.bounds[3]]];
const methods=$('methods');for(const id of ['about','limits'])$(id).onclick=()=>methods.showModal();methods.querySelector('.close').onclick=()=>methods.close();$('exploreTab').onclick=()=>document.querySelector('.workspace').scrollIntoView({behavior:'smooth'});
function err(text){$('mapError').hidden=false;$('mapError').textContent=text;}
let map;
try{map=new maplibregl.Map({container:'map',center:[(CITYDATA.meta.bounds[0]+CITYDATA.meta.bounds[2])/2,(CITYDATA.meta.bounds[1]+CITYDATA.meta.bounds[3])/2],zoom:14,maxPitch:0,dragRotate:false,pitchWithRotate:false,minZoom:9,maxZoom:19,style:{version:8,sources:{base:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'],tileSize:256,maxzoom:16,attribution:'Basemap © Esri · © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · Trees: NOAA LiDAR, PPR canopy'},labels:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}'],tileSize:256,maxzoom:16}},layers:[{id:'background',type:'background',paint:{'background-color':'#eeeee9'}},{id:'basemap',type:'raster',source:'base',paint:{'raster-fade-duration':0}}]},attributionControl:true});}catch(e){err('This browser could not start the map. Please open this prototype in a WebGL-enabled browser.');$('calculate').disabled=true;}
const markers={};
let season='summer';
const endpoints={start:null,end:null};
const hasLocation=key=>Boolean(endpoints[key] && endpoints[key].label===$(key).value.trim());
const hasTrip=()=>hasLocation('start')&&hasLocation('end');
function coord(key){
  if(!hasLocation(key)) throw new Error('Search for the edited location, then choose a result.');
  return endpoints[key].point;
}
let locationWorker, searchId=0;
const searches=new Map();
// Search: named places in the study area (instant, local), then street addresses via Photon inside it.
const normalizeText=text=>text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[’'`.]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const placeIndex=(window.PLACES||[]).map(([name,kind,lon,lat])=>({name,kind,point:[lon,lat],key:normalizeText(name),words:normalizeText(name).split(' ')}));
function findPlaces(query){
  const q=normalizeText(query);
  if(!q)return [];
  const tokens=q.split(' ');
  const scored=[];
  for(const place of placeIndex){
    if(!inShadeArea(place.point))continue;
    let score;
    if(place.key===q)score=0;
    else if(place.key.startsWith(q))score=1;
    else if(tokens.every(t=>place.words.some(w=>w.startsWith(t))))score=2;
    else if(place.key.includes(q))score=3;
    else continue;
    scored.push([score,place.key.length,place]);
  }
  scored.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const seen=new Set(),out=[];
  for(const [,,place] of scored){
    if(seen.has(place.key))continue;
    seen.add(place.key);
    out.push({label:`${place.name} · ${place.kind}`,point:place.point});
    if(out.length===8)break;
  }
  return out;
}
async function findAddresses(query){
  const [w,s,e,n]=CITYDATA.meta.bounds;
  const url=`https://photon.komoot.io/api/?q=${encodeURIComponent(query+' '+CITY.name)}&bbox=${w},${s},${e},${n}&limit=8&lang=en`;
  const response=await fetch(url);
  if(!response.ok)throw new Error('Address search is unavailable right now. Pick the point on the map instead.');
  const data=await response.json();
  const out=[],seen=new Set();
  for(const f of data.features||[]){
    const point=f.geometry.coordinates;
    if(!inShadeArea(point))continue;
    const p=f.properties;
    const street=[p.housenumber,p.street].filter(Boolean).join(' ');
    const label=[p.name,street].filter(Boolean).join(', ')||p.city||'Location';
    if(seen.has(label))continue;
    seen.add(label);
    out.push({label,point});
  }
  return out;
}
async function lookup(query,address=false,suggest=false){
  const local=/^\d/.test(query.trim())?[]:findPlaces(query);
  if(local.length)return local;
  if(suggest&&query.trim().length<4)return [];
  const found=await findAddresses(query);
  if(!found.length&&!suggest)throw new Error(`No match inside ${CITY.areaName}. Try a landmark name or a street address.`);
  return found;
}
function requestLocation(payload){
  if(!locationWorker){
    locationWorker=new Worker('location/worker.js?v=lidar');
    locationWorker.onmessage=({data})=>{
      const pending=searches.get(data.id);
      if(!pending)return;
      searches.delete(data.id);
      data.error?pending.reject(new Error(data.error)):pending.resolve(data.matches);
    };
    locationWorker.onerror=()=>{
      for(const pending of searches.values())pending.reject(new Error('Location search could not load. Try again.'));
      searches.clear();locationWorker.terminate();locationWorker=null;
    };
  }
  return new Promise((resolve,reject)=>{
    const id=++searchId;
    searches.set(id,{resolve,reject});
    locationWorker.postMessage({id,...payload});
  });
}
function useLocation(key,label,point){
  endpoints[key]={label,point};
  $(key).value=label;
  $(key+'Matches').hidden=true;
  const version=++routeVersion;
  if(map)marker(key,point);
  const message=hasTrip()?'Calculating walking routes…':
    key==='start'?'Choose a destination to compare routes.':'Choose a starting point to compare routes.';
  if(ready)clearRoute(message);
  else $('routeStatus').textContent=message;
  if(hasTrip()){
    // Let the new pin and status paint before starting route calculation.
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      if(version===routeVersion&&hasTrip())calculate(true);
    }));
  }
}
const suggestionTimers={};
const searchVersions={start:0,end:0};
async function searchLocation(key,suggest=false){
  clearTimeout(suggestionTimers[key]);
  const version=++searchVersions[key];
  const query=$(key).value.trim(), button=$(key+'Search'), list=$(key+'Matches');
  if(!query){$('routeStatus').textContent=`Enter a place or address in ${CITY.areaName}.`;return;}
  list.hidden=true;
  if(!suggest){
    button.disabled=true;
    $('routeStatus').textContent=`Searching ${CITY.areaName}…`;
  }
  try{
    const matches=await lookup(query,false,suggest);
    if($(key).value.trim()!==query||searchVersions[key]!==version)return;
    if(!suggest&&matches.length===1&&matches[0].point){
      useLocation(key,matches[0].label,matches[0].point);return;
    }
    list.replaceChildren();
    for(const match of matches){
      const option=document.createElement('button');
      option.type='button';option.textContent=match.label;
      option.onclick=async()=>{
        option.disabled=true;
        try{
          const point=match.point||(await lookup(match.address,true))[0].point;
          if($(key).value.trim()===query)useLocation(key,match.label,point);
        }catch(error){$('routeStatus').textContent=error.message;}
        finally{option.disabled=false;}
      };
      list.append(option);
    }
    list.hidden=matches.length===0;
    if(!suggest)$('routeStatus').textContent='Choose the matching location.';
  }catch(error){if(!suggest&&$(key).value.trim()===query)$('routeStatus').textContent=error.message;}
  finally{if(!suggest)button.disabled=false;}
}
function marker(key,p){if(!markers[key]){const el=document.createElement('div');el.className='marker '+(key==='end'?'end':'');el.textContent=key==='start'?'A':'B';el.setAttribute('aria-label',key==='start'?'Route start':'Route destination');markers[key]=new maplibregl.Marker({element:el}).setLngLat(p).addTo(map);}else markers[key].setLngLat(p);}
function feature(route){return fc([{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:route.coords}}]);}
function fit(){if(result){const b=new maplibregl.LngLatBounds();[...result.fast.coords,...result.shade.coords].forEach(p=>b.extend(p));map.fitBounds(b,{padding:{top:90,bottom:110,left:80,right:60},maxZoom:16,duration:700});}else map.fitBounds(cityBounds,{padding:42});}
function selectRoute(which){selected=which;document.querySelectorAll('.route-card').forEach(b=>{const active=b.dataset.route===which;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});map.setPaintProperty('fast','line-opacity',which==='fast'?1:.65);map.setPaintProperty('shade-route','line-opacity',which==='shade'?1:.6);const layer=which==='shade'?'shade-route':'fast';map.moveLayer(layer+'-halo');map.moveLayer(layer);}
function showRoute(route, zoom){
  const winter=season==='winter';
  const hasShadeDetour=Boolean(route.shade && route.shade!==route.fast);
  if(winter){
    const seconds=Math.floor(route.winterBudget*60+1e-8);
    const minutes=Math.floor(seconds/60);
    const remaining=seconds%60;
    const duration=[minutes?`${minutes} min`:'',remaining||!minutes?`${remaining} sec`:''].filter(Boolean).join(' ');
    $('winterBudget').textContent=Number.isFinite(seconds)?`Up to ${duration}`:'Auto';
  }
  const hasExposure=Number.isFinite(route.fast.exposure);
  const treePilot=season==='summer'&&$('treeShade').checked;
  result={...route,shade:route.shade||route.fast};
  map.getSource('fast').setData(feature(route.fast));
  map.getSource('shade-route').setData(hasShadeDetour?feature(route.shade):empty);

  function card(key,title,tag){
    const r=result[key];
    const minutes=r.length/80.4672;
    const shadeDetails=hasExposure?`<div class="sun-bar"><i style="width:${r.exposure/r.length*100}%"></i></div>
      <div class="card-foot"><span>~${(r.exposure/80.4672).toFixed(1)} min modeled sun</span>
      <span>${Math.round((winter?r.exposure/r.length:1-r.exposure/r.length)*100)}% ${winter?'sun':'shade'}</span></div>`:'';
    return `<button class="route-card ${key==='fast'?'direct':''}" data-route="${key}" aria-pressed="false">
      <div class="card-title">${title}<small>${tag}</small></div>
      <div class="route-stats"><strong>${Math.round(minutes)} <span>min</span></strong>
      <span>· ${(r.length/1609.344).toFixed(2)} mi</span></div>${shadeDetails}</button>`;
  }

  let note=winter?'The search found no sunnier route within the extra time allowed.':
    'The search found no lower-sun route within your per-detour time limit.';
  if(!hasExposure)note='Building shade could not be loaded for this trip. Try again to compare routes.';
  if(route.afterSunset)note='The sun is below the horizon at this time.';
  if(hasShadeDetour){
    const difference=Math.abs(route.fast.exposure-route.shade.exposure)/80.4672;
    const added=(route.shade.length-route.fast.length)/80.4672;
    note=`About ${difference.toFixed(1)} ${winter?'more':'fewer'} minutes in modeled direct sun for ${added.toFixed(1)} extra walking minutes total.`;
  }
  $('results').innerHTML=(hasShadeDetour?card('shade',winter?'Sunnier walk':'Lower-sun candidate','MODELED'):'')+
    card('fast','Shortest walk',hasShadeDetour?'BASELINE':'RECOMMENDED')+
    `<p class="result-note">${note}${hasExposure?(treePilot?' Building and LiDAR tree shade; street-centerline estimates.':' Building shade only; street-centerline estimates.'):''}</p>`;
  document.querySelectorAll('.route-card').forEach(button=>button.onclick=()=>selectRoute(button.dataset.route));
  selectRoute(hasShadeDetour?selected:'fast');
  if(!hasShadeDetour)selected='shade';
  $('routeStatus').textContent=`3 mph estimate · Points snapped ${Math.round(route.start.meters*3.28084)} ft / ${Math.round(route.end.meters*3.28084)} ft to the network; those gaps excluded.`;
  if(zoom)fit();
}
const cityBounds=CITY.bounds;
let areaRings=null;
fetch('cities/'+CITY.slug+'.geojson').then(r=>r.json()).then(fc=>{
  const g=fc.features.find(f=>f.properties.layer==='land').geometry;
  areaRings=(g.type==='Polygon'?[g.coordinates]:g.coordinates).map(poly=>poly[0]);
}).catch(()=>{});
const inShadeArea=p=>{
  const [x,y]=p;
  if(!(x>=bounds[0][0]&&x<=bounds[1][0]&&y>=bounds[0][1]&&y<=bounds[1][1]))return false;
  // A small tolerance: points within the data margin just outside the line are allowed.
  return !areaRings||areaRings.some(r=>HeatEngine.contains(p,r))||areaRings.some(r=>r.some(q=>Math.hypot((q[0]-x)*85000,(q[1]-y)*111000)<120));
};
let routeVersion=0, pendingCityTrip;
async function calculate(zoom=false){
  if(!ready||!hasTrip())return;
  const trip=[coord('start'),coord('end')];
  ++routeVersion;
  if(!trip.every(inShadeArea)){clearRoute('Choose both points inside the dashed boundary.');return;}
  if(!citySun)return;
  try{
    refreshShade();
    const route=engine.routes(...trip,+$('detour').value,season==='winter');
    route.afterSunset=citySun.altitude<=0;
    showRoute(route,zoom);
  }catch(error){clearRoute(error.message);}
}
function clearRoute(message){
  result=null;
  $('winterBudget').textContent='Auto';
  map.getSource('fast').setData(empty);
  map.getSource('shade-route').setData(empty);
  for(const key of Object.keys(markers)){
    if(hasLocation(key))continue;
    markers[key].remove();
    delete markers[key];
  }
  $('results').replaceChildren();
  $('routeStatus').textContent=message;
}
$('cityOverview').onclick=()=>{
  if(ready)map.fitBounds(cityBounds,{padding:45,duration:650});
};
let citySun, localSun;
function timeText(){const t=+$('time').value,h=Math.floor(t),m=Math.round((t-h)*60);$('timeLabel').textContent=`${h%12||12}:${String(m).padStart(2,'0')} ${h>=12?'PM':'AM'}`;return {h,m};}
const seasons={
  summer:{min:'2026-06-01',max:'2026-08-31',date:'2026-07-15',hour:'15',last:'19',offset:CITY.tz.summer,zone:CITY.tz.summerName},
  winter:{min:'2026-12-01',max:'2027-02-28',date:'2027-01-15',hour:'12',last:'17',offset:CITY.tz.winter,zone:CITY.tz.winterName},
};
const routeColors={
  summer:{fast:'#f4a96e',candidate:'#8bd5a6'},
  winter:{fast:'#b6d0ec',candidate:'#ffd078'},
};
function setSeason(next){
  clearTimeout(timer);
  ++routeVersion;
  season=next;
  const winter=next==='winter';
  const setting=seasons[next];
  document.body.dataset.season=next;
  try{localStorage.setItem('heatscape-season',next);}catch(e){}
  $('summerMode').setAttribute('aria-pressed',String(!winter));
  $('winterMode').setAttribute('aria-pressed',String(winter));
  $('seasonTitle').textContent=winter?'A little more sun.':'A little more shade.';
  $('walkMode').textContent=winter?'WINTER · SEEK SUN':'SUMMER · SEEK SHADE';
  $('candidateLegend').textContent=winter?'Sunnier route':'Lower-sun route';
  $('summerDetour').hidden=false;
  $('winterDetour').hidden=true;
  $('treeShade').disabled=winter;
  $('treeStatus').textContent=winter?'Leaf-off: trees not counted in winter':'LiDAR tree crowns';
  $('dateLabel').textContent=winter?'WINTER SCENARIO':'SUMMER SCENARIO';
  $('timezone').textContent=setting.zone;
  $('lastHour').textContent=winter?'5 PM':'7 PM';
  Object.assign($('date'),{min:setting.min,max:setting.max,value:setting.date});
  Object.assign($('time'),{max:setting.last,value:setting.hour});
  timeText();
  if(!ready)return;
  applyRouteColors();
  shadeKey='';
  clearRoute(hasTrip()?'Recalculating your walk…':'Choose a starting point and destination to compare routes.');
  updateSun();
}
function applyRouteColors(){
  const colors=routeColors[season];
  map.setPaintProperty('fast','line-color',colors.fast);
  map.setPaintProperty('shade-route','line-color',colors.candidate);
}
let shadeKey='';
// Recompute building (and, in summer, tree) shadows for the current sun, and draw them.
function refreshShade(){
  if(!ready||!citySun)return;
  const withTrees=season==='summer'&&$('treeShade').checked;
  const key=[citySun.azimuth.toFixed(4),citySun.altitude.toFixed(4),withTrees].join();
  if(key===shadeKey)return;
  shadeKey=key;
  const shade=engine.updateShade(citySun.azimuth,citySun.altitude,{geometry:true,withTrees});
  map.getSource('building-shadows').setData(shade.buildings);
  map.getSource('tree-shadows').setData(shade.trees);
  $('treeStatus').textContent=season==='winter'?'Leaf-off: trees not counted in winter':
    shade.night?'Sun below the horizon':
    withTrees?`${engine.treeCount.toLocaleString()} LiDAR-measured tree crowns`:'Tree shade off · buildings only';
}
const refreshTreeShade=refreshShade;
$('treeShade').onchange=()=>{
  refreshShade();
  calculate();
};
$('treePilot').onclick=()=>{
  if(!ready)return;
  if(season!=='summer')setSeason('summer');
  $('treeShade').checked=true;
  $('treeShade').onchange();
  map.fitBounds(cityBounds,{padding:45,duration:550});
};
function updateSun(){
  if(!ready)return;
  const {h,m}=timeText();
  const date=$('date').value;
  const setting=seasons[season];
  if(!date||!$('date').checkValidity()){
    $('routeStatus').textContent=`Choose a date between ${setting.min} and ${setting.max}.`;
    return;
  }
  const clock=`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:00`;
  citySun=SunCalc.getPosition(new Date(`${date}T${clock}${setting.offset}`),(cityBounds[0][1]+cityBounds[1][1])/2,(cityBounds[0][0]+cityBounds[1][0])/2);
  $('solarLabel').textContent=citySun.altitude<=0?'Sun below the horizon':
    `Sun elevation ${Math.round(citySun.altitude*180/Math.PI)}° · ${season==='winter'?'Winter':'Summer'} scenario`;
  refreshTreeShade();
  calculate();
}
$('summerMode').onclick=()=>{if(season!=='summer')setSeason('summer');};
$('winterMode').onclick=()=>{if(season!=='winter')setSeason('winter');};
{let saved=null;try{saved=localStorage.getItem('heatscape-season');}catch(e){}if((new URLSearchParams(location.search).get('season')||saved)==='winter')setSeason('winter');}
if(map){map.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');map.addControl(new maplibregl.ScaleControl({unit:'imperial'}),'bottom-right');map.on('error',e=>{if(e.sourceId==='base')err('Background tiles unavailable. Route lines are still available.');});map.on('load',()=>{
map.addSource('area',{type:'geojson',data:'cities/'+CITY.slug+'.geojson',tolerance:0});
map.addLayer({id:'city-mask',type:'fill',source:'area',filter:['==',['get','layer'],'mask'],paint:{
  'fill-color':'#f5f4ed','fill-opacity':.6,'fill-antialias':false,
}});
map.addLayer({id:'city-limits',type:'line',source:'area',filter:['==',['get','layer'],'land'],paint:{
  'line-color':'#4a4f4c','line-width':1.6,'line-opacity':.95,'line-dasharray':[3,2],
}});
map.addLayer({id:'labels',type:'raster',source:'labels',paint:{'raster-fade-duration':0,'raster-opacity':.8}});
// Shadows are drawn opaque in a light tint so overlapping shadow pieces do not stack darker.
map.addSource('building-shadows',{type:'geojson',data:empty,tolerance:.3});
map.addLayer({id:'building-shadows',type:'fill',source:'building-shadows',paint:{'fill-color':'#b4bac6','fill-opacity':1,'fill-antialias':false}});
map.addSource('tree-shadows',{type:'geojson',data:empty,tolerance:.3});
map.addLayer({id:'tree-shadows',type:'fill',source:'tree-shadows',paint:{'fill-color':'#9cc4a3','fill-opacity':1,'fill-antialias':false}});
map.addSource('trees',{type:'geojson',data:CITYDATA.trees||empty});
map.addLayer({id:'trees',type:'fill',source:'trees',paint:{'fill-color':'#4f8f5c','fill-opacity':.85}});
map.addSource('buildings',{type:'geojson',data:CITYDATA.buildings});
map.addLayer({id:'buildings',type:'fill',source:'buildings',paint:{'fill-color':'#7d848e','fill-opacity':1,'fill-outline-color':'#666c75'}});
map.moveLayer('city-mask');map.moveLayer('city-limits');
for(const [id,color,width] of [['fast','#f4a96e',4],['shade-route','#8bd5a6',5]]){
  map.addSource(id,{type:'geojson',data:empty});
  const layout={'line-join':'round','line-cap':'round'};
  map.addLayer({id:id+'-halo',type:'line',source:id,layout,paint:{'line-color':'#172c23','line-width':width+3}});
  map.addLayer({id,type:'line',source:id,layout,paint:{'line-color':color,'line-width':width}});
}
ready=true;applyRouteColors();updateSun();map.fitBounds(cityBounds,{padding:42,duration:0});
map.on('click',event=>{
  if(!picking)return;
  const point=[event.lngLat.lng,event.lngLat.lat];
  useLocation(picking,'Map pin · '+point[1].toFixed(5)+', '+point[0].toFixed(5),point);
  picking=null;
  map.getCanvas().style.cursor='';
  document.querySelectorAll('.pick-row button').forEach(button=>button.classList.remove('active'));
});
});}
for(const [id,key] of [['pickStart','start'],['pickEnd','end']])$(id).onclick=()=>{if(!ready)return;picking=picking===key?null:key;document.querySelectorAll('.pick-row button').forEach(b=>b.classList.toggle('active',b.id===id&&!!picking));map.getCanvas().style.cursor=picking?'crosshair':'';$('routeStatus').textContent=picking?`Click on the ${CITY.name} map to choose your ${key}.`:'Map selection canceled.';};
for(const key of ['start','end']){
  $(key+'Search').onclick=()=>searchLocation(key);
  $(key).onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$(key+'Search').click();}else if(event.key==='Escape'){++searchVersions[key];clearTimeout(suggestionTimers[key]);$(key+'Matches').hidden=true;}};
  $(key).oninput=()=>{
    $(key+'Matches').hidden=true;
    ++searchVersions[key];
    clearTimeout(suggestionTimers[key]);
    const query=$(key).value.trim();
    if(!query){
      endpoints[key]=null;
      ++routeVersion;
      const message='Enter a starting point and destination, or pick them on the map.';
      if(ready)clearRoute(message);
      else $('routeStatus').textContent=message;
      return;
    }
    if(hasLocation(key))return;
    $('routeStatus').textContent='Choose a suggestion or press Enter to update the route.';
    if(query.length>=2)suggestionTimers[key]=setTimeout(()=>searchLocation(key,true),150);
  };
}
$('calculate').onclick=async()=>{
  for(const key of ['start','end']){
    if(hasLocation(key))continue;
    if(!$(key).value.trim()){
      $('routeStatus').textContent=key==='start'?'Enter a starting point.':'Enter a destination.';
      $(key).focus();
    }else await searchLocation(key);
    return;
  }
  calculate(true);
};$('detour').oninput=()=>{$('detourLabel').textContent=`Up to ${$('detour').value} min`;};$('detour').onchange=()=>calculate();$('time').oninput=()=>{timeText();clearTimeout(timer);timer=setTimeout(updateSun,180);};$('date').onchange=updateSun;
$('reset').onclick=()=>{if(ready)fit();};

