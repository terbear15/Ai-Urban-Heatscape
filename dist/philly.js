/* UI for the Philadelphia walking and shade map. No secrets or external routing API. */
const $=id=>document.getElementById(id),fc=features=>({type:'FeatureCollection',features});
const places={rittenhouse:[-75.17175,39.9497],cityhall:[-75.1649,39.9526],love:[-75.1659,39.9541],kimmel:[-75.1654,39.9475]};
const engine=HeatEngine.create(PHILLY);let ready=false,picking=null,result=null,selected='shade',timer;
const empty=fc([]),bounds=[[-75.176,39.946],[-75.158,39.957]];
const methods=$('methods');for(const id of ['about','limits'])$(id).onclick=()=>methods.showModal();methods.querySelector('.close').onclick=()=>methods.close();$('exploreTab').onclick=()=>document.querySelector('.workspace').scrollIntoView({behavior:'smooth'});
function err(text){$('mapError').hidden=false;$('mapError').textContent=text;}
let map;
try{map=new maplibregl.Map({container:'map',center:[-75.1673,39.9518],zoom:15.4,maxPitch:0,dragRotate:false,pitchWithRotate:false,minZoom:9,maxZoom:19,style:{version:8,sources:{base:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'],tileSize:256,maxzoom:16,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · Tiles © Esri'}},layers:[{id:'background',type:'background',paint:{'background-color':'#e9ede2'}},{id:'basemap',type:'raster',source:'base',paint:{'raster-saturation':-.8,'raster-opacity':.75}}]},attributionControl:true});}catch(e){err('This browser could not start the 3D map. Please open this prototype in a WebGL-enabled browser.');$('calculate').disabled=true;}
const markers={};
const endpoints={start:{label:'Rittenhouse Square',point:places.rittenhouse},end:{label:'LOVE Park',point:places.love}};
function coord(key){
  if(endpoints[key].label!==$(key).value.trim()) throw new Error('Search for the edited location, then choose a result.');
  return endpoints[key].point;
}
let locationWorker, searchId=0;
const searches=new Map();
function lookup(query,address=false,suggest=false){return requestLocation({query,address,suggest});}
function requestLocation(payload){
  if(!locationWorker){
    locationWorker=new Worker('location/worker.js?v=street-map');
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
  if(['start','end'].every(k=>endpoints[k].label===$(k).value.trim()))calculate(true);
  else $('routeStatus').textContent='Search for the other location to compare routes.';
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
function fit(){if(result){const b=new maplibregl.LngLatBounds();[...result.fast.coords,...result.shade.coords].forEach(p=>b.extend(p));map.fitBounds(b,{padding:{top:90,bottom:110,left:80,right:60},maxZoom:16,duration:700});}else map.fitBounds(bounds,{padding:50});}
function selectRoute(which){selected=which;document.querySelectorAll('.route-card').forEach(b=>{const active=b.dataset.route===which;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});map.setPaintProperty('fast','line-opacity',which==='fast'?1:.65);map.setPaintProperty('shade-route','line-opacity',which==='shade'?1:.6);map.moveLayer(which==='shade'?'shade-route':'fast');}
function showRoute(route, zoom){
  const hasShadeDetour=Boolean(route.shade && route.shade!==route.fast);
  const hasExposure=Number.isFinite(route.fast.exposure);
  result={...route,shade:route.shade||route.fast};
  map.getSource('fast').setData(feature(route.fast));
  map.getSource('shade-route').setData(hasShadeDetour?feature(route.shade):empty);
  marker('start',route.start.coord);
  marker('end',route.end.coord);

  function card(key,title,tag){
    const r=result[key];
    const minutes=r.length/80.4672;
    const shadeDetails=hasExposure?`<div class="sun-bar"><i style="width:${r.exposure/r.length*100}%"></i></div>
      <div class="card-foot"><span>~${(r.exposure/80.4672).toFixed(1)} min modeled sun</span>
      <span>${Math.round((1-r.exposure/r.length)*100)}% shade</span></div>`:'';
    return `<button class="route-card ${key==='fast'?'direct':''}" data-route="${key}" aria-pressed="false">
      <div class="card-title">${title}<small>${tag}</small></div>
      <div class="route-stats"><strong>${Math.round(minutes)} <span>min</span></strong>
      <span>· ${(r.length/1609.344).toFixed(2)} mi</span></div>${shadeDetails}</button>`;
  }

  let note='The search found no lower-sun route within your per-detour time limit.';
  if(!hasExposure)note='Building shade could not be loaded for this trip. Try again to compare routes.';
  if(hasShadeDetour){
    const saved=(route.fast.exposure-route.shade.exposure)/80.4672;
    const added=(route.shade.length-route.fast.length)/80.4672;
    note=`About ${saved.toFixed(1)} fewer minutes in modeled direct sun for ${added.toFixed(1)} extra walking minutes total.`;
  }
  $('results').innerHTML=(hasShadeDetour?card('shade','Lower-sun candidate','MODELED'):'')+
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
  if(!ready||['start','end'].some(key=>endpoints[key].label!==$(key).value.trim()))return;
  const trip=[coord('start'),coord('end')];
  const version=++routeVersion;
  if(trip.every(inShadeArea)){
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
  trip.push(citySun.azimuth,citySun.altitude,+$('detour').value);
  const key=JSON.stringify(trip);
  if(!zoom&&result?.cityKey===key){
    return;
  }
  $('routeStatus').textContent='Comparing building shade along the walk…';
  try{
    if(pendingCityTrip?.key!==key){
      const promise=requestLocation({trip});
      pendingCityTrip={key,promise};
      const clear=()=>{if(pendingCityTrip?.promise===promise)pendingCityTrip=null;};
      promise.then(clear,clear);
    }
    const route=await pendingCityTrip.promise;
    if(version!==routeVersion||['start','end'].some(k=>endpoints[k].label!==$(k).value.trim()))return;
    showRoute({...route,cityKey:key},zoom || !result?.cityKey);
  }catch(error){
    if(version===routeVersion)clearRoute(error.message);
  }
}
function clearRoute(message){
  result=null;
  map.getSource('fast').setData(empty);
  map.getSource('shade-route').setData(empty);
  for(const key of Object.keys(markers)){markers[key].remove();delete markers[key];}
  $('results').replaceChildren();
  $('routeStatus').textContent=message;
}
$('cityOverview').onclick=()=>{
  if(ready)map.fitBounds(cityBounds,{padding:45,duration:650});
};
let citySun, localSun;
function timeText(){const t=+$('time').value,h=Math.floor(t),m=Math.round((t-h)*60);$('timeLabel').textContent=`${h%12||12}:${String(m).padStart(2,'0')} ${h>=12?'PM':'AM'}`;return {h,m};}
function updateSun(){if(!ready)return;const {h,m}=timeText(),date=$('date').value;if(!date||!$('date').checkValidity()){ $('routeStatus').textContent='Choose a summer date between June 1 and August 31, 2026.';return; }$('calculate').disabled=true;const sun=SunCalc.getPosition(new Date(`${date}T${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:00-04:00`),39.9515,-75.167);citySun=sun;$('solarLabel').textContent=`Sun elevation ${Math.round(sun.altitude*180/Math.PI)}° · Summer scenario, not live`;calculate();$('calculate').disabled=false;}
if(map){map.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');map.addControl(new maplibregl.ScaleControl({unit:'imperial'}),'bottom-right');map.on('error',e=>{if(e.sourceId==='base')err('Background tiles unavailable. Route lines are still available.');});map.on('load',()=>{
map.addSource('city-limits',{type:'geojson',data:'location/city-boundary.geojson'});
map.addLayer({id:'city-tint',type:'fill',source:'city-limits',paint:{'fill-color':'#91b79a','fill-opacity':.24}});
map.addLayer({id:'city-limits',type:'line',source:'city-limits',paint:{'line-color':'#58755e','line-width':1.6,'line-opacity':.85}});
map.addSource('boundary',{type:'geojson',data:fc([{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[bounds[0],[bounds[1][0],bounds[0][1]],bounds[1],[bounds[0][0],bounds[1][1]],bounds[0]]]}}])});map.addLayer({id:'boundary',type:'line',source:'boundary',paint:{'line-color':'#8e9d80','line-width':1.5,'line-dasharray':[3,3]}});
for(const [id,color,width] of [['fast','#cc855c',4],['shade-route','#2c7654',6]]){map.addSource(id,{type:'geojson',data:empty});map.addLayer({id,type:'line',source:id,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':color,'line-width':width}});}
ready=true;updateSun();map.fitBounds(cityBounds,{padding:42,duration:0});
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
    if(endpoints[key].label===query)return;
    $('routeStatus').textContent='Choose a suggestion or press Enter to update the route.';
    if(query.length>=3)suggestionTimers[key]=setTimeout(()=>searchLocation(key,true),250);
  };
}
$('calculate').onclick=async()=>{
  for(const key of ['start','end'])if(endpoints[key].label!==$(key).value.trim()){await searchLocation(key);return;}
  calculate(true);
};$('detour').oninput=()=>{$('detourLabel').textContent=`Up to ${$('detour').value} min`;};$('detour').onchange=()=>calculate();$('time').oninput=()=>{timeText();clearTimeout(timer);timer=setTimeout(updateSun,180);};$('date').onchange=updateSun;
$('reset').onclick=()=>{if(ready)fit();};

