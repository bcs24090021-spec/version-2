"""Package DELIVERY.zip without running its pipeline. Use the repository's reviewed cleaning code.
PYTHONPATH=<scientific dependencies> python scripts/build_delivery_data.py /path/DELIVERY.zip [Country]
"""
from pathlib import Path
import sys,zipfile,json,gzip,hashlib,io
import pandas as pd
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'FINAL/code'))
from sim_viirs import firms_to_pair_frame,keep_representatives
COUNTRIES={'Argentina':('ARG',[-74,-56,-53,-21]),'Canada':('CAN',[-141,41,-52,84]),'India':('IND',[68,6,98,36]),'United_States':('USA',[170,18,-66,72]),'Malaysia':('MYS',[99,0,120,8])}
DEST=ROOT/'frontend/public/data/delivery'
def write(path,value,compressed=False):
 path.parent.mkdir(parents=True,exist_ok=True);data=json.dumps(value,separators=(',',':'),allow_nan=False).encode()
 path.write_bytes(gzip.compress(data,compresslevel=7,mtime=0) if compressed else data)
def workbook(data):
 book=load_workbook(io.BytesIO(data),read_only=True,data_only=True);out={}
 for sheet in book:
  rows=iter(sheet.values);headers=next(rows,[]);out[sheet.title]=[dict(zip(headers,row)) for row in rows]
 book.close();return out

