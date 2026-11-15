import { confidenceAccepted, dateSelected, inBBox, type Filters, type DateInterval } from './selection.ts';
export type Observation = { latitude:number; longitude:number; acq_date:string; acq_time:string; satellite:string; instrument:string; confidence:string; frp:number; daynight:string; brightness:number; is_synthetic?:boolean };
export type Coverage = {sensor:string;start:string;end:string;country?:string;countryId?:string;product?:string;url?:string;bbox?:number[];observedOnly?:boolean;shape?:Shape;dates?:DateInterval[];scopeKey?:string};
export type Dataset = {metadata:{title:string;start:string;end:string;note:string;coverage:Coverage[]};rows:(number|string)[][]};
export type Shape = {type:'Polygon';coordinates:number[][][]}|{type:'MultiPolygon';coordinates:number[][][][]};
export type Fit = {available:boolean;n:number;slope?:number;intercept?:number;r2?:number|null;bias?:number;raw_bias?:number;spread?:number;rmse?:number;scope?:string};
export type Day = {date:string;modis:number|null;viirs:number|null;raw_modis_frp:number|null;raw_viirs_frp:number|null;harmonized_count:number|null;harmonized_frp:number|null;calibrated_viirs:number|null;lower:number|null;upper:number|null;source:string;percentile:number|null;anomaly:number|null;median:number|null;p95:number|null;unusual:boolean;detections:number};
export type Period={year:string;start:string;peak:string;end:string;intensity:number};
export type Analysis={days:Day[];hotspots:Observation[];fit:Fit;frpFit:Fit;monthly:Record<number,{count:Fit;frp:Fit}>;periods:Period[];annual:{year:string;count:number;covered:number}[];cells:number};
export const presets:Record<string,{name:string;sub:string;bbox:number[];center:[number,number];zoom:number}>={
  borneo:{name:'Borneo',sub:'Malaysia archive coverage',bbox:[108,-5,120,8],center:[1.3,113.8],zoom:5},
  malaysia:{name:'Malaysia',sub:'Complete country archive',bbox:[99,.5,120,8],center:[4,109],zoom:5},
  'southeast-asia':{name:'Southeast Asia',sub:'Malaysia archive coverage',bbox:[92,-11,142,28],center:[7,114],zoom:3},
  amazon:{name:'Amazon',sub:'Import observations to explore',bbox:[-75,-20,-45,6],center:[-6,-60],zoom:4},
  california:{name:'California',sub:'Import observations to explore',bbox:[-125,32,-114,43],center:[37,-119],zoom:5},
  australia:{name:'Australia',sub:'Import observations to explore',bbox:[112,-44,154,-10],center:[-26,134],zoom:4},
};
export const decode=(data:Dataset):Observation[]=>data.rows.map(r=>({latitude:+r[0],longitude:+r[1],acq_date:String(r[2]),acq_time:String(r[3]).padStart(4,'0'),satellite:String(r[4]),instrument:String(r[5]),confidence:String(r[6]),frp:+r[7],daynight:String(r[8]),brightness:+r[9]}));
export function parseCSV(text:string):Observation[]{
  const rows:string[][]=[]; let row:string[]=[],cell='',quoted=false;
  for(let i=0;i<text.length;i++){const c=text[i]; if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(cell);cell='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v.trim()))rows.push(row);row=[];cell='';}else cell+=c;}
  if(quoted)throw Error('The CSV contains an unclosed quoted field.');
  if(cell||row.length){row.push(cell);rows.push(row);}
  const headers=rows.shift()?.map(v=>v.trim().replace(/^\uFEFF/,''))||[];
  for(const h of ['latitude','longitude','acq_date','acq_time','confidence','frp'])if(!headers.includes(h))throw Error(`Missing FIRMS column: ${h}`);
  const syntheticColumn=headers.indexOf('is_synthetic'),versionColumn=headers.indexOf('version');
  if(rows.some(values=>(syntheticColumn>=0&&['true','1','yes'].includes((values[syntheticColumn]||'').trim().toLowerCase()))||(versionColumn>=0&&/^SIM/i.test(values[versionColumn]||''))))throw Error('This file contains simulated detections. Use the Historical record workspace; synthetic points cannot be imported as observed fires.');
  return rows.map(values=>{const r=Object.fromEntries(headers.map((h,i)=>[h,values[i]||'']));return {latitude:+r.latitude,longitude:+r.longitude,acq_date:r.acq_date,acq_time:r.acq_time.padStart(4,'0'),satellite:r.satellite||'Unknown',instrument:(r.instrument||(headers.includes('bright_ti4')?'VIIRS':'MODIS')).toUpperCase(),confidence:r.confidence.toLowerCase(),frp:+r.frp,daynight:r.daynight||'',brightness:+(r.brightness||r.bright_ti4||0)};}).filter(r=>Number.isFinite(r.latitude)&&Math.abs(r.latitude)<=90&&Number.isFinite(r.longitude)&&Math.abs(r.longitude)<=180&&Number.isFinite(r.frp)&&r.frp>=0&&/^\d{4}-\d{2}-\d{2}$/.test(r.acq_date)&&!isNaN(Date.parse(r.acq_date))&&/^\d{4}$/.test(r.acq_time)&&+r.acq_time.slice(0,2)<24&&+r.acq_time.slice(2)<60);
}
const median=(v:number[])=>quantile(v,.5);
function quantile(values:number[],p:number){if(!values.length)return 0; const v=[...values].sort((a,b)=>a-b),i=(v.length-1)*p;return v[Math.floor(i)]+(v[Math.ceil(i)]-v[Math.floor(i)])*(i-Math.floor(i));}
export function fitTransfer(input:[number,number][]):Fit{
  const pairs=input.filter(([x,y])=>x>0||y>0),n=pairs.length;
  if(n<20||new Set(pairs.map(p=>p[0])).size<3)return {available:false,n};
  const sample=pairs.filter((_,i)=>i%Math.max(1,Math.ceil(n/120))===0),slopes:number[]=[];
  sample.forEach(([x,y],i)=>sample.slice(i+1).forEach(([x2,y2])=>{if(x2!==x)slopes.push((y2-y)/(x2-x));}));
  const slope=Math.max(0,median(slopes)),intercept=median(pairs.map(([x,y])=>y-slope*x));
  const residual=pairs.map(([x,y])=>(x>0?Math.max(0,slope*x+intercept):0)-y),bias=residual.reduce((a,b)=>a+b,0)/n,mean=pairs.reduce((a,p)=>a+p[1],0)/n;
  const sse=residual.reduce((a,e)=>a+e*e,0),sst=pairs.reduce((a,p)=>a+(p[1]-mean)**2,0);
  return {available:true,n,slope,intercept,bias,raw_bias:pairs.reduce((a,[x,y])=>a+x-y,0)/n,r2:sst?1-sse/sst:null,rmse:Math.sqrt(sse/n),spread:1.96*Math.sqrt(residual.reduce((a,e)=>a+(e-bias)**2,0)/n)};
}
type PreparedRing={points:number[][];west:number;east:number;south:number;north:number;center:number};
function prepareRing(ring:number[][]):PreparedRing {
  const points:number[][]=[];let west=Infinity,east=-Infinity,south=Infinity,north=-Infinity;
  for(const [lng,lat] of ring){let x=lng;const previous=points.at(-1)?.[0];if(previous!==undefined){while(x-previous>180)x-=360;while(x-previous< -180)x+=360;}points.push([x,lat]);west=Math.min(west,x);east=Math.max(east,x);south=Math.min(south,lat);north=Math.max(north,lat);}
  return {points,west,east,south,north,center:(west+east)/2};
}
function inRing(x:number,y:number,ring:PreparedRing){
  if(y<ring.south||y>ring.north)return false;
  while(x-ring.center>180)x-=360;while(x-ring.center< -180)x+=360;
  if(x<ring.west||x>ring.east)return false;
  let inside=false;const points=ring.points;
  for(let i=0,j=points.length-1;i<points.length;j=i++){const [xi,yi]=points[i],[xj,yj]=points[j];if(Math.abs((x-xi)*(yj-yi)-(y-yi)*(xj-xi))<1e-9&&x>=Math.min(xi,xj)&&x<=Math.max(xi,xj)&&y>=Math.min(yi,yj)&&y<=Math.max(yi,yj))return true;if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)inside=!inside;}
  return inside;
}
const preparedShapes=new WeakMap<Shape,PreparedRing[][]>();
export function inShape(r:Pick<Observation,'latitude'|'longitude'>,shape?:Shape){
  if(!shape)return true;
  let polygons=preparedShapes.get(shape);if(!polygons){polygons=(shape.type==='Polygon'?[shape.coordinates]:shape.coordinates).map(p=>p.map(prepareRing));preparedShapes.set(shape,polygons);}
  return polygons.some(p=>inRing(r.longitude,r.latitude,p[0])&&!p.slice(1).some(h=>inRing(r.longitude,r.latitude,h)));
}

