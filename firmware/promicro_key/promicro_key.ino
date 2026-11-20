/* Pro Micro Key — ATmega32U4, firmware sans secret dans le binaire.
 * USB HID : branchement, bouton vers GND, ou les deux. Anti-rebond intégré.
 * Configuration : EEPROM avec CRC, protocole série PMK1, aucune lecture du secret.
 */
#include <Keyboard.h>
#include <EEPROM.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

const uint32_t MAGIC = 0x314B4D50UL;
const uint8_t VERSION = 2;
const uint8_t MAX_PASSWORD = 128;
const uint8_t MODE_USB = 0, MODE_BUTTON = 1, MODE_BOTH = 2;
const unsigned long DEBOUNCE_MS = 35;

struct __attribute__((packed)) LegacySettings {
  uint32_t magic;
  uint8_t version;
  uint8_t length;
  uint8_t french;
  uint8_t pressEnter;
  uint16_t delayMs;
  uint16_t intervalMs;
  char password[MAX_PASSWORD];
  uint16_t crc;
};

struct __attribute__((packed)) Settings {
  uint32_t magic;
  uint8_t version, length, french, pressEnter;
  uint16_t delayMs, intervalMs;
  char password[MAX_PASSWORD];
  uint8_t triggerMode, triggerPin;
  uint16_t crc;
};

Settings settings;
char line[320];
uint16_t lineLength = 0;
bool lineOverflow = false;
bool configured = false;
bool pending = true;
bool usbReady = false;
unsigned long connectedAt = 0;
bool configurationSession = false;
uint8_t lastButtonRead = HIGH, stableButtonState = HIGH;
bool buttonArmed = false;
unsigned long buttonChangedAt = 0;

uint16_t checksumBytes(const void *value, size_t length) {
  const uint8_t *data = reinterpret_cast<const uint8_t *>(value);
  uint16_t crc = 0xFFFF;
  for (uint16_t i = offsetof(Settings, version); i < length; i++) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; bit++) crc = (crc >> 1) ^ ((crc & 1) ? 0xA001 : 0);
  }
  return crc;
}

uint16_t checksum(const Settings &value) { return checksumBytes(&value, offsetof(Settings, crc)); }

bool validPin(uint8_t pin) {
  return pin <= 10 || (pin >= 14 && pin <= 16) || (pin >= 18 && pin <= 21);
}

bool valid(const Settings &value) {
  if (value.magic != MAGIC || value.version != VERSION || value.length == 0 || value.length > MAX_PASSWORD ||
      value.french > 1 || value.pressEnter > 1 || value.delayMs < 1000 || value.delayMs > 30000 ||
      value.intervalMs < 10 || value.intervalMs > 200 || value.triggerMode > MODE_BOTH ||
      !validPin(value.triggerPin) || value.crc != checksum(value)) return false;
  for (uint8_t i = 0; i < value.length; i++) if (value.password[i] < 32 || value.password[i] > 126) return false;
  return true;
}

void info() {
  Serial.print(F("PMK1 {\"protocol\":2,\"firmware\":\"1.1.0\",\"configured\":"));
  Serial.print(configured ? F("true") : F("false"));
  Serial.print(F(",\"length\":")); Serial.print(configured ? settings.length : 0);
  Serial.print(F(",\"layout\":\"")); Serial.print(settings.french ? F("fr") : F("us"));
  Serial.print(F("\",\"delay_ms\":")); Serial.print(settings.delayMs);
  Serial.print(F(",\"interval_ms\":")); Serial.print(settings.intervalMs);
  Serial.print(F(",\"press_enter\":")); Serial.print(settings.pressEnter ? F("true") : F("false"));
  Serial.print(F(",\"trigger_mode\":\""));
  Serial.print(settings.triggerMode == MODE_BUTTON ? F("button") : settings.triggerMode == MODE_BOTH ? F("both") : F("usb"));
  Serial.print(F("\",\"trigger_pin\":")); Serial.print(settings.triggerPin);
  Serial.print(F(",\"clock_hz\":")); Serial.print(F_CPU);
  Serial.println(F("}"));
}

