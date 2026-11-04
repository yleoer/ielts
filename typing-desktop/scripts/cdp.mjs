// Drive the running desktop WebView over CDP (WebView2 remote debugging).
//   node typing-desktop/scripts/cdp.mjs eval "<js expression>"
//   node typing-desktop/scripts/cdp.mjs shot out.png
// Requires the app to be started with CIJIAN_DEVTOOLS_PORT=9333.
import { writeFileSync } from 'node:fs';

const port = process.env.CDP_PORT || 9333;
const [, , command, arg] = process.argv;
const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const page = targets.find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
ws.onmessage = event => {
    const message = JSON.parse(event.data);
    if (pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
};
await new Promise(resolve => { ws.onopen = resolve; });
const send = (method, params = {}) => new Promise(resolve => {
    pending.set(++id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
});

if (command === 'eval') {
    const { result } = await send('Runtime.evaluate', { expression: arg, awaitPromise: true, returnByValue: true });
    console.log(JSON.stringify(result.exceptionDetails ?? result.result.value, null, 1));
} else if (command === 'shot') {
    const { result } = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(arg, Buffer.from(result.data, 'base64'));
    console.log(`wrote ${arg}`);
}
ws.close();
