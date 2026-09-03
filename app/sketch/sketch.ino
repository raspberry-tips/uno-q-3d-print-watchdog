// sketch.ino - Spaghetti Watchdog: the LED-matrix alarm on the real-time chip
//
// The STM32 deliberately does very little here - but it does the right thing:
// the alarm keeps blinking reliably even when the Linux side is under load or
// has stalled, because a separate chip is driving it. The Python app signals
// through Bridge.call("set_alarm", true/false).
// Idle state: a discreet heartbeat dot means the watchdog is alive.

#include "Arduino_RouterBridge.h"
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

const uint8_t ROWS = 8;
const uint8_t COLS = 13;
uint8_t frame[ROWS * COLS];

volatile bool alarm_on = false;
bool blink_phase = false;
unsigned long last_toggle = 0;
unsigned long last_beat = 0;

// Exclamation mark, 3 columns wide, centred - brightness 0..7
void draw_alert(uint8_t level) {
    for (int i = 0; i < ROWS * COLS; i++) frame[i] = 0;
    for (int r = 0; r < 5; r++) {                 // the bar
        frame[r * COLS + 5] = level;
        frame[r * COLS + 6] = level;
        frame[r * COLS + 7] = level;
    }
    frame[7 * COLS + 5] = level;                  // the dot
    frame[7 * COLS + 6] = level;
    frame[7 * COLS + 7] = level;
    matrix.draw(frame);
}

void draw_heartbeat(uint8_t level) {
    for (int i = 0; i < ROWS * COLS; i++) frame[i] = 0;
    frame[7 * COLS + 12] = level;                 // bottom right corner
    matrix.draw(frame);
}

void set_alarm(bool on) {
    alarm_on = on;
    if (!on) matrix.clear();
}

void setup() {
    Monitor.begin(115200);
    matrix.begin();
    matrix.setGrayscaleBits(3);
    matrix.clear();

    Bridge.begin();
    Bridge.provide("set_alarm", set_alarm);
    Monitor.println("Spaghetti Watchdog MCU ready.");
}

void loop() {
    unsigned long now = millis();

    if (alarm_on) {
        if (now - last_toggle >= 400) {           // blink at 2.5 Hz
            last_toggle = now;
            blink_phase = !blink_phase;
            draw_alert(blink_phase ? 7 : 1);
        }
    } else {
        // heartbeat: a short pulse every 3 s
        if (now - last_beat >= 3000) {
            last_beat = now;
            draw_heartbeat(3);
        } else if (now - last_beat >= 200) {
            draw_heartbeat(0);
        }
    }
    delay(20);
}
