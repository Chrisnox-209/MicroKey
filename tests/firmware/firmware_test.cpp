#include <cassert>
#include <iostream>
#include "../../firmware/promicro_key/promicro_key.ino"

void reboot() {
  testTime = 0;
  pending = true;
  usbReady = false;
  connectedAt = 0;
  lineLength = 0;
  lineOverflow = false;
  Serial.connected = false;
  Serial.input.clear();
  Serial.output.clear();
  Keyboard.output.clear();
  setup();
  loop();
}

void send(const std::string &text) {
  Serial.connected = true;
  Serial.output.clear();
  for (char value : text + "\n") Serial.input.push_back(value);
  loop();
}

int main() {
  static_assert(sizeof(Settings) == 144, "EEPROM format changed");
  static_assert(sizeof(LegacySettings) == 142, "Legacy EEPROM format changed");
  reboot();
  testTime = 40000; loop();
  assert(!configured && Keyboard.output.empty());

  send("PMK1 SET fr 1000 10 0 204162312120"); // " Ab1! "
  assert(configured && settings.length == 6 && settings.french);
  assert(settings.password[0] == ' ' && settings.password[5] == ' ');
  assert(Serial.output.find("204162312120") == std::string::npos);
  assert(Serial.output.find(" Ab1! ") == std::string::npos);
  Serial.connected = false; testTime = 40000; loop();
  assert(Keyboard.output.empty()); // Save does not type into the active window.

  reboot();
  testTime = 999; loop(); assert(Keyboard.output.empty());
  testTime = 1000; loop();
  assert(std::string(Keyboard.output.begin(), Keyboard.output.end()) == " Ab1! ");
  assert(Keyboard.layout == KeyboardLayout_fr_FR);
  testTime = 90000; loop(); assert(Keyboard.output.size() == 6); // Only once.

  reboot();
  Serial.connected = true;
  loop(); // OS/modem probes may open the port without using our protocol.
  for (char value : std::string("AT\r\n")) Serial.input.push_back(value);
  loop();
  Serial.connected = false;
  testTime = 1000; loop();
  assert(Keyboard.output.size() == 6); // A serial probe must not cancel typing.

  reboot();
  send("PMK1 INFO");
  Serial.connected = false; testTime = 40000; loop();
  assert(Keyboard.output.empty()); // A configuration connection disarms HID.

  const Settings saved = settings;
  send("PMK1 SET fr 1000 10 0 0a");
  assert(Serial.output.find("invalid_command") != std::string::npos);
  assert(std::memcmp(&settings, &saved, sizeof(saved)) == 0);
  send("PMK1 SET fr 0 10 0 41");
  assert(std::memcmp(&settings, &saved, sizeof(saved)) == 0);
  send("PMK1 " + std::string(400, 'x'));
  assert(Serial.output.find("invalid_command") != std::string::npos);
  send("PMK1 INFO");
  assert(Serial.output.find("\"protocol\":2") != std::string::npos);

  std::string maximum;
  for (int i = 0; i < 128; ++i) maximum += "41";
  send("PMK1 SET us 1000 10 1 " + maximum);
  assert(configured && settings.length == 128 && !settings.french);
  reboot(); testTime = 1000; loop();
  assert(Keyboard.layout == KeyboardLayout_en_US);
  assert(Keyboard.output.size() == 129 && Keyboard.output.back() == KEY_RETURN);

  send("PMK1 SET2 fr 1000 10 0 button 4 204162312120");
  reboot(); testTime = 40000; loop();
  assert(Keyboard.output.empty()); // Button mode never types on boot.
  pinValues[4] = LOW; loop();
  testTime += 34; loop(); assert(Keyboard.output.empty());
  testTime += 1; loop(); assert(Keyboard.output.size() == 6);
  testTime += 5000; loop(); assert(Keyboard.output.size() == 6); // Holding does not repeat.
  pinValues[4] = HIGH; loop(); testTime += 35; loop();
  pinValues[4] = LOW; loop(); testTime += 35; loop();
  assert(Keyboard.output.size() == 12); // Release and press re-arms.

  reboot(); testTime = 40000; loop();
  assert(Keyboard.output.empty()); // A button held at boot cannot type.
  pinValues[4] = HIGH; loop(); testTime += 35; loop();
  send("PMK1 INFO");
  pinValues[4] = LOW; loop(); testTime += 35; loop();
  assert(Keyboard.output.empty()); // Configuration also inhibits the button.
  pinValues[4] = HIGH;

  send("PMK1 PARAMS us 1000 10 0 both 18");
  assert(settings.triggerMode == MODE_BOTH && settings.triggerPin == 18 && settings.length == 6);
  assert(std::string(settings.password, settings.length) == " Ab1! ");
  reboot(); testTime = 1000; loop(); assert(Keyboard.output.size() == 6);
  pinValues[18] = LOW; loop(); testTime += 35; loop(); assert(Keyboard.output.size() == 12);
  pinValues[18] = HIGH;
  const Settings beforeBadPin = settings;
  send("PMK1 SET2 us 1000 10 0 button 13 41");
  assert(Serial.output.find("invalid_command") != std::string::npos);
  assert(std::memcmp(&beforeBadPin, &settings, sizeof(settings)) == 0);

  // A firmware upgrade migrates an existing password without exposing it.
  LegacySettings legacy = {};
  legacy.magic = MAGIC; legacy.version = 1; legacy.length = 6;
  legacy.french = 1; legacy.delayMs = 1000; legacy.intervalMs = 10;
  std::memcpy(legacy.password, "old!42", 6);
  legacy.crc = checksumBytes(&legacy, offsetof(LegacySettings, crc));
  std::memcpy(EEPROM.memory, &legacy, sizeof(legacy));
  reboot();
  assert(configured && settings.version == 2 && settings.triggerMode == MODE_USB && settings.triggerPin == 4);
  assert(std::string(settings.password, settings.length) == "old!42");
  testTime = 1000; loop(); assert(Keyboard.output.size() == 6);

  EEPROM.memory[offsetof(Settings, password)] ^= 1; // Corruption fails closed.
  reboot(); testTime = 40000; loop();
  assert(!configured && Keyboard.output.empty());

  send("PMK1 SET fr 1000 10 0 414243");
  assert(configured);
  send("PMK1 CLEAR");
  assert(!configured);
  for (unsigned int i = 0; i < sizeof(Settings); ++i) assert(EEPROM.memory[i] == 0);
  reboot(); testTime = 40000; loop();
  assert(!configured && Keyboard.output.empty());
  std::cout << "Firmware scenarios passed: boot, button, debounce, held button, both modes, parameter updates, legacy migration, CRC, erase.\n";
}
