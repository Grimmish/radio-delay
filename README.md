# radio-delay
A Python app and some supporting tools that buffer an incoming audio stream and play it back on an adjustable delay.

Primary use case is delaying FM radio broadcasts for sports events so they synchronize with the video broadcast. E.g., for cases where the local announcers are preferable to the national play-by-play stream.

Uses a mix of console input and GPIO controls to change behavior.

Original platform is a Raspberry Pi Zero (1st gen) running Raspberry Pi OS, but should work on any Raspberry Pi hardware.

## Helpful tools
The following snippet can be helpful to identify how your audio devices are exposed in PyAudio:
```python
import pyaudio
p = pyaudio.PyAudio()
info = p.get_host_api_info_by_index(0)
numdevices = info.get('deviceCount')
for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            print("Input Device id ", i, " - ", p.get_device_info_by_host_api_device_index(0, i))
```