def build(archive,only=None):
 z=zipfile.ZipFile(archive);catalog=[]
 for country,(iso,bbox) in COUNTRIES.items():
  if only and country!=only:continue
  if (DEST/country/'manifest.json').exists():print('REUSE',country,flush=True);continue
  dest=DEST/country;months={};sources=[];observed={};dedupe={}
  for year in range(2003,2021):
   blocks={f'{year}-{month:02}':{'modis':[],'viirs':[]} for month in range(1,13)}
   for sensor,product,key in [('MODIS','modis','modis'),('VIIRS','viirs-snpp','viirs')]:
    if sensor=='VIIRS' and year<2012:continue
    name=f'{product}_{year}_{country}.csv';member=f'DELIVERY/raw_data/{product}/{name}';data=z.read(member)
    raw=pd.read_csv(io.BytesIO(data),dtype=str,keep_default_na=False)
    frame,removed=keep_representatives(firms_to_pair_frame(raw,sensor,year));dedupe[name]=removed
    numeric=lambda col:pd.to_numeric(frame[col],errors='coerce').fillna(0)
    packed=pd.DataFrame({'lat':numeric('latitude').round(5),'lon':numeric('longitude').round(5),'date':frame.acq_date,'time':frame.acq_time,'satellite':'Aqua' if key=='modis' else 'S-NPP','sensor':sensor,'confidence':frame.confidence.astype(str),'frp':numeric('frp').round(2),'dn':frame.daynight,'brightness':numeric('brightness' if key=='modis' else 'bright_ti4').round(2),'scan':numeric('scan').round(3),'track':numeric('track').round(3),'bright5':numeric('bright_t31' if key=='modis' else 'bright_ti5').round(2),'synthetic':False,'origin':'','parent':'','run':0})
    for month in range(1,13):
     rows=packed[frame.month==month].values.tolist();blocks[f'{year}-{month:02}'][key]=rows
    sources.append({'file':name,'sensor':sensor,'product':product,'start':f'{year}-01-20' if sensor=='VIIRS' and year==2012 else f'{year}-01-01','end':f'{year}-12-31','country':country,'sha256':hashlib.sha256(data).hexdigest(),'rawRecords':len(raw),'records':len(frame),'url':f'https://firms.modaps.eosdis.nasa.gov/data/country/{product}/{year}/{name}'})
   for month,block in blocks.items():
    path=f'points/{month}.json.gz';write(dest/path,block,True)
    months[month]={'url':path,'counts':{k:len(v) for k,v in block.items()}};observed[month]=len(block['viirs'])
   print(country,year,sum(len(b[k]) for b in blocks.values() for k in b),flush=True)
  calendar=[];downloads=[];screen=json.loads(z.read(f'DELIVERY/results/{country}/screen.json').decode('utf-8-sig'))
  if country!='Malaysia':
   predictions=pd.read_csv(z.open(f'DELIVERY/results/{country}/pred_2003_2011_monthly.csv'));cells=pd.read_parquet(io.BytesIO(z.read(f'DELIVERY/results/{country}/pred_2003_2011_cells.parquet')))
   sums=cells.groupby(['year','month']).pred.sum().reset_index().merge(predictions,on=['year','month'])
   if (sums.pred-sums.pred_viirs_count).abs().max()>.051:raise ValueError('Monthly/grid mismatch')
   for (year,month),group in cells[cells.pred>0].groupby(['year','month']):
    key=f'{int(year)}-{int(month):02}';path=f'grids/{key}.json.gz';rows=group[['lat','lon','daynight','pred','m_count']].values.tolist();write(dest/path,rows,True);months[key]['grid']=path
   early={(int(r.year),int(r.month)):float(r.pred_viirs_count) for r in predictions.itertuples()}
   for year in range(2003,2021):
    for month in range(1,13):
     key=f'{year}-{month:02}';calendar.append({'year':year,'month':month,'value':early[(year,month)] if year<2012 else observed[key],'source':'estimated' if year<2012 else 'observed_partial' if key=='2012-01' else 'observed'})
   for row in calendar:
    baseline=float(pd.Series([r['value'] for r in calendar if r['month']==row['month'] and r['source']!='observed_partial']).median());row['median']=baseline;row['anomaly_pct']=(row['value']-baseline)/max(1,baseline)*100
   for file in ['pred_2003_2011_monthly.csv','screen.json','retrain.json']:
    data=z.read(f'DELIVERY/results/{country}/{file}');p=dest/'files'/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);downloads.append({'name':file,'url':'files/'+file,'sha256':hashlib.sha256(data).hexdigest()})
  manifest={'schema':1,'country':country,'label':country.replace('_',' '),'iso':iso,'bbox':bbox,'start':'2003-01-01','end':'2020-12-31','months':months,'calendar':calendar,'screen':screen,'sources':sources,'dedupe':dedupe,'downloads':downloads,'cleaning':'Aqua MODIS / S-NPP only; vegetation fires; nominal/high confidence; exact and same-minute overlapping-footprint duplicate removal.','notes':['Monthly estimates are not observed hotspot locations.','January 2012 S-NPP is partial.','Only country/year/month data requested by the visitor are loaded.']}
  write(dest/'manifest.json',manifest);catalog.append({k:manifest[k] for k in ['country','label','iso','bbox','start','end']})
 for manifest_path in DEST.glob('*/manifest.json'):
  manifest=json.loads(manifest_path.read_text())
  for source in manifest['sources']:
   if source['sensor']=='VIIRS' and source['start'].startswith('2012'):source['start']='2012-01-20'
  write(manifest_path,manifest)
 write(DEST/'catalog.json',[{'country':country,'label':country.replace('_',' '),'iso':iso,'bbox':bbox,'start':'2003-01-01','end':'2020-12-31'} for country,(iso,bbox) in COUNTRIES.items()])
 fixed='DELIVERY/others/indonesia_check/loyo_indonesia_fixed2012.xlsx';data=z.read(fixed);(DEST/'loyo_indonesia_fixed2012.xlsx').write_bytes(data)
 fixedbook=workbook(data);write(DEST/'indonesia-corrected.json',fixedbook)
 reports=ROOT/'frontend/public/data/final/reports.json';r=json.loads(reports.read_text());r['summary']['Indonesia_LOYO_other_metrics']=fixedbook['averages'];r['summary']['Indonesia_LOYO_by_year']=fixedbook['by_year'];write(reports,r)
 for file in ['README.md','reference/README.md','results/README.md']:
  p=DEST/'guides'/file.replace('/','-');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read('DELIVERY/'+file))
 write(DEST/'provenance.json',{'archive':'DELIVERY.zip','sha256':hashlib.sha256(Path(archive).read_bytes()).hexdigest(),'countries':list(COUNTRIES),'screenSummary':'Empty source file; per-country screen.json used.','indonesia':'Corrected 2012 workbook supersedes old workbook and PDF figures.'})
 print('COMPLETE',sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()),flush=True)
if __name__=='__main__':build(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else None)
