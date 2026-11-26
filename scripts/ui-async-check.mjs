import assert from 'node:assert/strict';
import {loadChromium,projectPaths} from './ui-test-support.mjs';
const {chromium}=loadChromium();
const {fixtureDir,browserOptions}=projectPaths;
const browser=await chromium.launch(browserOptions);
const page=await browser.newPage({viewport:{width:1440,height:1000}});
page.setDefaultTimeout(10000);
const errors=[];page.on('pageerror',e=>errors.push(e.message));
async function select(){
 await page.waitForFunction(()=>document.querySelector('.image-surface')?.clientWidth===1000);
 const b=await page.locator('.image-surface').boundingBox();
 await page.mouse.move(b.x+20,b.y+20);await page.mouse.down();await page.mouse.move(b.x+580,b.y+160,{steps:10});await page.mouse.up();
}
try{
 await page.goto(process.argv[2] || 'http://127.0.0.1:54226');await page.locator('.connection.ready').waitFor();
 await page.locator('input[type=file]').setInputFiles([`${fixtureDir}/dark-background-ocr-source.png`,`${fixtureDir}/dark-background-edited.png`]);
 await page.getByRole('tab').nth(0).click();await select();
 await page.waitForFunction(()=>document.querySelector('#original-text').value==='20261113');
 await page.locator('#replacement-text').fill('20261114');await page.locator('#font-select').selectOption('yahei');
 let releaseJob, seenJob;const jobGate=new Promise(r=>releaseJob=r),jobSeen=new Promise(r=>seenJob=r);
 await page.route('**/api/jobs/*',async route=>{seenJob();try{await jobGate;await route.continue();}catch{}});
 await page.getByRole('button',{name:'生成精修预览'}).click();await jobSeen;
 await page.getByRole('tab').nth(1).click();releaseJob();
 await page.locator('.job-progress').waitFor({state:'hidden'});
 assert.equal(await page.locator('.report-card').count(),0);assert.equal(await page.locator('#original-text').inputValue(),'');
 await page.getByRole('tab').nth(0).click();await page.locator('.report-card').waitFor();
 console.log('PASS background result belongs to original tab');await page.unroute('**/api/jobs/*');
 await page.getByRole('tab').nth(1).click();
 let releaseOcr,seenOcr;const gate=new Promise(r=>releaseOcr=r),seen=new Promise(r=>seenOcr=r);let first=true;
 await page.route('**/api/ocr',async route=>{if(!first){await route.continue();return;}first=false;seenOcr();try{await gate;await route.continue();}catch{}});
 await select();await seen;await page.locator('#original-text').fill('manual-before-switch');
 await page.getByRole('tab').nth(0).click();releaseOcr();await page.getByRole('tab').nth(1).click();
 await page.waitForFunction(()=>document.querySelector('#ocr-status').textContent.includes('已保留你的手动输入'));
 assert.equal(await page.locator('#original-text').inputValue(),'manual-before-switch');
 console.log('PASS manual text survives switching during pending OCR');await page.unroute('**/api/ocr');
 await page.getByRole('button',{name:'放大',exact:true}).click();
 assert.equal(await page.locator('.zoom-controls > span').innerText(),'250%');
 await page.getByRole('tab').nth(0).click();assert.equal(await page.locator('.zoom-controls > span').innerText(),'200%');
 await page.getByRole('tab').nth(1).click();assert.equal(await page.locator('.zoom-controls > span').innerText(),'250%');
 console.log('PASS zoom isolation');assert.deepEqual(errors,[]);
}finally{await browser.close();}
