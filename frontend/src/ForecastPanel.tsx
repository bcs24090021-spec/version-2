import {useEffect,useState} from 'react';
import {LoaderCircle} from 'lucide-react';
import {fmt} from './final-model';
/** Next-day fire spread forecast, refreshed daily by .github/workflows/forecast_daily.yml (forecast/spread_model.py). */
export default function ForecastPanel({country,label}:{country:string;label:string}){
 const [rows,setRows]=useState<string[][]|null>(null),[updated,setUpdated]=useState(''),[error,setError]=useState('');
 const url=import.meta.env.BASE_URL+'data/forecast/latest_'+country+'.csv';
 useEffect(()=>{fetch(url).then(r=>{if(!r.ok)throw Error(`Forecast not available (${r.status})`);return r.text();}).then(t=>setRows(t.trim().split(/\r?\n/).slice(1).map(l=>l.split(',')))).catch(e=>setError(e.message));fetch(import.meta.env.BASE_URL+'data/forecast/updated.txt').then(r=>r.ok?r.text():'').then(t=>setUpdated(t.trim())).catch(()=>{});},[url]);
 if(error)return <div className="final-report"><p role="alert">{error}</p></div>;
 if(!rows)return <div className="final-loading"><LoaderCircle className="spin"/><p>Loading forecast…</p></div>;
 const high=rows.filter(r=>+r[3]>=.5).length,mid=rows.filter(r=>+r[3]>=.2).length;
 return <div className="final-report"><div className="final-report-heading"><span className="eyebrow">NEXT-DAY FIRE SPREAD</span><h1>{label}: forecast for {rows[0]?.[0]||'—'}</h1><p>Probability that each ~1 km cell within 5 km of today’s fires has a VIIRS fire tomorrow. Input: NASA FIRMS near-real-time NOAA-20 VIIRS, last 7 days. Updated {updated||'—'} (daily).</p></div>
 <section className="final-card"><h2>{rows.length} cells scored · {high} cells ≥ 50% · {mid} cells ≥ 20%</h2><table className="delivery-score-table"><thead><tr><th>Latitude</th><th>Longitude</th><th>Fire probability</th><th>km to nearest fire today</th></tr></thead><tbody>{rows.slice(0,15).map(r=><tr key={r[1]+r[2]}><td>{r[1]}</td><td>{r[2]}</td><td>{fmt(+r[3]*100,1)}%</td><td>{r[4]}</td></tr>)}</tbody></table><a href={url} download>Download all cells (CSV)</a></section>
 <section className="final-card"><h2>How reliable</h2><p>Gradient-boosted trees trained on S-NPP VIIRS 2012–2018, tested on 2019–2020 (never seen). It ranks tomorrow’s fire cells better than the persistence baseline (“tomorrow’s fire is where today’s fire is”): Malaysia AUC 0.908 vs 0.874, new fires &gt;1 km away 0.763 vs 0.668; Argentina 0.870 vs 0.833 and 0.743 vs 0.667. A probability, not a guarantee; NOAA-20 is the same 375 m sensor type as the S-NPP training data.</p></section></div>;
}
