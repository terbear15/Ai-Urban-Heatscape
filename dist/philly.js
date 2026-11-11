/* UI for the bounded Philadelphia prototype. No secrets or external routing API. */
const $=id=>document.getElementById(id),fc=features=>({type:'FeatureCollection',features});
const places={rittenhouse:[-75.17175,39.9497],cityhall:[-75.1649,39.9526],love:[-75.1659,39.9541],kimmel:[-75.1654,39.9475]};
const engine=HeatEngine.create(PHILLY);let ready=false,picking=null,result=null,selected='shade',is3d=true,timer;
const empty=fc([]),bounds=[[-75.176,39.946],[-75.158,39.957]];
const methods=$('methods');for(const id of ['about','limits'])$(id).onclick=()=>methods.showModal();methods.querySelector('.close').onclick=()=>methods.close();$('exploreTab').onclick=()=>document.querySelector('.workspace').scrollIntoView({behavior:'smooth'});
function err(text){$('mapError').hidden=false;$('mapError').textContent=text;}
let map;
try{map=new maplibregl.Map({container:'map',center:[-75.1673,39.9518],zoom:15.4,pitch:48,bearing:-18,maxPitch:65,minZoom:12,maxZoom:19,style:{version:8,sources:{base:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'],tileSize:256,maxzoom:16,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · Tiles © Esri'}},layers:[{id:'background',type:'background',paint:{'background-color':'#e9ede2'}},{id:'basemap',type:'raster',source:'base',paint:{'raster-saturation':-.8,'raster-opacity':.75}}]},attributionControl:true});}catch(e){err('This browser could not start the 3D map. Please open this prototype in a WebGL-enabled browser.');$('calculate').disabled=true;}
const markers={};
const endpoints={start:{label:'Rittenhouse Square',point:places.rittenhouse},end:{label:'LOVE Park',point:places.love}};
function coord(key){
  if(endpoints[key].label!==$(key).value.trim()) throw new Error('Search for the edited location, then choose a result.');
  return endpoints[key].point;
}
let locationWorker, searchId=0;
const searches=new Map();
function lookup(query,address=false,suggest=false){
  if(!locationWorker){
    locationWorker=new Worker('location/worker.js?v=autocomplete');
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
    locationWorker.postMessage({id,query,address,suggest});
  });
}
function useLocation(key,label,point){
  if(point[0]<bounds[0][0]||point[0]>bounds[1][0]||point[1]<bounds[0][1]||point[1]>bounds[1][1]){
    throw new Error('That location is outside this map’s Center City routing area. Choose a closer address or place.');
  }
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
function fit(){if(result){const b=new maplibregl.LngLatBounds();[...result.fast.coords,...result.shade.coords].forEach(p=>b.extend(p));map.fitBounds(b,{padding:{top:90,bottom:110,left:80,right:60},maxZoom:16,pitch:is3d?48:0,bearing:is3d?-18:0,duration:700});}else map.fitBounds(bounds,{padding:50});}
function selectRoute(which){selected=which;document.querySelectorAll('.route-card').forEach(b=>{const active=b.dataset.route===which;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});map.setPaintProperty('fast','line-opacity',which==='fast'?1:.65);map.setPaintProperty('shade-route','line-opacity',which==='shade'?1:.6);map.moveLayer(which==='shade'?'shade-route':'fast');}
function calculate(zoom=false){if(!ready||['start','end'].some(key=>endpoints[key].label!==$(key).value.trim()))return;try{result=engine.routes(coord('start'),coord('end'),+$('detour').value);map.getSource('fast').setData(feature(result.fast));map.getSource('shade-route').setData(feature(result.shade));marker('start',result.start.coord);marker('end',result.end.coord);const gain=(result.fast.exposure-result.shade.exposure)/80.4672;const card=(key,title,tag)=>{const r=result[key],minutes=r.length/80.4672,sun=r.exposure/80.4672;return `<button class="route-card ${key==='fast'?'direct':''}" data-route="${key}" aria-pressed="false"><div class="card-title">${title}<small>${tag}</small></div><div class="route-stats"><strong>${Math.round(minutes)} <span>min</span></strong><span>· ${(r.length/1609.344).toFixed(2)} mi</span></div><div class="sun-bar"><i style="width:${r.exposure/r.length*100}%"></i></div><div class="card-foot"><span>~${sun.toFixed(1)} min modeled sun</span><span>${Math.round((1-r.exposure/r.length)*100)}% shade</span></div></button>`;};$('results').innerHTML=card('shade','Lower-sun candidate','MODELED')+card('fast','Shortest walk','BASELINE')+`<p class="result-note">${gain>.1?`About ${gain.toFixed(1)} fewer minutes in modeled direct sun, for ${((result.shade.length-result.fast.length)/80.4672).toFixed(1)} extra walking minutes.`:'No meaningful lower-exposure alternative found within this allowance.'} Building shade only; street-centerline estimates.</p>`;document.querySelectorAll('.route-card').forEach(b=>b.onclick=()=>selectRoute(b.dataset.route));selectRoute(selected);$('routeStatus').textContent=`3 mph estimate · Points snapped ${Math.round(result.start.meters*3.28084)} ft / ${Math.round(result.end.meters*3.28084)} ft to network; those gaps excluded.`;if(zoom)fit();}catch(e){result=null;map.getSource('fast').setData(empty);map.getSource('shade-route').setData(empty);$('results').innerHTML='';$('routeStatus').textContent=e.message;}}
function timeText(){const t=+$('time').value,h=Math.floor(t),m=Math.round((t-h)*60);$('timeLabel').textContent=`${h%12||12}:${String(m).padStart(2,'0')} ${h>=12?'PM':'AM'}`;return {h,m};}
function updateSun(){if(!ready)return;const {h,m}=timeText(),date=$('date').value;if(!date||!$('date').checkValidity()){ $('routeStatus').textContent='Choose a summer date between June 1 and August 31, 2026.';return; }$('calculate').disabled=true;const sun=SunCalc.getPosition(new Date(`${date}T${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:00-04:00`),39.9515,-75.167);const shadows=engine.updateShade(sun.azimuth,sun.altitude);map.getSource('shadows').setData(shadows);map.setLight({anchor:'map',position:[1.5,(sun.azimuth*180/Math.PI+180+360)%360,90-sun.altitude*180/Math.PI],intensity:.35});$('solarLabel').textContent=`Sun elevation ${Math.round(sun.altitude*180/Math.PI)}° · Summer scenario, not live`;calculate();$('calculate').disabled=false;}
if(map){map.addControl(new maplibregl.NavigationControl({visualizePitch:true}),'top-right');map.addControl(new maplibregl.ScaleControl({unit:'imperial'}),'bottom-right');map.on('error',e=>{if(e.sourceId==='base')err('Background tiles unavailable. Local building and route data are still displayed.');});map.on('load',()=>{
map.addSource('network',{type:'geojson',data:fc(PHILLY.edges.map(e=>({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[e.p,e.q]}})))});map.addLayer({id:'network',type:'line',source:'network',paint:{'line-color':'#fdfdf8','line-width':3,'line-opacity':.75}});
map.addSource('shadows',{type:'geojson',data:empty});map.addLayer({id:'shadows',type:'fill',source:'shadows',paint:{'fill-color':'#a7b3a3','fill-opacity':1,'fill-antialias':false}});
map.addSource('buildings',{type:'geojson',data:PHILLY.buildings});map.addLayer({id:'buildings',type:'fill-extrusion',source:'buildings',paint:{'fill-extrusion-color':['case',['==',['get','basis'],'assumed 39 ft'],'#d1d4bd','#e1decb'],'fill-extrusion-height':['get','height'],'fill-extrusion-opacity':.92}});
map.addSource('boundary',{type:'geojson',data:fc([{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[bounds[0],[bounds[1][0],bounds[0][1]],bounds[1],[bounds[0][0],bounds[1][1]],bounds[0]]]}}])});map.addLayer({id:'boundary',type:'line',source:'boundary',paint:{'line-color':'#8e9d80','line-width':1.5,'line-dasharray':[3,3]}});
for(const [id,color,width] of [['fast','#cc855c',4],['shade-route','#2c7654',6]]){map.addSource(id,{type:'geojson',data:empty});map.addLayer({id,type:'line',source:id,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':color,'line-width':width}});}
ready=true;updateSun();fit();
map.on('click',e=>{if(picking){const p=[e.lngLat.lng,e.lngLat.lat];if(p[0]<bounds[0][0]||p[0]>bounds[1][0]||p[1]<bounds[0][1]||p[1]>bounds[1][1]){ $('routeStatus').textContent='Pick inside the dashed Center City study boundary.';return;}useLocation(picking,'Map pin · '+p[1].toFixed(5)+', '+p[0].toFixed(5),p);picking=null;map.getCanvas().style.cursor='';document.querySelectorAll('.pick-row button').forEach(b=>b.classList.remove('active'));calculate();return;}const f=map.queryRenderedFeatures(e.point,{layers:['buildings']})[0];if(f){const el=document.createElement('div'),title=document.createElement('strong'),body=document.createElement('p');title.textContent=f.properties.name;body.textContent=`${Math.round(f.properties.height*3.28084)} ft · ${f.properties.basis}. Approximate geometry; no tree shade included.`;el.append(title,body);new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(el).addTo(map);}});
});}
for(const [id,key] of [['pickStart','start'],['pickEnd','end']])$(id).onclick=()=>{if(!ready)return;picking=picking===key?null:key;document.querySelectorAll('.pick-row button').forEach(b=>b.classList.toggle('active',b.id===id&&!!picking));map.getCanvas().style.cursor=picking?'crosshair':'';$('routeStatus').textContent=picking?`Click inside the dashed study boundary to choose your ${key}.`:'Map selection canceled.';};
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
for(const [id,three] of [['flat',false],['three',true]])$(id).onclick=()=>{if(!ready)return;is3d=three;map.easeTo({pitch:three?48:0,bearing:three?-18:0,duration:600});map.setPaintProperty('buildings','fill-extrusion-height',three?['get','height']:0);for(const k of ['flat','three']){$(k).classList.toggle('selected',k===id);$(k).setAttribute('aria-pressed',String(k===id));}};$('reset').onclick=()=>{if(ready)fit();};

