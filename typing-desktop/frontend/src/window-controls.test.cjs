const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function harness() {
    const calls = [], buttons = {};
    for (const action of ['minimize', 'maximize', 'close']) {
        buttons[action] = {
            dataset: { windowAction: action }, attributes: {},
            addEventListener(event, callback) { this[event] = callback; },
            setAttribute(name, value) { this.attributes[name] = value; },
            querySelector() { return this.icon; },
            icon: { setAttribute(name, value) { this[name] = value; } }
        };
    }
    const desktop = {
        maximized: false,
        async minimize() { calls.push('minimize'); },
        async close() { calls.push('close'); },
        async toggleMaximize() { calls.push('toggleMaximize'); this.maximized = !this.maximized; await this.resized(); },
        async isMaximized() { return this.maximized; },
        async onResized(callback) { this.resized = callback; }
    };
    let ready;
    const context = vm.createContext({
        window: { __TAURI__: { window: { getCurrentWindow: () => desktop } } },
        document: {
            addEventListener(event, callback) { ready = callback; },
            querySelectorAll() { return Object.values(buttons); },
            querySelector() { return buttons.maximize; }
        }
    });
    vm.runInContext(fs.readFileSync(__dirname + '/window-controls.js', 'utf8'), context);
    await ready();
    return { buttons, calls, desktop };
}

test('window buttons minimize, toggle maximize and close the native window', async () => {
    const h = await harness();
    await h.buttons.minimize.click();
    await h.buttons.maximize.click();
    assert.equal(h.buttons.maximize.attributes['aria-label'], '还原');
    assert.equal(h.buttons.maximize.icon.href, '/assets/icons.svg#restore');
    await h.buttons.maximize.click();
    assert.equal(h.buttons.maximize.attributes['aria-label'], '最大化');
    assert.equal(h.buttons.maximize.icon.href, '/assets/icons.svg#maximize');
    await h.buttons.close.click();
    assert.deepEqual(h.calls, ['minimize', 'toggleMaximize', 'toggleMaximize', 'close']);
});

test('native resize updates the maximize label and icon without clicking a button', async () => {
    const h = await harness();
    h.desktop.maximized = true;
    await h.desktop.resized();
    assert.equal(h.buttons.maximize.attributes.title, undefined);
    assert.equal(h.buttons.maximize.icon.href, '/assets/icons.svg#restore');
    assert.deepEqual(h.calls, []);
});
