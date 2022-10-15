#!/bin/bash

case $1 in
	start)
		screen -dmS radiodelay
		screen -S radiodelay -X stuff "python3 /opt/radio-delay/radio-delay.py --channels 1 --chunk 4096 --sample_rate 44100 --delay 5 --bffsz 180
"
		;;
	stop)
		screen -S radiodelay -X stuff "q

exit
"
		;;
	*)
		echo "Usage: $0 {start|stop}"
		;;
esac
