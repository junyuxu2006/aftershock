#include <Arduino.h>
#include <Wire.h>
#include <Arduino_RouterBridge.h>

constexpr uint8_t MPU1_ADDR = 0x68; // AD0 -> GND
constexpr uint8_t MPU2_ADDR = 0x69; // AD0 -> 3.3V
constexpr unsigned long SAMPLE_INTERVAL_MS = 20; // 50 Hz

void writeMPURegister(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

bool initMPU(uint8_t addr) {
  Wire.beginTransmission(addr);
  if (Wire.endTransmission() != 0) {
    return false; // Sensor not responding at this address
  }
  writeMPURegister(addr, 0x6B, 0x00); // Wake up MPU6050
  writeMPURegister(addr, 0x1A, 0x03); // Low-pass filter
  writeMPURegister(addr, 0x19, 0x13); // Sample rate divider: 50 Hz
  writeMPURegister(addr, 0x1C, 0x00); // Accel range: +/- 2g
  return true;
}

bool readMPU(uint8_t addr, float &ax, float &ay, float &az) {
  Wire.beginTransmission(addr);
  Wire.write(0x3B); // Accel Xout_H
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  Wire.requestFrom(addr, (uint8_t)6, (uint8_t)true);
  if (Wire.available() == 6) {
    int16_t rawX = (Wire.read() << 8) | Wire.read();
    int16_t rawY = (Wire.read() << 8) | Wire.read();
    int16_t rawZ = (Wire.read() << 8) | Wire.read();

    constexpr float scale = 9.80665f / 16384.0f;
    ax = rawX * scale;
    ay = rawY * scale;
    az = rawZ * scale;
    return true;
  }
  return false;
}

// Alert trigger called by Linux when an aftershock is confirmed
bool trigger_alert(bool active) {
  digitalWrite(LED_BUILTIN, active ? HIGH : LOW);
  return active;
}

void setup() {
  Bridge.begin();
  Wire.begin();
  Wire.setClock(400000); // 400 kHz Fast I2C to read both sensors quickly
  Monitor.begin(115200);

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Bridge.provide_safe("trigger_alert", trigger_alert);

  while (!initMPU(MPU1_ADDR)) {
    Monitor.println("MPU1 (0x68) not detected. Retrying in 1s...");
    delay(1000);
  }
  Monitor.println("MPU1 (0x68) initialized.");

  while (!initMPU(MPU2_ADDR)) {
    Monitor.println("MPU2 (0x69) not detected. Check AD0 -> 3.3V. Retrying in 1s...");
    delay(1000);
  }
  Monitor.println("MPU2 (0x69) initialized.");
}

void loop() {
  static unsigned long lastSample = 0;
  unsigned long now = millis();

  if (now - lastSample >= SAMPLE_INTERVAL_MS) {
    lastSample = now;

    float ax1 = 0, ay1 = 0, az1 = 0;
    float ax2 = 0, ay2 = 0, az2 = 0;

    bool ok1 = readMPU(MPU1_ADDR, ax1, ay1, az1);
    bool ok2 = readMPU(MPU2_ADDR, ax2, ay2, az2);

    if (ok1 && ok2) {
      // Send all 6 values in a single synchronized frame
      Bridge.notify("accel_sample", ax1, ay1, az1, ax2, ay2, az2);
    }
  }
}