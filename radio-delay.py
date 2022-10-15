#!/usr/bin/python

# Radio Delay
# Original version by Steven Young <stevenryoung@gmail.com> 2014-2015 
#
# Extensively rewritten by Ben Adams 2021-2022 to add multiple 
# input/control methods
#

from multiprocessing import Process, Pipe
import os
from pkg_resources import Requirement, resource_filename
import pyaudio
import argparse
import select
import tty
import sys
import termios

import board
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
import time

# Some Global Variables
DELAY_PROMPT = 'Use "[" and "]" to change delay. Press "q" to quit.\n'
OLED_TIMEOUT_SECS = 600
MORE_DELAY_BUTTON = board.D14
LESS_DELAY_BUTTON = board.D4
CHG_INCREMENT_SECS = 0.5

# Parse Arguments
parser = argparse.ArgumentParser()
parser.add_argument('--delay', type=float, help='delay (seconds)', 
                    action='store', default=5.0)
parser.add_argument('--sample_rate', type=int, help='sample rate (hz)',
                    action='store', default=44100)
parser.add_argument('--chunk', type=int, help='chunk size (bytes)',
                    action='store', default=2048)
parser.add_argument('--width', type=int, help='width',
                    action='store', default=2)
parser.add_argument('--channels', type=int, help='number of channels',
                    action='store', default=2)
parser.add_argument('--bffsz', type=int, help='size of ring buffer (seconds)',
                    action='store', default=300)
parser.add_argument('--primelen', type=int, help='number of chunks to prime output',
                    action='store', default=5)
ARGS = parser.parse_args()

def write_terminal(desired_delay):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("Delay (seconds): {}".format(desired_delay))
    print(DELAY_PROMPT)
    
def inputcheck():
    return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

def initialize_stream(audio):
    return audio.open(format=audio.get_format_from_width(ARGS.width),
                    channels=ARGS.channels,
                    rate=ARGS.sample_rate,
                    input=True,
                    input_device_index=0,
                    output=True,
                    output_device_index=0,
                    frames_per_buffer=ARGS.chunk)

def refresh_oled(oled, delaysecs):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    # Status bar
    draw.text(
        (0, 0),
        "Current delay:",
        font=ImageFont.truetype("DejaVuSansMono-Bold.ttf", 12),
        fill=255,
    )
    # Number
    draw.text(
        (10, 16),
        "{:4.1f}s".format(delaysecs),
        font=ImageFont.truetype("DejaVuSansMono-Bold.ttf", 35),
        fill=255,
    )
    oled.image(image)
    oled.show()

#
# GPIO thread:
#   - Read hardware input buttons; display current delay value on OLED
#   - Send values representing requested change to delay
#   - Accept new delay values to display on OLED (or None to quit)
#
def gpio_worker(conn):
    morebutton = digitalio.DigitalInOut(MORE_DELAY_BUTTON)
    morebutton.direction = digitalio.Direction.INPUT
    morebutton.pull = digitalio.Pull.UP

    lessbutton = digitalio.DigitalInOut(LESS_DELAY_BUTTON)
    lessbutton.direction = digitalio.Direction.INPUT
    lessbutton.pull = digitalio.Pull.UP

    i2c = board.I2C()
    oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
    refresh_oled(oled, ARGS.delay)

    lastinput = time.time()
    while True:
        if conn.poll():
            newdelay = conn.recv()
            if newdelay:
                refresh_oled(oled, newdelay)
                lastinput = time.time()
            else:
                oled.fill(0)
                oled.show()
                break

        if (not morebutton.value) and (not lessbutton.value):
            # Both buttons? Quittin' time!
            conn.send(False)
        elif not morebutton.value:
            conn.send(CHG_INCREMENT_SECS)
            lastinput = time.time()
        elif not lessbutton.value:
            conn.send(0 - CHG_INCREMENT_SECS)
            lastinput = time.time()

        if (time.time() - lastinput > OLED_TIMEOUT_SECS):
            oled.fill(0)
            oled.show()

        time.sleep(0.2)


