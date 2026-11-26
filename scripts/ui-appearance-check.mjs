import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {loadChromium,prepareQaDirectories,projectPaths} from './ui-test-support.mjs';
const {chromium}=loadChromium();
const {artifactsDir,fixtureDir,playwrightDir,browserOptions}=projectPaths;
await prepareQaDirectories();
const browser=await chromium.launch(browserOptions);
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
const base=process.argv[2];
const checks=[];
async function verifyLayout(label){
 const result=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,buttons:[...document.querySelectorAll('.generate-button,.adopt-button,.export-button')].map(n=>{const r=n.getBoundingClientRect();return{label:n.textContent,visible:r.width>20&&r.height>20,right:r.right,left:r.left,bottom:r.bottom}})}));
 assert.equal(result.overflow,false,label+' horizontal overflow');
 assert(result.buttons.every(b=>b.visible&&b.left>=0&&b.right<=page.viewportSize().width+1),label+' clipped action buttons');
 if(page.viewportSize().width>760)assert(result.buttons.every(b=>b.bottom<=page.viewportSize().height),label+' unreachable footer');
 checks.push(label);
}
try{
 await page.goto(base);await page.locator('.connection.ready').waitFor();
 await verifyLayout('welcome-1440');
 await page.screenshot({path:`${playwrightDir}/local-0.5-welcome.png`});
 await page.getByRole('button',{name:'使用说明',exact:true}).click();await page.getByRole('dialog').waitFor();
 await page.screenshot({path:`${playwrightDir}/local-0.5-guide.png`});
 await page.getByRole('button',{name:'开始使用',exact:true}).click();
 await page.locator('input[type=file]').setInputFiles([`${fixtureDir}/dark-background-ocr-source.png`,`${fixtureDir}/dark-background-edited.png`]);
 await page.getByRole('tab').nth(0).click();await page.waitForFunction(()=>document.querySelector('.image-surface')?.clientWidth===1000);
 const b=await page.locator('.image-surface').boundingBox();
 await page.mouse.move(b.x+20,b.y+20);await page.mouse.down();await page.mouse.move(b.x+580,b.y+160,{steps:10});await page.mouse.up();
 await page.waitForFunction(()=>document.querySelector('#original-text').value==='20261113');
 await page.locator('#replacement-text').fill('20261114');await page.locator('#font-select').selectOption('yahei');
 const fieldFonts=await page.locator('.text-input').evaluateAll(ns=>ns.map(n=>{const c=getComputedStyle(n);return{type:n.type,size:c.fontSize,variant:c.fontVariantNumeric,family:c.fontFamily,height:n.clientHeight}}));
 assert.deepEqual(fieldFonts[0],fieldFonts[1]);assert.equal(fieldFonts[0].type,'text');assert.equal(fieldFonts[0].size,'18px');
 await page.getByRole('button',{name:'生成精修预览'}).click();await page.locator('.report-card').waitFor();
 await page.locator('.report-card').scrollIntoViewIfNeeded();
 await verifyLayout('preview-1440');
 await page.screenshot({path:`${playwrightDir}/local-0.5-workspace.png`});
 for(const [width,height] of [[1920,1080],[1280,800],[1101,768],[1024,768],[820,650],[760,900],[390,844],[360,740]]){
  await page.setViewportSize({width,height});
  await page.waitForFunction(()=>document.querySelector('.canvas-viewport').clientWidth>0);
  await verifyLayout('preview-'+width);
  if(width===820)await page.screenshot({path:`${playwrightDir}/local-0.5-compact.png`});
  if(width===390)await page.screenshot({path:`${playwrightDir}/local-0.5-narrow.png`,fullPage:true});
 }
 assert.deepEqual(pageErrors,[]);
 await fs.writeFile(`${artifactsDir}/local-0.5-appearance-qa.json`,JSON.stringify({passed:true,checks,pageErrors,fieldFonts},null,2));
 console.log('PASS appearance and responsive checks:',checks.join(', '));
}finally{await browser.close();}
