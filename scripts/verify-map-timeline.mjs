import {chromium,expect} from '@playwright/test';
import {options} from './browser-options.mjs';
const browser=await chromium.launch(options);
try{
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const row=(date,time,lat)=>[lat,112,date,time,'Terra','MODIS','90',10,'D',300];
 let fixtureRows=[row('2019-01-02','0010',2),row('2019-01-01','1200',3),row('2019-01-01','0930',4),row('2019-01-01','1200',5)];
 await page.route('**/data/sample.json',route=>route.fulfill({json:{metadata:{title:'Timeline verification',start:'2019-01-01',end:'2019-01-02',note:'Test observations',coverage:[]},rows:fixtureRows}}));
 await page.goto(process.env.BASE_URL||'http://127.0.0.1:5173',{waitUntil:'domcontentloaded'});
 const checkbox=page.getByRole('checkbox',{name:'Timeline',exact:true}),slider=page.getByRole('slider',{name:'Hotspot detection time'}),count=page.locator('.explorer-count strong');
 await expect(checkbox).toBeVisible();await expect(checkbox).not.toBeChecked();await expect(slider).toHaveCount(0);await expect(count).toHaveText('4');
 await checkbox.check();await expect(slider).toHaveAttribute('max','2');await expect(count).toHaveText('1');
 await expect(slider).toHaveAttribute('aria-valuetext','Hotspots detected through 2019-01-01 09:30 UTC');
 await expect(page.getByRole('region',{name:'Hotspot detection timeline'}).getByRole('button')).toHaveCount(0);
 await slider.focus();await page.keyboard.press('ArrowRight');await expect(count).toHaveText('3');
 await expect(slider).toHaveAttribute('aria-valuetext','Hotspots detected through 2019-01-01 12:00 UTC');
 await page.keyboard.press('End');await expect(count).toHaveText('4');
 await page.keyboard.press('Home');await expect(count).toHaveText('1');
 for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
  await page.setViewportSize(viewport);await slider.scrollIntoViewIfNeeded();
  const box=await page.locator('.map-timeline').boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(viewport.width);
  const controls=await page.locator('.map-bottom').boundingBox();expect(controls.y+controls.height).toBeLessThanOrEqual(box.y);
 }
 await checkbox.uncheck();await expect(slider).toHaveCount(0);await expect(count).toHaveText('4');
 fixtureRows=[row('2019-01-01','0930',4)];await page.reload({waitUntil:'domcontentloaded'});await checkbox.check();await expect(slider).toBeDisabled();await expect(count).toHaveText('1');
 fixtureRows=[];await page.reload({waitUntil:'domcontentloaded'});await checkbox.check();await expect(slider).toBeDisabled();await expect(count).toHaveText('0');
 await page.setViewportSize({width:1440,height:900});await page.getByRole('button',{name:'Historical record',exact:true}).click();
 await expect(checkbox).toBeVisible({timeout:90000});await expect(slider).toHaveCount(0);
 const historicalCount=page.locator('.final-map-count strong'),original=await historicalCount.innerText();
 await checkbox.check();await expect(slider).toBeVisible();
 const initial=Number((await historicalCount.innerText()).replaceAll(',',''));
 await slider.focus();await page.keyboard.press('End');
 await expect.poll(async()=>Number((await historicalCount.innerText()).replaceAll(',','')),{timeout:15000}).toBeGreaterThan(initial);
 const all=Number((await historicalCount.innerText()).replaceAll(',',''));await page.keyboard.press('Home');
 await expect.poll(async()=>Number((await historicalCount.innerText()).replaceAll(',','')),{timeout:15000}).toBe(initial);
 expect(all).toBeGreaterThan(initial);await checkbox.uncheck();await expect(slider).toHaveCount(0);await expect(historicalCount).toHaveText(original);
 console.log('PASS: optional slider only; exact acquisition time ordering and tied timestamps; cumulative and reverse scrubbing; keyboard; desktop/mobile spacing; historical accumulation and selected-month restoration');
}finally{await browser.close();}