void error() { Serial.println(F("PMK1 {\"protocol\":2,\"error\":\"invalid_command\"}")); }

int hexDigit(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  return -1;
}

bool number(const char *text, unsigned long minimum, unsigned long maximum, uint16_t &result) {
  if (!text || !*text) return false;
  for (const char *p = text; *p; p++) if (*p < '0' || *p > '9') return false;
  char *end;
  unsigned long value = strtoul(text, &end, 10);
  if (*end || value < minimum || value > maximum) return false;
  result = value;
  return true;
}

void persist(const Settings &next) {
  // Invalidate before writing; power loss cannot leave a half-valid secret.
  EEPROM.update(0, 0);
  const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&next);
  for (uint16_t i = sizeof(next.magic); i < sizeof(next); i++) EEPROM.update(i, bytes[i]);
  for (uint8_t i = 1; i < sizeof(next.magic); i++) EEPROM.update(i, bytes[i]);
  EEPROM.update(0, bytes[0]);
  EEPROM.get(0, settings);
  configured = valid(settings);
}

void save(char *arguments, bool extended, bool keepPassword) {
  if (keepPassword && !configured) { error(); return; }
  Settings next = keepPassword ? settings : Settings{};
  next.triggerMode = MODE_USB;
  next.triggerPin = 4;
  char *context;
  char *layout = strtok_r(arguments, " ", &context);
  if (!layout || (strcmp(layout, "fr") && strcmp(layout, "us"))) { error(); return; }
  next.french = !strcmp(layout, "fr");
  uint16_t delayMs, intervalMs;
  if (!number(strtok_r(NULL, " ", &context), 1000, 30000, delayMs) ||
      !number(strtok_r(NULL, " ", &context), 10, 200, intervalMs)) { error(); return; }
  next.delayMs = delayMs;
  next.intervalMs = intervalMs;
  char *enter = strtok_r(NULL, " ", &context);
  if (!enter || (strcmp(enter, "0") && strcmp(enter, "1"))) { error(); return; }
  next.pressEnter = !strcmp(enter, "1");
  if (extended) {
    char *mode = strtok_r(NULL, " ", &context);
    if (!mode) { error(); return; }
    if (!strcmp(mode, "usb")) next.triggerMode = MODE_USB;
    else if (!strcmp(mode, "button")) next.triggerMode = MODE_BUTTON;
    else if (!strcmp(mode, "both")) next.triggerMode = MODE_BOTH;
    else { error(); return; }
    uint16_t pin;
    if (!number(strtok_r(NULL, " ", &context), 0, 21, pin) || !validPin(pin)) { error(); return; }
    next.triggerPin = pin;
  }
  if (keepPassword) {
    if (strtok_r(NULL, " ", &context)) { error(); memset(&next, 0, sizeof(next)); return; }
  } else {
  char *hex = strtok_r(NULL, " ", &context);
  if (!hex || strtok_r(NULL, " ", &context)) { error(); return; }
  size_t length = strlen(hex);
  if (length < 2 || length > MAX_PASSWORD * 2 || length % 2) { error(); return; }
  next.length = length / 2;
  for (uint8_t i = 0; i < next.length; i++) {
    int high = hexDigit(hex[i * 2]), low = hexDigit(hex[i * 2 + 1]);
    if (high < 0 || low < 0) { error(); memset(&next, 0, sizeof(next)); return; }
    char value = high * 16 + low;
    if (value < 32 || value > 126) { error(); memset(&next, 0, sizeof(next)); return; }
    next.password[i] = value;
  }
  }
  next.magic = MAGIC;
  next.version = VERSION;
  next.crc = checksum(next);
  persist(next);
  memset(&next, 0, sizeof(next));
  info();
}

