#!/bin/bash
# Espera a que publicar.html genere los dos archivos cifrados y cierra la publicación.
# Se detiene solo tras publicar, o a las 2 horas si no aparecen.
cd "$(dirname "$0")" || exit 1

A="$HOME/Downloads/datos-senescyt.js"
B="$HOME/Downloads/payload-campos.txt"
FIN=$((SECONDS + 7200))

echo "[$(date +%H:%M:%S)] esperando $A y $B ..."

while [ $SECONDS -lt $FIN ]; do
  if [ -s "$A" ] && [ -s "$B" ]; then
    # esperar a que terminen de escribirse (tamaño estable en dos lecturas)
    s1=$(( $(wc -c < "$A") + $(wc -c < "$B") ))
    sleep 3
    s2=$(( $(wc -c < "$A") + $(wc -c < "$B") ))
    if [ "$s1" = "$s2" ]; then
      echo "[$(date +%H:%M:%S)] archivos detectados ($s2 bytes). Publicando..."
      python3 finalizar_publicacion.py --push
      code=$?
      if [ $code -eq 0 ]; then
        echo "[$(date +%H:%M:%S)] ✓ PUBLICADO EN GITHUB"
      else
        echo "[$(date +%H:%M:%S)] ✗ falló la publicación (código $code)"
      fi
      exit $code
    fi
  fi
  sleep 10
done

echo "[$(date +%H:%M:%S)] tiempo agotado: los archivos no aparecieron."
exit 2
