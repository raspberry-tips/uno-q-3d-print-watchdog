#!/bin/sh
# Laedt alle Bilder aus ~/dataset/no-anomaly als Label "no anomaly" zu Edge
# Impulse hoch (Ingestion-API, 20er-Batches, Duplikate werden uebersprungen).
# Vorher den API-Key des eigenen Projekts eintragen (Studio -> Dashboard -> Keys).
EI_API_KEY="ei_DEIN_API_KEY_HIER"

cd /home/arduino/dataset/no-anomaly || exit 1
ok=0; args=""; n=0
for f in *.jpg; do
  args="$args -F data=@$f"; n=$((n+1))
  if [ $n -eq 20 ]; then
    r=$(curl -s -X POST https://ingestion.edgeimpulse.com/api/training/files -H "x-api-key: $EI_API_KEY" -H "x-label: no anomaly" -H "x-disallow-duplicates: 1" $args)
    ok=$((ok + $(echo "$r" | grep -o '"success":true' | wc -l))); n=0; args=""
  fi
done
if [ -n "$args" ]; then
  r=$(curl -s -X POST https://ingestion.edgeimpulse.com/api/training/files -H "x-api-key: $EI_API_KEY" -H "x-label: no anomaly" -H "x-disallow-duplicates: 1" $args)
  ok=$((ok + $(echo "$r" | grep -o '"success":true' | wc -l)))
fi
echo "OK-Antworten: $ok"