const dateRange=(start:string,end:string)=>{const dates:string[]=[];for(let t=Date.parse(start);t<=Date.parse(end);t+=86400000)dates.push(new Date(t).toISOString().slice(0,10));return dates;};
export function analyze(rows:Observation[],coverage:Coverage[],bbox:number[],start:string,end:string,confidence:number,sensors:string[],grid:number,shape?:Shape,options?:Filters):Analysis{
  const seen=new Set<string>();
  const selected=rows.filter(r=>{if(!inBBox(r.longitude,r.latitude,bbox)||!sensors.includes(r.instrument)||!inShape(r,shape)||(options&&!dateSelected(r.acq_date,options.dates)))return false;
    if(!confidenceAccepted(r,options||{confidence,modisMax:100,viirs:['nominal','high'],platforms:['Terra','Aqua','S-NPP','NOAA-20','NOAA-21','Unknown']}))return false;
    const key=[r.acq_date,r.acq_time,r.latitude,r.longitude,r.satellite,r.instrument].join('|');if(seen.has(key))return false;seen.add(key);return true;});
  const grouped=new Map<string,Record<string,{pixels:Map<string,number>;detections:number}>>();const cells=new Set<string>();
  for(const r of selected){if(!grouped.has(r.acq_date))grouped.set(r.acq_date,{});const d=grouped.get(r.acq_date)!;
    d[r.instrument]??={pixels:new Map(),detections:0};const s=d[r.instrument],pixel=`${Math.floor(r.latitude/.01)},${Math.floor(r.longitude/.01)}`;s.pixels.set(pixel,Math.max(s.pixels.get(pixel)||0,r.frp));s.detections++;
    if(r.acq_date>=start&&r.acq_date<=end)cells.add(`${Math.floor(r.latitude/grid)},${Math.floor(r.longitude/grid)}`);}
  const validCoverage=coverage.filter(c=>(!c.bbox||(JSON.stringify(c.bbox)===JSON.stringify(bbox)&&JSON.stringify(c.shape)===JSON.stringify(shape)))&&(!c.country||options?.region===`country:${c.countryId||(c.country==='Malaysia'?'MYS':'')}`));
  const covers=(d:string,s:string)=>sensors.includes(s)&&(!!grouped.get(d)?.[s]?.pixels.size||validCoverage.some(c=>c.sensor===s&&c.start<=d&&c.end>=d&&(!c.dates||dateSelected(d,c.dates))&&(!c.observedOnly||!!grouped.get(d)?.[s]?.pixels.size)));

  const value=(d:string,s:string,metric:string)=>{const p=grouped.get(d)?.[s]?.pixels;return metric==='count'?(p?.size||0):[...(p?.values()||[])].reduce((a,b)=>a+b,0);};
  const informative=[...grouped.keys()].sort().filter(d=>covers(d,'MODIS')&&covers(d,'VIIRS'));
  const fit=(dates:string[],metric:string)=>fitTransfer(dates.map(d=>[value(d,'VIIRS',metric),value(d,'MODIS',metric)]));
  const global={count:fit(informative,'count'),frp:fit(informative,'frp')};
  const monthly:Record<number,{count:Fit;frp:Fit}>={};for(let m=1;m<=12;m++){const f=Object.fromEntries(['count','frp'].map(metric=>{const local=fit(informative.filter(d=>+d.slice(5,7)===m),metric);return [metric,{...(local.available?local:global[metric as 'count'|'frp']),scope:local.available?'month':'AOI fallback'}];}));monthly[m]=f as {count:Fit;frp:Fit};}
  const days:Day[]=dateRange(start,end).filter(d=>!options||dateSelected(d,options.dates)).map(date=>{const mc=covers(date,'MODIS'),vc=covers(date,'VIIRS'),fm=monthly[+date.slice(5,7)];
    const calc=(metric:'count'|'frp')=>{const f=fm[metric],v=value(date,'VIIRS',metric),cv=vc&&f.available?(v>0?Math.max(0,v*f.slope!+f.intercept!):0):null,mv=mc?value(date,'MODIS',metric):null;return {value:mv!==null&&cv!==null?(mv+cv)/2:mv??cv,cv};};
    const count=calc('count'),frp=calc('frp'),spread=count.cv!==null?(fm.count.spread||0)/(mc?2:1):0;
    return {date,modis:mc?value(date,'MODIS','count'):null,viirs:vc?value(date,'VIIRS','count'):null,raw_modis_frp:mc?value(date,'MODIS','frp'):null,raw_viirs_frp:vc?value(date,'VIIRS','frp'):null,harmonized_count:count.value,harmonized_frp:frp.value,calibrated_viirs:count.cv,lower:count.value!==null?Math.max(0,count.value-spread):null,upper:count.value!==null?count.value+spread:null,source:mc&&count.cv!==null?'Both sensors':mc?'MODIS only':count.cv!==null?'Calibrated VIIRS':vc?'Uncalibrated VIIRS':'No coverage',percentile:null,anomaly:null,median:null,p95:null,unusual:false,detections:Object.values(grouped.get(date)||{}).reduce((a,s)=>a+s.detections,0)};
  });
  const known=days.filter(d=>d.harmonized_count!==null),byYear=new Map<string,Day[]>();for(const d of known){const y=d.date.slice(0,4);if(!byYear.has(y))byYear.set(y,[]);byYear.get(y)!.push(d);}
  const doy=(date:string)=>Math.round((Date.parse('2000'+date.slice(4))-Date.parse('2000-01-01'))/86400000);
  const baselineBuckets=Array.from({length:366},()=>[] as {year:string;value:number}[]);for(const d of known){const center=doy(d.date);for(let k=-15;k<=15;k++)baselineBuckets[(center+k+366)%366].push({year:d.date.slice(0,4),value:d.harmonized_count!});}
  for(const d of known){const sample=baselineBuckets[doy(d.date)].filter(p=>p.year!==d.date.slice(0,4));if(sample.length<60||new Set(sample.map(p=>p.year)).size<2)continue;const v=sample.map(p=>p.value),mean=v.reduce((a,b)=>a+b,0)/v.length,sd=Math.sqrt(v.reduce((a,b)=>a+(b-mean)**2,0)/v.length);d.median=median(v);d.p95=quantile(v,.95);d.percentile=100*v.filter(n=>n<d.harmonized_count!).length/v.length;d.anomaly=sd?(d.harmonized_count!-mean)/sd:null;d.unusual=d.harmonized_count!>0&&d.harmonized_count!>d.p95;}
  const periods:Period[]=[],annual:{year:string;count:number;covered:number}[]=[];
  for(const [year,list] of byYear){annual.push({year,count:list.reduce((a,d)=>a+d.harmonized_count!,0),covered:list.length});const rolling=list.map((d,i)=>{const window=list.filter(p=>Math.abs(Date.parse(p.date)-Date.parse(d.date))<=3*86400000);return {d,v:window.reduce((a,p)=>a+p.harmonized_count!,0)/window.length};});const peak=rolling.reduce((a,b)=>b.v>a.v?b:a);const active=rolling.filter(p=>p.v>peak.v*.2&&p.v>0);if(active.length)periods.push({year,start:active[0].d.date,peak:peak.d.date,end:active.at(-1)!.d.date,intensity:peak.v});}
  return {days,hotspots:selected.filter(r=>r.acq_date>=start&&r.acq_date<=end),fit:global.count,frpFit:global.frp,monthly,periods:periods.sort((a,b)=>b.intensity-a.intensity),annual,cells:cells.size};
}
