import {chromium,expect} from '@playwright/test';
import {options} from './browser-options.mjs';
const browser=await chromium.launch(options),base=process.env.BASE_URL||'http://127.0.0.1:5173';
try{
 const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('**/server.arcgisonline.com/**',r=>r.abort());
 for(const country of ['Argentina','Canada','India','United_States']){
  await page.goto(`${base}/?hCountry=${country}&hMonth=2003-03#history`,{waitUntil:'domcontentloaded'});
  await expect(page.getByLabel('Historical country',{exact:true})).toHaveValue(country);
  await expect(page.getByRole('button',{name:'Estimated cells CSV',exact:true})).toBeEnabled({timeout:90000});
  await expect(page.locator('.final-provenance-note')).toContainText('Estimated monthly cells');
  await page.getByLabel('Historical month',{exact:true}).fill('2019-03');
  await expect.poll(async()=>Number((await page.locator('.final-map-count strong').innerText()).replaceAll(',','')),{timeout:90000}).toBeGreaterThan(0);
  await expect(page.getByRole('button',{name:'Estimated cells CSV',exact:true})).toBeDisabled();
  await page.getByRole('checkbox',{name:'Timeline',exact:true}).check();await expect(page.getByRole('slider',{name:'Hotspot detection time'})).toBeVisible();
  console.log('PASS historical estimates, observed month and timeline:',country);
 }
 const ids={Argentina:'ARG',Canada:'CAN',India:'IND',United_States:'USA',Malaysia:'MYS'};
 for(const [country,id] of Object.entries(ids)){
  await page.goto(`${base}/?archive=${country}&region=country:${id}&start=2019-03-01&end=2019-03-31`,{waitUntil:'domcontentloaded'});
  await expect(page.getByLabel('Explorer archive',{exact:true})).toHaveValue(country,{timeout:90000});
  await expect.poll(async()=>Number((await page.locator('.explorer-count strong').innerText()).replaceAll(',','')),{timeout:90000}).toBeGreaterThan(0);
  await expect(page.locator('.sensor-map-key')).toContainText('MODIS');await expect(page.locator('.sensor-map-key')).toContainText('VIIRS');
  console.log('PASS observed explorer archive:',country);
 }
 await page.goto(`${base}/?hCountry=Argentina&hMonth=2019-03#history`,{waitUntil:'domcontentloaded'});
 await page.getByLabel('Historical country',{exact:true}).selectOption('Canada');await page.getByLabel('Historical country',{exact:true}).selectOption('India');
 await expect(page.locator('.analysis-sidebar-heading h2')).toHaveText('India',{timeout:90000});await expect.poll(async()=>Number((await page.locator('.final-map-count strong').innerText()).replaceAll(',','')),{timeout:90000}).toBeGreaterThan(0);
 expect(errors).toEqual([]);console.log('PASS all country views without JavaScript runtime errors');
}finally{await browser.close();}
