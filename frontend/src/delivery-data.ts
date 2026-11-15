import type {Dataset} from './engine';
import type {DateInterval} from './selection';
import type {CalendarMonth,FinalPoint} from './final-model';
import {decodeFinal} from './final-model';
export const deliveryCountries=[{country:'Malaysia',label:'Malaysia',iso:'MYS',bbox:[99,0,120,8]},{country:'Argentina',label:'Argentina',iso:'ARG',bbox:[-74,-56,-53,-21]},{country:'Canada',label:'Canada',iso:'CAN',bbox:[-141,41,-52,84]},{country:'India',label:'India',iso:'IND',bbox:[68,6,98,36]},{country:'United_States',label:'United States',iso:'USA',bbox:[170,18,-66,72]}];
export type CompactRow=(string|number|boolean|null)[];
export type DeliveryManifest={country:string;label:string;iso:string;bbox:number[];start:string;end:string;months:Record<string,{url:string;counts:{modis:number;viirs:number};grid?:string;synthetic?:{url:string;count:number}}>;calendar:CalendarMonth[];screen:{screen_pass:boolean;seeds:{seed:number;mean_wape:number;worst_year_wape:number}[];screen_years:number[];note?:string};sources:{file:string;url:string;sha256:string;sensor:string;product:string;start:string;end:string;country:string}[];downloads:{name:string;url:string;sha256:string}[];cleaning:string};
export type EstimatedCell={latitude:number;longitude:number;value:number;daynight:string;modis:number};
export const deliveryBase=(country:string)=>import.meta.env.BASE_URL+'data/delivery/'+country+'/';
export async function deliveryJSON<T>(url:string,signal?:AbortSignal):Promise<T>{
 const response=await fetch(url,{signal});if(!response.ok)throw Error(`Could not load archive file (${response.status}). Please retry.`);
 const bytes=new Uint8Array(await response.arrayBuffer());
 const text=bytes[0]===31&&bytes[1]===139?await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text():new TextDecoder().decode(bytes);
 return JSON.parse(text) as T;
}
export const loadDeliveryManifest=(country:string,signal?:AbortSignal)=>deliveryJSON<DeliveryManifest>(deliveryBase(country)+'manifest.json',signal);
/** includeSynthetic: also load the 2003-2011 point-level synthetic VIIRS shards (flagged is_synthetic). */
export async function loadDeliveryPoints(manifest:DeliveryManifest,months:string[],signal?:AbortSignal,includeSynthetic=false){
 const chunks:FinalPoint[][]=new Array(months.length);let next=0;
 await Promise.all(Array.from({length:Math.min(3,months.length)},async()=>{while(next<months.length){const index=next++,entry=manifest.months[months[index]];if(!entry){chunks[index]=[];continue;}const block=await deliveryJSON<{modis:CompactRow[];viirs:CompactRow[]}>(deliveryBase(manifest.country)+entry.url,signal);if(block.modis.length!==entry.counts.modis||block.viirs.length!==entry.counts.viirs)throw Error('Incomplete observation shard. Please retry.');chunks[index]=[...decodeFinal(block.modis,'modis'),...decodeFinal(block.viirs,'viirs')];if(includeSynthetic&&entry.synthetic){const sim=await deliveryJSON<CompactRow[]>(deliveryBase(manifest.country)+entry.synthetic.url,signal);if(sim.length!==entry.synthetic.count)throw Error('Incomplete synthetic shard. Please retry.');chunks[index].push(...decodeFinal(sim,'synthetic'));}}}));
 return chunks.flat();
}
export async function loadDeliveryDataset(country:string,dates:DateInterval[],signal?:AbortSignal):Promise<Dataset>{
 const m=await loadDeliveryManifest(country,signal),months=Object.keys(m.months).filter(month=>dates.some(([a,b])=>month>=a.slice(0,7)&&month<=b.slice(0,7)));
 const points=await loadDeliveryPoints(m,months,signal);
 return {metadata:{title:`NASA FIRMS · ${m.label} delivery archive`,start:m.start,end:m.end,note:`${m.label}: 2003–2020. Observed Aqua MODIS and S-NPP VIIRS (2012 onward). ${m.cleaning}`,coverage:m.sources.map(s=>({...s,countryId:m.iso}))},rows:points.map(p=>[p.latitude,p.longitude,p.acq_date,p.acq_time,p.satellite,p.instrument,p.confidence,p.frp,p.daynight,p.brightness])};
}
export async function loadDeliveryGrid(m:DeliveryManifest,month:string,signal?:AbortSignal){
 const path=m.months[month]?.grid;if(!path)return [];
 const rows=await deliveryJSON<(number|string)[][]>(deliveryBase(m.country)+path,signal);
 return rows.map(r=>({latitude:Number(r[0]),longitude:Number(r[1]),daynight:String(r[2]),value:Number(r[3]),modis:Number(r[4])}));
}
