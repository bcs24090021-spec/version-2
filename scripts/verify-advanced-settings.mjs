import {chromium,expect} from '@playwright/test';
import {options} from './browser-options.mjs';
const browser=await chromium.launch(options);
try {
 const page=await browser.newPage({viewport:{width:1920,height:900}});
 // External satellite tiles are unrelated to these control/state checks.
 await page.route('**/server.arcgisonline.com/**',route=>route.abort());
 await page.goto(process.env.BASE_URL||'http://127.0.0.1:5173');
 await page.getByRole('tab',{name:'Area summary',exact:true}).click();
 for(const viewport of [{width:1920,height:900},{width:1440,height:768},{width:390,height:844}]){
  await page.setViewportSize(viewport);
  const dimensions=await page.locator('#analysis-summary').evaluate(el=>({height:el.clientHeight,content:el.scrollHeight}));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.height+1);
  await expect(page.locator('.area-summary .stat')).toHaveCount(3);
 }
 await page.setViewportSize({width:1920,height:900});
 const toggle=page.getByRole('button',{name:'Tap to close fire activity sidebar',exact:true});
 expect((await toggle.boundingBox()).width).toBe(40);
 await toggle.click();
 const reopen=page.getByRole('button',{name:'Tap to open fire activity sidebar',exact:true});
 await reopen.focus();await page.keyboard.press('Enter');
 await expect(page.locator('.analysis-sidebar')).toBeVisible();
 const share=async()=>{await page.getByRole('button',{name:'Share view',exact:true}).click();return new URL(page.url()).searchParams;};
 const before=await share();
 await page.getByLabel('Advanced settings',{exact:true}).check();
 const panel=page.getByRole('form',{name:'Advanced map settings'});
 await panel.getByLabel('Map grid size',{exact:true}).selectOption('0.5');
 await panel.getByLabel('MODIS minimum confidence',{exact:true}).fill('55');
 await panel.getByLabel('MODIS maximum confidence',{exact:true}).fill('90');
 await panel.getByLabel('Low',{exact:true}).check();
 await panel.getByText('Satellite platforms',{exact:true}).click();
 await panel.getByLabel('Terra',{exact:true}).uncheck();
 await panel.getByLabel('VIIRS',{exact:true}).uncheck();
 const pending=await share();
 for(const key of ['grid','confidence','modisMax','viirs','platforms','sensors'])expect(pending.get(key)).toBe(before.get(key));
 await panel.getByRole('button',{name:'Apply changes',exact:true}).click();
 await expect(panel).toHaveCount(0);
 const after=await share();
 expect(after.get('grid')).toBe('0.5');expect(after.get('confidence')).toBe('55');expect(after.get('modisMax')).toBe('90');
 expect(after.get('viirs').split(',')).toContain('low');expect(after.get('platforms').split(',')).not.toContain('Terra');expect(after.get('sensors')).toBe('MODIS');
 for(const key of ['region','dates','bbox'])expect(after.get(key)).toBe(before.get(key));
 await page.getByLabel('Advanced settings',{exact:true}).check();
 await panel.getByLabel('Map grid size',{exact:true}).selectOption('0.1');
 await page.getByLabel('Advanced settings',{exact:true}).uncheck();
 await page.getByLabel('Advanced settings',{exact:true}).check();
 await expect(panel.getByLabel('Map grid size',{exact:true})).toHaveValue('0.5');
 console.log('PASS: compact summary fits desktop/laptop/phone, narrow tab and keyboard reopening, all advanced changes deferred and applied together, area/dates preserved, closing discards drafts');
} finally {await browser.close();}
