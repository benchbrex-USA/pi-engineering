const {spawn} = require('node:child_process');
const {chromium} = require('./solver/node_modules/playwright');
const fs = require('node:fs');
const root = '/private/tmp/pi-opsgraph-v1.1/solver';
async function main() {
  if (!fs.existsSync(root + '/out/index.html')) throw Error('Missing static export');
  const server = spawn('/usr/bin/python3', ['-m', 'http.server', '49173', '--bind', '127.0.0.1', '--directory', root + '/out']);
  let browser;
  try {
    let response;
    for (let i = 0; i < 100; i++) {
      try { response = await fetch('http://127.0.0.1:49173/'); if (response.status === 200) break; } catch {}
      await new Promise(r => setTimeout(r, 100));
    }
    if (response?.status !== 200) throw Error('HTTP readiness failed');
    console.log('GET / => 200 before Playwright');
    browser = await chromium.launch({headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
    for (const [width, height] of [[390,844],[1280,720],[1440,900]]) {
      const page = await browser.newPage({viewport: {width,height}});
      await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
      const result = await page.goto('http://127.0.0.1:49173/');
      if (result.status() !== 200 || !(await page.locator('body').innerText()).trim()) throw Error('Blank baseline');
      console.log(JSON.stringify({width,height,status:result.status(),title:await page.title()}));
      await page.close();
    }
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve => server.once('exit', resolve));
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
