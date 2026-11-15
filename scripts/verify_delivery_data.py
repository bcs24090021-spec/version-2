"""Validate generated DELIVERY shards without refitting the scientific model."""
from pathlib import Path
import json,gzip,math,calendar
ROOT=Path(__file__).resolve().parents[1]/'frontend/public/data/delivery'
def read(path):return json.loads(gzip.decompress(path.read_bytes())) if path.suffix=='.gz' else json.loads(path.read_text())
def verify():
 total=0
 for country in ['Argentina','Canada','India','United_States','Malaysia']:
  base=ROOT/country;m=read(base/'manifest.json');assert len(m['months'])==216
  assert len(m['sources'])==27 and all(len(s['sha256'])==64 for s in m['sources'])
  assert next(s for s in m['sources'] if s['sensor']=='VIIRS' and s['start'].startswith('2012'))['start']=='2012-01-20'
  calendar_by_month={f"{r['year']}-{r['month']:02}":r for r in m['calendar']}
  for month,entry in m['months'].items():
   block=read(base/entry['url'])
   for sensor in ['modis','viirs']:
    rows=block[sensor];assert len(rows)==entry['counts'][sensor];total+=len(rows)
    if sensor=='viirs' and month<'2012-01':assert not rows
    for r in rows:
     assert r[2].startswith(month) and -90<=r[0]<=90 and -180<=r[1]<=180
     assert len(r[3])==4 and int(r[3][:2])<24 and int(r[3][2:])<60
     assert math.isfinite(r[7]) and r[7]>=0
     assert (sensor=='modis' and r[4]=='Aqua' and 30<=float(r[6])<=100) or (sensor=='viirs' and r[4]=='S-NPP' and r[6] in ['n','h','nominal','high'])
     assert r[5]==('MODIS' if sensor=='modis' else 'VIIRS') and r[13] is False
   if 'grid' in entry:
    cells=read(base/entry['grid']);assert month<'2012-01'
    assert all(len(c)==5 and math.isfinite(c[3]) and c[3]>0 for c in cells)
    assert abs(sum(c[3] for c in cells)-calendar_by_month[month]['value'])<=.051
   if country!='Malaysia' and month>='2012-01':assert calendar_by_month[month]['value']==len(block['viirs'])
  if country!='Malaysia':assert len(m['calendar'])==216 and m['screen']['screen_pass'] is True
  print('PASS',country,'216 monthly shards; coverage, timestamp/schema, counts and estimate reconciliation',flush=True)
 fixed=read(ROOT/'indonesia-corrected.json');score=next(r for r in fixed['averages'] if r['slice']=='all_scored_years' and r['method']=='fusion_G1');assert score['month_wape']==11.53
 assert max(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())<100*1024*1024
 print('PASS',total,'cleaned observed points; corrected Indonesia scores; all assets below GitHub file limit',flush=True)
if __name__=='__main__':verify()
