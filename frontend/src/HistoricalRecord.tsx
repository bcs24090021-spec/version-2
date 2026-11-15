import {useState} from 'react';
import FinalWorkspace from './FinalWorkspace';
import DeliveryHistory from './DeliveryHistory';
import {deliveryCountries} from './delivery-data';
import './delivery.css';
export default function HistoricalRecord(){
 const [country,setCountry]=useState(()=>{const value=new URLSearchParams(location.search).get('hCountry');return deliveryCountries.some(c=>c.country===value)?value!:'Malaysia';});
 return <div className="historical-record"><div className="historical-country"><label>Historical archive<select aria-label="Historical country" value={country} onChange={e=>{setCountry(e.target.value);const url=new URL(location.href);url.searchParams.set('hCountry',e.target.value);url.searchParams.delete('hShape');url.searchParams.delete('hArea');history.replaceState(null,'',url);}}>{deliveryCountries.map(c=><option key={c.country} value={c.country}>{c.label}</option>)}</select></label><span>2003–2020 · observed records and clearly labeled estimates</span></div>{country==='Malaysia'?<FinalWorkspace/>:<DeliveryHistory key={country} country={country}/>}</div>;
}
