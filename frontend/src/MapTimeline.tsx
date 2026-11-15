import {useMemo,useState,type CSSProperties} from 'react';
import type {Observation} from './engine';
import './map-timeline.css';

export function detectionTime(point:Observation){
 const time=point.acq_time.padStart(4,'0');
 return `${point.acq_date}T${time.slice(0,2)}:${time.slice(2,4)}`;
}
/** Timeline = pick one day; the map shows only the hotspots detected on that day (not a running total). */
export function useHotspotTimeline<T extends Observation>(points:T[],scopeKey:string){
 const [enabled,setEnabled]=useState(false),[position,setPosition]=useState<{scope:string;time:string}|null>(null);
 const times=useMemo(()=>[...new Set(points.map(point=>point.acq_date))].sort(),[points]);
 const cutoff=position?.scope===scopeKey&&times.includes(position.time)?position.time:times[0];
 const visible=useMemo(()=>enabled?points.filter(point=>point.acq_date===cutoff):points,[points,enabled,cutoff]);
 return {enabled,setEnabled,times,cutoff,visible,setCutoff:(time:string)=>setPosition({scope:scopeKey,time})};
}
type TimelineProps={enabled:boolean;setEnabled:(enabled:boolean)=>void;times:string[];cutoff:string|undefined;setCutoff:(time:string)=>void};
export default function MapTimeline({enabled,setEnabled,times,cutoff,setCutoff}:TimelineProps){
 const index=Math.max(0,times.indexOf(cutoff||''));
 return <>
  <label className="timeline-toggle"><input type="checkbox" checked={enabled} onChange={event=>setEnabled(event.target.checked)}/>Timeline{enabled&&cutoff?` · ${cutoff}`:''}</label>
  {enabled&&<div className="map-timeline" role="region" aria-label="Hotspot detection timeline"><input type="range" aria-label="Hotspot detection time" aria-valuetext={cutoff?`Hotspots detected on ${cutoff}`:'No hotspots in this selection'} title={cutoff?`Hotspots on ${cutoff}`:'No hotspots in this selection'} min="0" max={Math.max(0,times.length-1)} step="1" value={index} disabled={times.length<2} style={{'--timeline-progress':`${times.length>1?index/(times.length-1)*100:0}%`} as CSSProperties} onChange={event=>setCutoff(times[+event.target.value])}/></div>}
 </>;
}
