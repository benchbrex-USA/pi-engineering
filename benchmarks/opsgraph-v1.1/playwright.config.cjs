const {defineConfig} = require('./solver/node_modules/@playwright/test');
module.exports = defineConfig({
  testDir: '/private/tmp/pi-opsgraph-v1.1/solver/tests', workers: 2, timeout: 60000,
  use: {baseURL: 'http://127.0.0.1:49173', headless: true,
    launchOptions: {executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}},
  webServer: {
    command: 'python3 -m http.server 49173 --bind 127.0.0.1 --directory /private/tmp/pi-opsgraph-v1.1/solver/out',
    cwd: '/private/tmp/pi-opsgraph-v1.1/solver',
    url: 'http://127.0.0.1:49173', reuseExistingServer: false
  }, reporter: 'list'
});
