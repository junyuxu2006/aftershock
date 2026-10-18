#include <Arduino.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Arduino_RouterBridge.h>

constexpr uint8_t MPU1_ADDR = 0x68;
constexpr uint8_t MPU2_ADDR = 0x69;
constexpr unsigned long SAMPLE_INTERVAL_MS = 20;
constexpr uint8_t RGB_RED_PIN = 11;
constexpr uint8_t RGB_GREEN_PIN = 10;
constexpr uint8_t RGB_BLUE_PIN = 9;
constexpr uint8_t BUZZER_PIN = 7;
constexpr unsigned long BUZZER_HOLD_MS = 10000;
constexpr unsigned long BUZZER_BEEP_ON_MS = 150;
constexpr unsigned long BUZZER_BEEP_OFF_MS = 500;
constexpr uint8_t LCD_PRIMARY_ADDRESS = 0x27;
constexpr uint8_t LCD_ALTERNATE_ADDRESS = 0x3F;
constexpr uint8_t LCD_COLUMNS = 16;
constexpr uint8_t LCD_ROWS = 2;
// Set true only when the LED common leg is connected to 3.3V.
constexpr bool RGB_COMMON_ANODE = false;

LiquidCrystal_I2C lcdPrimary(LCD_PRIMARY_ADDRESS, LCD_COLUMNS, LCD_ROWS);
LiquidCrystal_I2C lcdAlternate(LCD_ALTERNATE_ADDRESS, LCD_COLUMNS, LCD_ROWS);
LiquidCrystal_I2C *lcd = nullptr;
unsigned long buzzerActiveUntil = 0;
unsigned long buzzerLastToggle = 0;
bool buzzerOn = false;

bool initLcd() {
  Wire.beginTransmission(LCD_PRIMARY_ADDRESS);
  if (Wire.endTransmission() == 0) {
    lcd = &lcdPrimary;
  } else {
    Wire.beginTransmission(LCD_ALTERNATE_ADDRESS);
    if (Wire.endTransmission() != 0) {
      return false;
    }
    lcd = &lcdAlternate;
  }

  lcd->init();
  lcd->backlight();
  return true;
}

void showMagnitude(const String &magnitude) {
  if (lcd == nullptr) {
    return;
  }

  auto printCentered = [](const String &text) {
    const uint8_t textLength = min(static_cast<uint8_t>(text.length()), LCD_COLUMNS);
    const uint8_t leftPadding = (LCD_COLUMNS - textLength) / 2;
    for (uint8_t index = 0; index < leftPadding; ++index) {
      lcd->print(' ');
    }
    lcd->print(text.substring(0, textLength));
  };

  lcd->clear();
  lcd->setCursor(0, 0);
  printCentered("Magnitude:");
  lcd->setCursor(0, 1);
  printCentered(magnitude);
}

void writeRgb(uint8_t red, uint8_t green, uint8_t blue) {
  if (RGB_COMMON_ANODE) {
    red = 255 - red;
    green = 255 - green;
    blue = 255 - blue;
  }
  analogWrite(RGB_RED_PIN, red);
  analogWrite(RGB_GREEN_PIN, green);
  analogWrite(RGB_BLUE_PIN, blue);
}

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
  static String displayedMagnitude = "";
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

  writeRgb(red, green, blue);
  if (magnitude == "HIGH") {
    buzzerActiveUntil = millis() + BUZZER_HOLD_MS;
    buzzerOn = true;
    buzzerLastToggle = millis();
    digitalWrite(BUZZER_PIN, HIGH);
  } else {
    buzzerActiveUntil = 0;
    buzzerOn = false;
    digitalWrite(BUZZER_PIN, LOW);
  }
  if (magnitude != displayedMagnitude) {
    showMagnitude(magnitude);
    displayedMagnitude = magnitude;
  }
  return true;
}

bool trigger_alert(bool active) {
  return active;
}

void setup() {
  Monitor.begin(115200);
  Bridge.begin();
  Wire.begin();
  Wire.setClock(400000);
  if (initLcd()) {
    lcd->clear();
    lcd->setCursor(0, 0);
    const String detectedText = "I2C LCD detected";
    lcd->setCursor((LCD_COLUMNS - detectedText.length()) / 2, 0);
    lcd->print(detectedText);
    lcd->setCursor(0, 1);
    const String initializingText = "Initializing...";
    lcd->setCursor((LCD_COLUMNS - initializingText.length()) / 2, 1);
    lcd->print(initializingText);
    Monitor.println("I2C LCD detected.");
    delay(1500);
    showMagnitude("BASELINE");
  } else {
    Monitor.println("I2C LCD not detected at 0x27 or 0x3F.");
  }
  pinMode(RGB_RED_PIN, OUTPUT);
  pinMode(RGB_GREEN_PIN, OUTPUT);
  pinMode(RGB_BLUE_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  writeRgb(0, 255, 0);

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
  if (buzzerActiveUntil != 0 &&
      static_cast<long>(now - buzzerActiveUntil) >= 0) {
    buzzerActiveUntil = 0;
    buzzerOn = false;
    digitalWrite(BUZZER_PIN, LOW);
  } else if (buzzerActiveUntil != 0 &&
             now - buzzerLastToggle >=
                 (buzzerOn ? BUZZER_BEEP_ON_MS : BUZZER_BEEP_OFF_MS)) {
    buzzerLastToggle = now;
    buzzerOn = !buzzerOn;
    digitalWrite(BUZZER_PIN, buzzerOn ? HIGH : LOW);
  }
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