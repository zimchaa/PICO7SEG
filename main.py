# main.py
# Simple code for the YSD-439AY2B-35 display.
# Features stable colon/degree LEDs and flicker-free temperature updates.
# Allows a simple wiring approach where the top 8 pins are connected to the top of the PICO, and the bottom to the bottom

import machine
import utime
import network
import ntptime
from secrets import SSID, PASSWORD

# ==============================================================================
# WIRING GUIDE AND PINOUT CONFIGURATION
# ==============================================================================
#
# Display Model: YSD-439AY2B-35 (Common Anode)
#
# Display Pin Diagram (Top-down view):
#
#      [16][15][14][13][12][11][10][09]
#
#      [01][02][03][04][05][06][07][08]

#
# 7-Segment Diagram:
#      ---A---
#     |       |
#     F       B
#     |       |
#      ---G---
#     |       |
#     E       C
#     |       |
#      ---D---   . DP
#
# Special LEDs:
# L1, L2: Colon (:)
# L3: Degree Symbol (°)
#
# ------------------------------------------------------------------------------
# Pico GP Pin -> Display Function -> Display Pin #
# ------------------------------------------------------------------------------

# --- Segment Pins (Cathodes - Set LOW to turn ON) ---
segments = [
    machine.Pin(12, machine.Pin.OUT),  # Segment A  -> Display Pin 14
    machine.Pin(14, machine.Pin.OUT),  # Segment B  -> Display Pin 16
    machine.Pin(11, machine.Pin.OUT),  # Segment C  -> Display Pin 13
    machine.Pin(18, machine.Pin.OUT),  # Segment D  -> Display Pin 3
    machine.Pin(20, machine.Pin.OUT),  # Segment E  -> Display Pin 5
    machine.Pin(9, machine.Pin.OUT),   # Segment F  -> Display Pin 11
    machine.Pin(13, machine.Pin.OUT),  # Segment G  -> Display Pin 7 
    machine.Pin(22, machine.Pin.OUT)   # Segment DP -> Display Pin 15 
]

# --- Digit Select Pins (Anodes - Set HIGH to turn ON) ---
digits = [
    machine.Pin(16, machine.Pin.OUT),  # Digit 1 (Left) -> Display Pin 1
    machine.Pin(17, machine.Pin.OUT),  # Digit 2        -> Display Pin 2
    machine.Pin(21, machine.Pin.OUT),  # Digit 3        -> Display Pin 6
    machine.Pin(26, machine.Pin.OUT)   # Digit 4 (Right)-> Display Pin 8
]

# --- Special LED Pins (Driven Independently) ---
# To turn on, set Anode HIGH and Cathode LOW.
colon_anode = machine.Pin(19, machine.Pin.OUT)     # Anode (+) for Colon -> Display Pin 4
colon_cathode = machine.Pin(10, machine.Pin.OUT)   # Cathode (-) for Colon -> Display Pin 12
degree_anode = machine.Pin(8, machine.Pin.OUT)     # Anode (+) for Degree -> Display Pin 10
degree_cathode = machine.Pin(7, machine.Pin.OUT)   # Cathode (-) for Degree -> Display Pin 9

# --- Constants ---
SEGMENT_ON, SEGMENT_OFF = 0, 1
DIGIT_ON, DIGIT_OFF = 1, 0

segment_patterns = {
    '0':(0,0,0,0,0,0,1),'1':(1,0,0,1,1,1,1),'2':(0,0,1,0,0,1,0),
    '3':(0,0,0,0,1,1,0),'4':(1,0,0,1,1,0,0),'5':(0,1,0,0,1,0,0),
    '6':(0,1,0,0,0,0,0),'7':(0,0,0,1,1,1,1),'8':(0,0,0,0,0,0,0),
    '9':(0,0,0,1,1,0,0),'C':(1,1,1,0,0,1,0),'F':(0,1,1,1,0,0,0),
    '-':(1,1,1,1,1,1,0),' ':(1,1,1,1,1,1,1),'E':(0,1,1,0,0,0,0),
    'R':(1,1,1,0,1,0,1) # Lowercase 'r'
}

