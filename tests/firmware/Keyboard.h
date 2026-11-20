#pragma once
#include <cstdint>
#include <cstring>
#include <deque>
#include <string>
#include <vector>
#define F(value) value
#define KEY_RETURN 0xB0
#define HIGH 1
#define LOW 0
#define INPUT_PULLUP 2
#define F_CPU 16000000UL
inline uint8_t pinValues[24] = {1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1};
inline void pinMode(uint8_t, uint8_t) {}
inline uint8_t digitalRead(uint8_t pin) { return pinValues[pin]; }
inline unsigned long testTime = 0;
inline unsigned long millis() { return testTime; }
inline void delay(unsigned long value) { testTime += value; }
inline const uint8_t KeyboardLayout_fr_FR[] = {1};
inline const uint8_t KeyboardLayout_en_US[] = {2};
struct MockKeyboard {
  std::vector<uint8_t> output;
  const uint8_t *layout = nullptr;
  void begin(const uint8_t *value) { layout = value; }
  void end() {}
  void releaseAll() {}
  void write(uint8_t value) { output.push_back(value); }
};
inline MockKeyboard Keyboard;
struct MockSerial {
  bool connected = false;
  std::deque<char> input;
  std::string output;
  void begin(int) {}
  explicit operator bool() const { return connected; }
  int available() { return input.size(); }
  char read() { char value = input.front(); input.pop_front(); return value; }
  void print(const char *value) { output += value; }
  template<typename T> void print(T value) { output += std::to_string(value); }
  void println(const char *value) { output += value; output += '\n'; }
};
inline MockSerial Serial;
struct MockUSB { bool configured() { return true; } };
inline MockUSB USBDevice;
