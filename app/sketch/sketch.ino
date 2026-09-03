// sketch.ino — Spaghetti-Waechter: LED-Matrix-Alarm auf dem Echtzeit-Chip
// raspberry.tips — Skeleton v0.1 (21.08.2026)
//
// Der M33 (Zephyr) macht hier bewusst wenig — aber das Richtige: Der Alarm
// blinkt auch dann zuverlaessig weiter, wenn die Linux-Seite unter Last
// steht. Python meldet per Bridge.call("set_alarm", true/false).
// Ruhezustand: dezenter "Herzschlag"-Punkt = Waechter lebt.

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

// Ausrufezeichen, 3 Spalten breit, mittig — Helligkeit 0..7
void draw_alert(uint8_t level) {
    for (int i = 0; i < ROWS * COLS; i++) frame[i] = 0;
    for (int r = 0; r < 5; r++) {                 // Balken
        frame[r * COLS + 5] = level;
        frame[r * COLS + 6] = level;
        frame[r * COLS + 7] = level;
    }
    frame[7 * COLS + 5] = level;                  // Punkt
    frame[7 * COLS + 6] = level;
    frame[7 * COLS + 7] = level;
    matrix.draw(frame);
}

void draw_heartbeat(uint8_t level) {
    for (int i = 0; i < ROWS * COLS; i++) frame[i] = 0;
    frame[7 * COLS + 12] = level;                 // Ecke unten rechts
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
    Monitor.println("Spaghetti-Waechter MCU bereit.");
}

void loop() {
    unsigned long now = millis();

    if (alarm_on) {
        if (now - last_toggle >= 400) {           // 2,5-Hz-Blinken
            last_toggle = now;
            blink_phase = !blink_phase;
            draw_alert(blink_phase ? 7 : 1);
        }
    } else {
        // Herzschlag: alle 3 s kurz aufpulsen
        if (now - last_beat >= 3000) {
            last_beat = now;
            draw_heartbeat(3);
        } else if (now - last_beat >= 200) {
            draw_heartbeat(0);
        }
    }
    delay(20);
}
