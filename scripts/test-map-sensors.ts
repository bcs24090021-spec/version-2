import assert from 'node:assert/strict';
import {binHotspots,sensorColors} from '../frontend/src/map-detections.ts';
const base={latitude:2,longitude:112,acq_date:'2020-01-01',acq_time:'1200',satellite:'Terra',confidence:'90',frp:10,daynight:'D',brightness:300};
const rows=[{...base,instrument:'MODIS'},{...base,instrument:'VIIRS'},{...base,instrument:'VIIRS',is_synthetic:true}];
const points=binHotspots(rows,.25,false,null);assert.equal(points.length,3);assert.deepEqual(points.map(bin=>[...bin.sensors]),[['MODIS'],['VIIRS'],['VIIRS']]);
const grid=binHotspots(rows,.25,true,null);assert.equal(grid.length,2);assert.deepEqual([...grid[0].sensors],['MODIS','VIIRS']);assert.equal(grid[0].n,2);assert.equal(grid[0].frp,20);assert.equal(grid[1].synthetic,true);
assert.equal(binHotspots(rows,.25,false,'2020-01-02').length,0);assert.equal(new Set(Object.values(sensorColors)).size,4);
console.log('PASS: colocated sensor points stay separate; mixed grid cells combine counts; simulated provenance and date filtering preserved; four distinct colors');
