import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import {generatePassword} from "../static/password-generator.mjs";
const {layouts} = JSON.parse(readFileSync(new URL("./fixtures/keyboard-layouts.json", import.meta.url), "utf8"));

test("each length preserves printable ASCII and all requested character groups", () => {
  for (const length of [8, 12, 20, 32, 64, 128]) {
    for (let sample = 0; sample < 50; sample++) {
      const password = generatePassword(length);
      assert.equal(password.length, length);
      assert.match(password, /^[A-Za-z2-9!@#$%&*+\-=?]+$/);
      assert.match(password, /[a-z]/);
      assert.match(password, /[A-Z]/);
      assert.match(password, /[2-9]/);
      assert.match(password, /[!@#$%&*+\-=?]/);
      assert.doesNotMatch(password, /[\s^`~\\'"<>;:0O1Il]/);
    }
  }
});

test("symbols can be disabled for restrictive password fields", () => {
  for (let sample = 0; sample < 100; sample++) {
    const password = generatePassword(24, {symbols:false});
    assert.match(password, /^[A-Za-z2-9]{24}$/);
    assert.match(password, /[a-z]/);
    assert.match(password, /[A-Z]/);
    assert.match(password, /[2-9]/);
  }
});

test("dual-layout passwords type identically through both Arduino HID layout tables", () => {
  const fr = layouts.fr_FR.printable;
  const us = layouts.en_US.printable;
  for (const length of [8, 12, 20, 32, 64, 128]) {
    for (let sample = 0; sample < 50; sample++) {
      const password = generatePassword(length, {symbols:true, dualLayout:true});
      assert.equal(password.length, length);
      assert.match(password, /[a-z]/);
      assert.match(password, /[A-Z]/);
      assert.match(password, /[+=]/);
      assert.doesNotMatch(password, /[0-9aAmMqQwWzZ]/);
      for (const character of password) {
        const index = character.charCodeAt(0) - 32;
        // Simulate a FR-configured board on a US host, then a US board on a FR host.
        assert.equal(us.indexOf(fr[index]), index, `FR → US changes ${character}`);
        assert.equal(fr.indexOf(us[index]), index, `US → FR changes ${character}`);
      }
    }
  }
});

test("dual-layout mode also supports letters only", () => {
  for (let sample = 0; sample < 100; sample++) {
    const password = generatePassword(24, {symbols:false, dualLayout:true});
    assert.match(password, /^[A-Za-z]{24}$/);
    assert.match(password, /[a-z]/);
    assert.match(password, /[A-Z]/);
    assert.doesNotMatch(password, /[aAmMqQwWzZ]/);
  }
});

test("repeated generations produce fresh passwords", () => {
  const passwords = new Set(Array.from({length:100}, () => generatePassword()));
  assert.equal(passwords.size, 100);
});

test("unsupported lengths and malformed options are rejected", () => {
  for (const length of [0, 7, 129, -1, 12.5, NaN, Infinity, "20"]) {
    assert.throws(() => generatePassword(length), RangeError);
  }
  assert.throws(() => generatePassword(20, {symbols:"true"}), TypeError);
  assert.throws(() => generatePassword(20, {dualLayout:"true"}), TypeError);
});
