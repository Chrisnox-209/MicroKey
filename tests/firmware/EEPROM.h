#pragma once
#include <algorithm>
#include <cstdint>
#include <cstring>
struct MockEEPROM {
  uint8_t memory[1024];
  MockEEPROM() { std::fill(memory, memory + sizeof(memory), 0xFF); }
  template<typename T> void get(unsigned int address, T &value) { std::memcpy(&value, memory + address, sizeof(value)); }
  void update(unsigned int address, uint8_t value) { memory[address] = value; }
};
inline MockEEPROM EEPROM;
