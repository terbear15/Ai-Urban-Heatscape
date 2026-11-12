/* UI for the Philadelphia walking and shade map. No secrets or external routing API. */
const $=id=>document.getElementById(id),fc=features=>({type:'FeatureCollection',features});
const engine=HeatEngine.create(PHILLY);let ready=false,picking=null,result=null,selected='shade',timer;
const empty=fc([]),bounds=[[-75.176,39.946],[-75.158,39.957]];
const methods=$('methods');for(const id of ['about','limits'])$(id).onclick=()=>methods.showModal();methods.querySelector('.close').onclick=()=>methods.close();$('exploreTab').onclick=()=>document.querySelector('.workspace').scrollIntoView({behavior:'smooth'});
function err(text){$('mapError').hidden=false;$('mapError').textContent=text;}
let map;
try{map=new maplibregl.Map({container:'map',center:[-75.1673,39.9518],zoom:15.4,maxPitch:0,dragRotate:false,pitchWithRotate:false,minZoom:9,maxZoom:19,style:{version:8,sources:{base:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],tileSize:256,maxzoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · Imagery © Esri and contributors'}},layers:[{id:'background',type:'background',paint:{'background-color':'#e9ede2'}},{id:'basemap',type:'raster',source:'base',paint:{'raster-fade-duration':0}}]},attributionControl:true});}catch(e){err('This browser could not start the map. Please open this prototype in a WebGL-enabled browser.');$('calculate').disabled=true;}
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
function lookup(query,address=false,suggest=false){return requestLocation({query,address,suggest});}
function requestLocation(payload){
  if(!locationWorker){
    locationWorker=new Worker('location/worker.js?v=seasons');
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
  if(!query){$('routeStatus').textContent='Enter a Philadelphia address or place name.';return;}
  list.hidden=true;
  if(!suggest){
    button.disabled=true;
    $('routeStatus').textContent='Searching Philadelphia…';
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
    `<p class="result-note">${note}${hasExposure?' Building shade only; street-centerline estimates.':''}</p>`;
  document.querySelectorAll('.route-card').forEach(button=>button.onclick=()=>selectRoute(button.dataset.route));
  selectRoute(hasShadeDetour?selected:'fast');
  if(!hasShadeDetour)selected='shade';
  $('routeStatus').textContent=`3 mph estimate · Points snapped ${Math.round(route.start.meters*3.28084)} ft / ${Math.round(route.end.meters*3.28084)} ft to the network; those gaps excluded.`;
  if(zoom)fit();
}
const cityBounds=[[-75.28026599998037,39.867464000224096],[-74.95576300016803,40.13799199984529]];
const inShadeArea=([x,y])=>x>=bounds[0][0]&&x<=bounds[1][0]&&y>=bounds[0][1]&&y<=bounds[1][1];
let routeVersion=0, pendingCityTrip;
async function calculate(zoom=false){
  if(!ready||!hasTrip())return;
  const trip=[coord('start'),coord('end')];
  const version=++routeVersion;
  if(season==='summer'&&trip.every(inShadeArea)){
    try{
      if(citySun && localSun!==citySun){
        engine.updateShade(citySun.azimuth,citySun.altitude,false);
        localSun=citySun;
      }
      showRoute(engine.routes(...trip,+$('detour').value),zoom);
    }
    catch(error){clearRoute(error.message);}
    return;
  }
  if(!citySun)return;
  trip.push(citySun.azimuth,citySun.altitude,+$('detour').value,season);
  const key=JSON.stringify(trip);
  if(!zoom&&result?.cityKey===key){
    return;
  }
  $('routeStatus').textContent=season==='winter'?'Finding sunnier streets within your time limit…':'Comparing building shade along the walk…';
  try{
    if(pendingCityTrip?.key!==key){
      const promise=requestLocation({trip});
      pendingCityTrip={key,promise};
      const clear=()=>{if(pendingCityTrip?.promise===promise)pendingCityTrip=null;};
      promise.then(clear,clear);
    }
    const route=await pendingCityTrip.promise;
    if(version!==routeVersion||!hasTrip())return;
    showRoute({...route,cityKey:key},zoom || !result?.cityKey);
  }catch(error){
    if(version===routeVersion)clearRoute(error.message);
  }
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
  summer:{min:'2026-06-01',max:'2026-08-31',date:'2026-07-15',hour:'15',last:'19',offset:'-04:00',zone:'EDT'},
  winter:{min:'2026-12-01',max:'2027-02-28',date:'2027-01-15',hour:'12',last:'17',offset:'-05:00',zone:'EST'},
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
  $('summerMode').setAttribute('aria-pressed',String(!winter));
  $('winterMode').setAttribute('aria-pressed',String(winter));
  $('seasonTitle').textContent=winter?'A little more sun.':'A little more shade.';
  $('walkMode').textContent=winter?'WINTER · SEEK SUN':'SUMMER · SEEK SHADE';
  $('candidateLegend').textContent=winter?'Sunnier route':'Lower-sun route';
  $('summerDetour').hidden=winter;
  $('winterDetour').hidden=!winter;
  $('dateLabel').textContent=winter?'WINTER SCENARIO':'SUMMER SCENARIO';
  $('timezone').textContent=setting.zone;
  $('lastHour').textContent=winter?'5 PM':'7 PM';
  Object.assign($('date'),{min:setting.min,max:setting.max,value:setting.date});
  Object.assign($('time'),{max:setting.last,value:setting.hour});
  timeText();
  if(!ready)return;
  applyRouteColors();
  clearRoute(hasTrip()?'Recalculating your walk…':'Choose a starting point and destination to compare routes.');
  updateSun();
}
function applyRouteColors(){
  const colors=routeColors[season];
  map.setPaintProperty('fast','line-color',colors.fast);
  map.setPaintProperty('shade-route','line-color',colors.candidate);
}
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
  citySun=SunCalc.getPosition(new Date(`${date}T${clock}${setting.offset}`),39.9515,-75.167);
  $('solarLabel').textContent=citySun.altitude<=0?'Sun below the horizon':
    `Sun elevation ${Math.round(citySun.altitude*180/Math.PI)}° · ${season==='winter'?'Winter':'Summer'} scenario`;
  calculate();
}
$('summerMode').onclick=()=>{if(season!=='summer')setSeason('summer');};
$('winterMode').onclick=()=>{if(season!=='winter')setSeason('winter');};
if(new URLSearchParams(location.search).get('season')==='winter')setSeason('winter');
if(map){map.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');map.addControl(new maplibregl.ScaleControl({unit:'imperial'}),'bottom-right');map.on('error',e=>{if(e.sourceId==='base')err('Background tiles unavailable. Route lines are still available.');});map.on('load',()=>{
map.addSource('city-mask',{type:'geojson',data:'location/city-mask.geojson',tolerance:0});
map.addLayer({id:'city-mask',type:'fill',source:'city-mask',paint:{
  'fill-color':'#fff','fill-opacity':.36,'fill-antialias':false,
}});
map.addSource('city-limits',{type:'geojson',data:'location/city-boundary.geojson',tolerance:0});
map.addLayer({id:'city-limits',type:'line',source:'city-limits',paint:{
  'line-color':'#fff','line-width':2,'line-opacity':.95,
}});
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
for(const [id,key] of [['pickStart','start'],['pickEnd','end']])$(id).onclick=()=>{if(!ready)return;picking=picking===key?null:key;document.querySelectorAll('.pick-row button').forEach(b=>b.classList.toggle('active',b.id===id&&!!picking));map.getCanvas().style.cursor=picking?'crosshair':'';$('routeStatus').textContent=picking?`Click on the Philadelphia map to choose your ${key}.`:'Map selection canceled.';};
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
    if(query.length>=3)suggestionTimers[key]=setTimeout(()=>searchLocation(key,true),250);
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