#
# Audio thread:
#   - Handle recording & playback for audio ringbuffer
#   - Accept new delay values (or None as exit command)
#
def audio_worker(conn):
    # Initialize PyAudio
    p = pyaudio.PyAudio()

    # Initialize Stream
    stream = initialize_stream(p)

    # Establish some parameters
    bps = float(ARGS.sample_rate) / float(ARGS.chunk)  # blocks per second
    desireddelay = ARGS.delay  # delay in seconds
    buffersecs = ARGS.bffsz  # size of buffer in seconds

    # Create buffer
    bfflen = int(buffersecs * bps)
    buff = [0 for x in range(bfflen)]

    # Establish initial buffer pointer
    widx = int(desireddelay * bps)  # pointer to write position
    ridx = 0  # pointer to read position

    # Prewrite empty data to buffer to be read
    blocksize = len(stream.read(ARGS.chunk, exception_on_overflow = False))
    for tmp in range(bfflen):
        buff[tmp] = '0' * blocksize

    # Write to command prompt
    write_terminal(desireddelay)

    # Preload data into output to avoid stuttering during playback
    for tmp in range(ARGS.primelen):
        stream.write('0' * blocksize, ARGS.chunk)

    # Loop until program terminates
    while True:
        # Read a sample
        buff[widx] = stream.read(ARGS.chunk, exception_on_overflow = False)

        # Playback a sample
        try:
            #stream.write(buff[ridx], ARGS.chunk, exception_on_underflow=True)
            stream.write(buff[ridx], ARGS.chunk, exception_on_underflow=False)
        except IOError:  # underflow, priming the output
            #stream.stop_stream()
            stream.close()
            stream = initialize_stream(p)
            for i in range(ARGS.primelen):
                stream.write('0' * blocksize, ARGS.chunk, exception_on_underflow=False)

        # Update write and read pointers
        widx += 1
        ridx += 1
        if widx == bfflen:
            widx = 0
        if ridx == bfflen:
            ridx = 0

        # Check for updated delay
        if conn.poll():
            desireddelay = conn.recv()
            if desireddelay:
                ridx = int((widx - int(desireddelay * bps)) % bfflen)
                write_terminal(desireddelay)
            else:
                stream.stop_stream()
                stream.close()
                break



old_tty_settings = termios.tcgetattr(sys.stdin)

def main():
    tty.setcbreak(sys.stdin.fileno())
    delayval = ARGS.delay

    # Spin off worker processes
    audiopipe, apipe_child = Pipe()
    audioproc = Process(target=audio_worker, args=(apipe_child,))
    audioproc.start()

    gpiopipe, gpipe_child = Pipe()
    gpioproc = Process(target=gpio_worker, args=(gpipe_child,))
    gpioproc.start()

    write_terminal(delayval)

    while True:
        if inputcheck():
            c = sys.stdin.read(1)
            if c == '\x5b' or c == '\x5d':
                delayval += CHG_INCREMENT_SECS if c == '\x5d' else (0 - CHG_INCREMENT_SECS)
                if delayval < CHG_INCREMENT_SECS:
                    delayval = CHG_INCREMENT_SECS
                elif delayval > ARGS.bffsz:
                    delayval = ARGS.bffsz - CHG_INCREMENT_SECS
                audiopipe.send(delayval)
                gpiopipe.send(delayval)
                write_terminal(delayval)
            elif c == '\x71':
                audiopipe.send(False)
                gpiopipe.send(False)
                break

        if gpiopipe.poll():
            delaychg = gpiopipe.recv()
            if delaychg == False:
                audiopipe.send(False)
                gpiopipe.send(False)
                break
            elif type(delaychg) in (int, float):
                delayval += delaychg
                if delayval < CHG_INCREMENT_SECS:
                    delayval = CHG_INCREMENT_SECS
                elif delayval > ARGS.bffsz:
                    delayval = ARGS.bffsz - CHG_INCREMENT_SECS
                audiopipe.send(delayval)
                gpiopipe.send(delayval)
                write_terminal(delayval)


    print("Bailing out!")
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty_settings)
    audioproc.join()
    gpioproc.join()


if __name__ == '__main__':
    main()
