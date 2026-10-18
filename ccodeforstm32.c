#include <Arduino.h>
#include <Wire.h>
#include <Arduino_RouterBridge.h>

constexpr uint8_t MPU1_ADDR = 0x68;
constexpr uint8_t MPU2_ADDR = 0x69;
constexpr unsigned long SAMPLE_INTERVAL_MS = 20;

void writeMPURegister(uint8_t address, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

bool initMPU(uint8_t address) {
  Wire.beginTransmission(address);
  if (Wire.endTransmission() != 0) {
    return false;
  }

  writeMPURegister(address, 0x6B, 0x00);
  writeMPURegister(address, 0x1A, 0x03);
  writeMPURegister(address, 0x19, 0x13);
  writeMPURegister(address, 0x1C, 0x00);
  return true;
}

bool readMPU(uint8_t address, float &ax, float &ay, float &az) {
  Wire.beginTransmission(address);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  Wire.requestFrom(address, static_cast<uint8_t>(6), static_cast<uint8_t>(true));
  if (Wire.available() != 6) {
    return false;
  }

  const int16_t rawX = (Wire.read() << 8) | Wire.read();
  const int16_t rawY = (Wire.read() << 8) | Wire.read();
  const int16_t rawZ = (Wire.read() << 8) | Wire.read();
  constexpr float scale = 9.80665f / 16384.0f;
  ax = rawX * scale;
  ay = rawY * scale;
  az = rawZ * scale;
  return true;
}

bool set_magnitude_led(String magnitude) {
  uint8_t red = 0;
  uint8_t green = 0;
  uint8_t blue = 0;

  if (magnitude == "LOW") {
    red = 255;
    green = 255;
  } else if (magnitude == "MEDIUM") {
    red = 255;
    green = 128;
  } else if (magnitude == "HIGH") {
    red = 255;
  } else {
    green = 255;
  }

  rgbLedWrite(RGB_BUILTIN, red, green, blue);
  return true;
}

bool trigger_alert(bool active) {
  set_magnitude_led(active ? "HIGH" : "BASELINE");
  return active;
}

void setup() {
  Bridge.begin();
  Wire.begin();
  Wire.setClock(400000);
  Monitor.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  rgbLedWrite(RGB_BUILTIN, 0, 255, 0);

  Bridge.provide_safe("trigger_alert", trigger_alert);
  Bridge.provide_safe("set_magnitude_led", set_magnitude_led);

  while (!initMPU(MPU1_ADDR)) {
    Monitor.println("MPU1 (0x68) not detected. Retrying in 1s...");
    delay(1000);
  }
  while (!initMPU(MPU2_ADDR)) {
    Monitor.println("MPU2 (0x69) not detected. Retrying in 1s...");
    delay(1000);
  }
}

void loop() {
  static unsigned long lastSample = 0;
  const unsigned long now = millis();
  if (now - lastSample < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSample = now;

  float ax1 = 0;
  float ay1 = 0;
  float az1 = 0;
  float ax2 = 0;
  float ay2 = 0;
  float az2 = 0;
  if (readMPU(MPU1_ADDR, ax1, ay1, az1) &&
      readMPU(MPU2_ADDR, ax2, ay2, az2)) {
    Bridge.notify("accel_sample", ax1, ay1, az1, ax2, ay2, az2);
  }
}