void command() {
  if (strncmp(line, "PMK1 ", 5)) return;
  pending = false;
  configurationSession = true;
  if (!strcmp(line + 5, "INFO")) info();
  else if (!strncmp(line + 5, "PARAMS ", 7)) save(line + 12, true, true);
  else if (!strncmp(line + 5, "SET2 ", 5)) save(line + 10, true, false);
  else if (!strncmp(line + 5, "SET ", 4)) save(line + 9, false, false);
  else if (!strcmp(line + 5, "CLEAR")) {
    for (uint16_t i = 0; i < sizeof(settings); i++) EEPROM.update(i, 0);
    memset(&settings, 0, sizeof(settings));
    configured = false;
    info();
  } else error();
}

void setup() {
  Serial.begin(115200);
  EEPROM.get(0, settings);
  configured = valid(settings);
  if (!configured) {
    LegacySettings legacy;
    EEPROM.get(0, legacy);
    if (legacy.magic == MAGIC && legacy.version == 1 &&
        legacy.crc == checksumBytes(&legacy, offsetof(LegacySettings, crc))) {
      Settings migrated = {};
      memcpy(&migrated, &legacy, offsetof(LegacySettings, crc));
      migrated.version = VERSION;
      migrated.triggerMode = MODE_USB;
      migrated.triggerPin = 4;
      migrated.crc = checksum(migrated);
      if (valid(migrated)) persist(migrated);
      memset(&migrated, 0, sizeof(migrated));
    }
    memset(&legacy, 0, sizeof(legacy));
  }
  if (!configured) {
    memset(&settings, 0, sizeof(settings));
    settings.french = 1;
    settings.delayMs = 5000;
    settings.intervalMs = 30;
    settings.triggerPin = 4;
  }
  configurationSession = false;
  pending = configured && settings.triggerMode != MODE_BUTTON;
  if (configured && settings.triggerMode != MODE_USB) {
    pinMode(settings.triggerPin, INPUT_PULLUP);
    lastButtonRead = stableButtonState = digitalRead(settings.triggerPin);
    buttonArmed = stableButtonState == HIGH;
    buttonChangedAt = millis();
  }
}

void typePassword() {
  Keyboard.begin(settings.french ? KeyboardLayout_fr_FR : KeyboardLayout_en_US);
  for (uint8_t i = 0; i < settings.length; i++) {
    Keyboard.write(settings.password[i]);
    delay(settings.intervalMs);
  }
  if (settings.pressEnter) Keyboard.write(KEY_RETURN);
  Keyboard.releaseAll();
  Keyboard.end();
}

void pollButton() {
  uint8_t reading = digitalRead(settings.triggerPin);
  if (reading != lastButtonRead) { lastButtonRead = reading; buttonChangedAt = millis(); }
  if (millis() - buttonChangedAt < DEBOUNCE_MS || reading == stableButtonState) return;
  stableButtonState = reading;
  if (reading == HIGH) { buttonArmed = true; return; }
  if (buttonArmed) {
    buttonArmed = false;
    if (usbReady && !configurationSession) typePassword();
  }
}

void loop() {
  // Only a PMK1 command disarms HID. OS serial probes must not cancel typing.
  while (Serial.available()) {
    char value = Serial.read();
    if (value == '\n' || value == '\r') {
      if (lineOverflow) error();
      else if (lineLength) { line[lineLength] = 0; command(); }
      memset(line, 0, sizeof(line));
      lineLength = 0;
      lineOverflow = false;
    } else {
      if (lineLength < sizeof(line) - 1) line[lineLength++] = value;
      else lineOverflow = true;
    }
  }
  if (!usbReady && USBDevice.configured()) { usbReady = true; connectedAt = millis(); }
  if (pending && configured && usbReady && !configurationSession && millis() - connectedAt >= settings.delayMs) {
    pending = false;
    typePassword();
  }
  if (configured && settings.triggerMode != MODE_USB) pollButton();
}
