const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = { window: {}, document: { createElement() {
  return { listeners: {}, attrs: {}, addEventListener(type, fn) { this.listeners[type] = fn; },
    setAttribute(key, value) { this.attrs[key] = value; } };
} } };
vm.runInNewContext(fs.readFileSync('static/js/inline_reels.js', 'utf8'), context);
let button;
let plays = 0;
const video = { muted: true, volume: 1, listeners: {},
  parentElement: { querySelector() { return button; }, append(value) { button = value; } },
  addEventListener(type, fn) { this.listeners[type] = fn; },
  play() { plays++; assert.equal(this.muted, false); return Promise.resolve(); } };
context.window.initializeTouchVideoSound(video);
assert.equal(button.textContent, 'Sound on');
const click = () => button.listeners.click({ stopPropagation() {} });
click();
assert.equal(video.muted, false);
assert.equal(plays, 1);
assert.equal(button.textContent, 'Mute');
click();
assert.equal(video.muted, true);
assert.equal(plays, 1);
video.volume = 0;
click();
assert.equal(video.volume, 1);
assert.equal(video.muted, false);
video.muted = true;
video.listeners.volumechange();
assert.equal(button.textContent, 'Sound on');
const original = button;
context.window.initializeTouchVideoSound(video);
assert.equal(button, original);
console.log('Touch sound toggle: unmute, mute, zero-volume recovery, native state sync, and duplicate guard passed.');
