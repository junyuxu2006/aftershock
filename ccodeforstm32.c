#include <Arduino_RouterBridge.h>

// Linux side calls: Bridge.call("set_led", true)
bool set_led(bool on) {
  digitalWrite(LED_BUILTIN, on ? HIGH : LOW);
  Monitor.println(on ? "ACK: LED is ON" : "ACK: LED is OFF");
  return on;                      // sent back to the caller as the result
}

// Linux side calls: Bridge.call("echo", "hello")  ->  "STM32 reply: hello"
String echo(String text) {
  return String("STM32 reply: ") + text;
}

void setup() {
  Bridge.begin();                 // start the link to the Linux side
  Monitor.begin(115200);          // replaces Serial on the UNO Q

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Register functions the Linux side is allowed to call.
  // provide_safe runs them on the main loop thread, so they can touch pins safely.
  Bridge.provide_safe("set_led", set_led);
  Bridge.provide_safe("echo", echo);
}

void loop() {
  // Heartbeat every 5 s. notify() is fire-and-forget: no reply expected.
  static unsigned long lastBeat = 0;
  if (millis() - lastBeat > 5000) {
    lastBeat = millis();
    Bridge.notify("heartbeat", lastBeat);
    Monitor.println("PING from STM32");
  }
}
