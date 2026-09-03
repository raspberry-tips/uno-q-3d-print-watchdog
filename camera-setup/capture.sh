#!/bin/sh
# Trainingsbild-Sammler Spaghetti-Waechter (Label: no anomaly)
mkdir -p /home/arduino/dataset/no-anomaly
while true; do
  cp /dev/shm/live.jpg "/home/arduino/dataset/no-anomaly/$(date +%Y%m%d_%H%M%S).jpg" 2>/dev/null
  sleep 10
done
