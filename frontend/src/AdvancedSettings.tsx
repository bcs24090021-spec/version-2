import {useState} from 'react';
import FilterControls from './FilterControls';
import type {Filters} from './selection';

export default function AdvancedSettings({value,onApply}:{value:Filters;onApply:(filters:Filters)=>void}){
 const [draft,setDraft]=useState<Filters>(()=>({...value}));
 return <form className="map-advanced-panel" aria-label="Advanced map settings" onSubmit={event=>{
  event.preventDefault();
  const {sensors,platforms,grid,confidence,modisMax,viirs}=draft;
  onApply({...value,sensors,platforms,grid,confidence,modisMax,viirs});
 }}>
  <strong>Advanced settings</strong>
  <FilterControls value={draft} prefix="map" onChange={setDraft}/>
  <div className="advanced-apply"><button type="submit" className="primary-button">Apply changes</button></div>
 </form>;
}
