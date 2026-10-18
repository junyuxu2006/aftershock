#include <Arduino.h>
#include <RPC.h>

void setup() {
  // Initialize standard hardware serial for debugging (optional)
  Serial.begin(115200);

  // Initialize the inter-processor RPMsg bridge to Linux
  RPC.begin();

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
}

void loop() {
  // Check for incoming commands or data from the Linux router/bridge
  if (RPC.available()) {
    String cmd = RPC.readStringUntil('\n');
    cmd.trim();

    if (cmd == "LED_ON") {
      digitalWrite(LED_BUILTIN, HIGH);
      RPC.println("ACK: LED is ON");
    } else if (cmd == "LED_OFF") {
      digitalWrite(LED_BUILTIN, LOW);
      RPC.println("ACK: LED is OFF");
    } else if (cmd.startsWith("ECHO:")) {
      RPC.print("STM32 reply: ");
      RPC.println(cmd.substring(5));
    } else {
      RPC.print("UNKNOWN_COMMAND: ");
      RPC.println(cmd);
    }
  }

  // Periodic heartbeat sent to Linux every 5 seconds
  static unsigned long lastBeat = 0;
  if (millis() - lastBeat > 5000) {
    lastBeat = millis();
    RPC.println("PING from STM32");
  }
}