# ==============================================================================
# GLOBAL STATE VARIABLES
# ==============================================================================
# These hold the data that the display will render.
# They are updated periodically by the main loop's timers.
time_str = "----"
temp_str = "----"
colon_on = False
degree_on = False

# ==============================================================================
# FUNCTIONS
# =================================================S=============================
def connect_wifi():
    """Connects to WiFi and syncs time. Returns True on success."""
    # (Function is unchanged, kept for completeness)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    print("Connecting to WiFi...")
    max_wait = 15
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3: break
        max_wait -= 1; utime.sleep(1)

    if wlan.status() != 3:
        print("WiFi connection failed.")
        return False
    else:
        print('Connected! IP:', wlan.ifconfig()[0])
        try:
            ntptime.settime()
            print("Time synced successfully.")
        except Exception as e:
            print("Failed to sync time:", e)
        return True

def clear_digits_and_segments():
    """Turns off all 7-segment digits and segments to prevent ghosting."""
    for segment in segments:
        segment.value(SEGMENT_OFF)
    for digit in digits:
        digit.value(DIGIT_OFF)

def display(text):
    """
    Renders the given 4-character text by multiplexing the digits.
    This function should be called repeatedly in a fast loop.
    It does NOT control the colon or degree symbol; they are set independently.
    """
    text_to_display = "{:4}".format(text)
    dp_pos = text_to_display.find('.')
    if dp_pos != -1:
        text_to_display = text_to_display.replace('.', '')

    for i in range(4):
        clear_digits_and_segments()

        char = text_to_display[i]
        pattern = segment_patterns.get(char.upper(), segment_patterns[' '])
        for j in range(7):
            segments[j].value(pattern[j])

        if i == dp_pos - 1:
            segments[7].value(SEGMENT_ON) # Turn on Decimal Point

        digits[i].value(DIGIT_ON) # Turn on current digit
        utime.sleep_ms(10) # Multiplexing delay

# ==============================================================================
# MAIN PROGRAM
# ==============================================================================

# --- Setup ---
sensor_temp = machine.ADC(4)
conversion_factor = 3.3 / 65535
wifi_connected = connect_wifi()

# --- Timing Control ---
DATA_UPDATE_INTERVAL_MS = 1000  # Update data once per second
MODE_SWITCH_INTERVAL_MS = 10000 # Switch modes every 10 seconds
last_data_update = utime.ticks_ms()
last_mode_switch = utime.ticks_ms()
display_mode = "TIME"

print("Starting main loop...")

while True:
    current_ticks = utime.ticks_ms()

    # --- TIMER 1: Data Acquisition (runs every 1 second) ---
    if utime.ticks_diff(current_ticks, last_data_update) > DATA_UPDATE_INTERVAL_MS:
        # Get time
        if wifi_connected:
            current_time = utime.localtime()
            time_str = "{:02d}{:02d}".format(current_time[3], current_time[4])
        else:
            time_str = "Err" # Show error if no WiFi for time

        # Get temperature
        reading = sensor_temp.read_u16() * conversion_factor
        temperature = 27 - (reading - 0.706) / 0.001721
        temp_str = "{:>3.0f}C".format(temperature)

        last_data_update = current_ticks

    # --- TIMER 2: Mode Switching (runs every 10 seconds) ---
    if utime.ticks_diff(current_ticks, last_mode_switch) > MODE_SWITCH_INTERVAL_MS:
        display_mode = "TEMP" if display_mode == "TIME" else "TIME"
        last_mode_switch = current_ticks

    # --- State Management & Rendering ---
    # This part of the loop runs as fast as possible.

    # 1. Decide what to show based on the current mode
    if display_mode == "TIME":
        text_to_show = time_str
        colon_on = True
        degree_on = False
    else: # TEMP mode
        text_to_show = temp_str
        colon_on = False
        degree_on = True

    # 2. Set the state of the independent LEDs (they will stay on/off)
    colon_anode.value(DIGIT_ON if colon_on else DIGIT_OFF)
    colon_cathode.value(SEGMENT_ON if colon_on else SEGMENT_OFF)
    degree_anode.value(DIGIT_ON if degree_on else DIGIT_OFF)
    degree_cathode.value(SEGMENT_ON if degree_on else SEGMENT_OFF)

    # 3. Call the display renderer to handle the multiplexing
    display(text_to_show)
