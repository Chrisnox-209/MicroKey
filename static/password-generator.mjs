// Normal mode requires the firmware layout to match the target computer.
const GROUPS = ["abcdefghjkmnpqrstuvwxyz", "ABCDEFGHJKLMNPQRSTUVWXYZ", "23456789"];
const SYMBOLS = "!@#$%&*+-=?";
// Same USB HID key AND modifiers in KeyboardLayout_fr_FR / KeyboardLayout_en_US.
// Digits need Shift only in French; A/Q/W/Z/M move. Only + and = are shared symbols.
const DUAL_LAYOUT_GROUPS = GROUPS.slice(0, 2).map((group) => group.replace(/[amqwz]/gi, ""));
const DUAL_LAYOUT_SYMBOLS = "+=";

function randomIndex(maximum) {
  const source = globalThis.crypto;
  if (typeof source?.getRandomValues !== "function") {
    throw new Error("Génération sécurisée indisponible. Ouvrez l’application sur http://127.0.0.1:5000.");
  }
  const sample = new Uint32Array(1);
  const limit = 2 ** 32 - (2 ** 32 % maximum);
  do { source.getRandomValues(sample); } while (sample[0] >= limit);
  return sample[0] % maximum;
}

export function generatePassword(length = 20, {symbols = true, dualLayout = false} = {}) {
  if (!Number.isInteger(length) || length < 8 || length > 128) {
    throw new RangeError("Choisissez une longueur comprise entre 8 et 128 caractères.");
  }
  if (typeof symbols !== "boolean") throw new TypeError("Option de symboles invalide.");
  if (typeof dualLayout !== "boolean") throw new TypeError("Option de compatibilité invalide.");
  const baseGroups = dualLayout ? DUAL_LAYOUT_GROUPS : GROUPS;
  const symbolGroup = dualLayout ? DUAL_LAYOUT_SYMBOLS : SYMBOLS;
  const groups = symbols ? [...baseGroups, symbolGroup] : baseGroups;
  const alphabet = groups.join("");
  const characters = groups.map((group) => group[randomIndex(group.length)]);
  while (characters.length < length) characters.push(alphabet[randomIndex(alphabet.length)]);
  // Shuffle required character groups into random positions.
  for (let index = characters.length - 1; index > 0; index--) {
    const other = randomIndex(index + 1);
    [characters[index], characters[other]] = [characters[other], characters[index]];
  }
  return characters.join("");
}
