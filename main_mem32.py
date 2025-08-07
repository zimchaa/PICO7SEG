# main.py (Refactored with a dedicated Scroller class)
import machine
import utime
import network
import ntptime
import rp2
from secrets import SSID, PASSWORD

# --- 1. CONFIGURATION ---
# User-configurable settings for the clock.
# --------------------------------------------------------------------------
WIFI_SSID = SSID
WIFI_PASSWORD = PASSWORD

# --- Display Behavior ---
REFRESH_DELAY_US = 2500
SCROLL_DELAY_MS = 350
MANUAL_MODE_TIMEOUT_S = 15

# --- Messages (Padding is now handled by the Scroller class) ---
STARTUP_MESSAGE = "HELLO PICO"
WIFI_FAIL_MESSAGE = "WIFI FAILED"

# --- Hardware Pin Mapping ---
PINS = {
    'a': 2, 'b': 3, 'c': 4, 'd': 5, 'e': 6, 'f': 7, 'g': 8, 'dp': 9,
    'd1': 18, 'd2': 19, 'd3': 21, 'd4': 12,
    'colon_anode': 20, 'colon_cathode': 13,
    'deg_anode': 11, 'deg_cathode': 10
}
# --------------------------------------------------------------------------


class SevenSegmentDisplay:
    """ Manages a 4-digit, 7-segment display with multiplexing. (Unchanged from previous refactor) """
    SEGMENT_MAP = {
        ' ': (1, 1, 1, 1, 1, 1, 1, 1), '0': (0, 0, 0, 0, 0, 0, 1, 1),
        '1': (1, 0, 0, 1, 1, 1, 1, 1), '2': (0, 0, 1, 0, 0, 1, 0, 1),
        '3': (0, 0, 0, 0, 1, 1, 0, 1), '4': (1, 0, 0, 1, 1, 0, 0, 1),
        '5': (0, 1, 0, 0, 1, 0, 0, 1), '6': (0, 1, 0, 0, 0, 0, 0, 1),
        '7': (0, 0, 0, 1, 1, 1, 1, 1), '8': (0, 0, 0, 0, 0, 0, 0, 1),
        '9': (0, 0, 0, 0, 1, 0, 0, 1), 'A': (0, 0, 0, 1, 0, 0, 0, 1),
        'B': (1, 1, 0, 0, 0, 0, 0, 1), 'C': (0, 1, 1, 0, 0, 0, 1, 1), 
        'E': (0, 1, 1, 0, 0, 0, 0, 1), 'F': (0, 1, 1, 1, 0, 0, 0, 1), 
        'H': (1, 0, 0, 1, 0, 0, 0, 1), 'I': (1, 1, 1, 1, 0, 0, 1, 1), 
        'L': (1, 1, 1, 0, 0, 0, 1, 1), 'N': (0, 0, 1, 1, 0, 1, 0, 1), 
        'O': (0, 0, 0, 0, 0, 0, 1, 1), 'P': (0, 0, 1, 1, 0, 0, 0, 1), 
        'S': (0, 1, 0, 0, 1, 0, 0, 1), 'U': (1, 1, 0, 0, 0, 1, 1, 1), 
        'W': (1, 0, 0, 0, 1, 0, 1, 1), '-': (1, 1, 1, 1, 1, 1, 0, 1),
    }
    for i in range(10):
        char = str(i)
        SEGMENT_MAP[char + '.'] = SEGMENT_MAP[char][:-1] + (0,)

    def __init__(self, pin_map, refresh_delay_us):
        self._pins = pin_map
        self.refresh_delay_us = refresh_delay_us
        self._display_buffer = [' '] * 4
        self._colon_on = False
        self._degree_on = False
        self._setup_pins()
        self._setup_mem32()

    def _get_pin_mask(self, pin_names):
        mask = 0
        for name in pin_names:
            mask |= (1 << self._pins[name])
        return mask

    def _setup_pins(self):
        print("Initializing GPIO pins...")
        for pin_num in self._pins.values():
            machine.Pin(pin_num, machine.Pin.OUT)

    def _setup_mem32(self):
        print("Setting up fast memory-mapped I/O...")
        SIO_BASE = 0xd0000000
        self._GPIO_OUT_SET = SIO_BASE + 0x14
        self._GPIO_OUT_CLR = SIO_BASE + 0x18
        anode_pins_list = ['d1', 'd2', 'd3', 'd4']
        self._ALL_ANODES_MASK = self._get_pin_mask(anode_pins_list)
        self._ANODE_MASKS = [self._get_pin_mask([d]) for d in anode_pins_list]
        segment_pins_list = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'dp']
        self._ALL_SEGMENTS_MASK = self._get_pin_mask(segment_pins_list)
        self._SEG_ON_MASKS, self._SEG_OFF_MASKS = {}, {}
        for char, pattern in self.SEGMENT_MAP.items():
            on_mask, off_mask = 0, 0
            for i, pin_state in enumerate(pattern):
                pin_num = self._pins[segment_pins_list[i]]
                if pin_state == 0: on_mask |= (1 << pin_num)
                else: off_mask |= (1 << pin_num)
            self._SEG_ON_MASKS[char] = on_mask
            self._SEG_OFF_MASKS[char] = off_mask
        self._COLON_ANODE_MASK = self._get_pin_mask(['colon_anode'])
        self._COLON_CATHODE_MASK = self._get_pin_mask(['colon_cathode'])
        self._DEG_ANODE_MASK = self._get_pin_mask(['deg_anode'])
        self._DEG_CATHODE_MASK = self._get_pin_mask(['deg_cathode'])
        machine.mem32[self._GPIO_OUT_CLR] = self._ALL_ANODES_MASK | self._COLON_ANODE_MASK | self._DEG_ANODE_MASK
        machine.mem32[self._GPIO_OUT_SET] = self._ALL_SEGMENTS_MASK | self._COLON_CATHODE_MASK | self._DEG_CATHODE_MASK

    def show(self, text, colon=None, degree=None):
        processed_text = []
        i = 0
        while i < len(text) and len(processed_text) < 4:
            char = text[i].upper()
            if i + 1 < len(text) and text[i+1] == '.':
                processed_text.append(char + '.')
                i += 2
            else:
                processed_text.append(char)
                i += 1
        self._display_buffer = list(f"{''.join(processed_text): <4}")
        if colon is not None: self._colon_on = colon
        if degree is not None: self._degree_on = degree

    def refresh(self):
        for i in range(4):
            machine.mem32[self._GPIO_OUT_CLR] = self._ALL_ANODES_MASK
            char_to_display = self._display_buffer[i]
            if char_to_display in self.SEGMENT_MAP:
                machine.mem32[self._GPIO_OUT_SET] = self._SEG_OFF_MASKS[char_to_display]
                machine.mem32[self._GPIO_OUT_CLR] = self._SEG_ON_MASKS[char_to_display]
            else:
                machine.mem32[self._GPIO_OUT_SET] = self._ALL_SEGMENTS_MASK
            machine.mem32[self._GPIO_OUT_SET] = self._ANODE_MASKS[i]
            if i == 0:
                if self._colon_on:
                    machine.mem32[self._GPIO_OUT_SET] = self._COLON_ANODE_MASK
                    machine.mem32[self._GPIO_OUT_CLR] = self._COLON_CATHODE_MASK
                else:
                    machine.mem32[self._GPIO_OUT_CLR] = self._COLON_ANODE_MASK
                if self._degree_on:
                    machine.mem32[self._GPIO_OUT_SET] = self._DEG_ANODE_MASK
                    machine.mem32[self._GPIO_OUT_CLR] = self._DEG_CATHODE_MASK
                else:
                    machine.mem32[self._GPIO_OUT_CLR] = self._DEG_ANODE_MASK
            utime.sleep_us(self.refresh_delay_us)


class Scroller:
    """
    Handles displaying static or scrolling text on a SevenSegmentDisplay.
    If the text fits on the 4-digit display, it is shown statically.
    If it's longer, it scrolls the text from right to left.
    """
    def __init__(self, display, scroll_delay_ms):
        self.display = display
        self.scroll_delay_ms = scroll_delay_ms
        self.message = ""
        self.index = 0
        self.is_active = False
        self.loop = False
        self.last_scroll_time_ms = 0

    def start(self, text, loop=False):
        """
        Starts a new text sequence. Displays statically or starts a scroll.
        :param text: The string to display.
        :param loop: If True, the scroll will repeat indefinitely.
        """
        # If the text fits, just show it and we're done.
        if len(text) <= 4:
            self.display.show(text)
            self.is_active = False
            return

        # For longer text, set up for scrolling.
        # Add 3 spaces of padding on each side for a smooth entry/exit.
        self.message = (' ' * 3) + text + (' ' * 3)
        self.index = 0
        self.loop = loop
        self.is_active = True
        self.last_scroll_time_ms = utime.ticks_ms()

    def stop(self):
        """Immediately stops any active scroll."""
        self.is_active = False

    def update(self):
        """
        Call this in a loop. If a scroll is active, it will update the display
        at the correct interval. Returns True if the scroll is still active.
        """
        if not self.is_active:
            return False

        now = utime.ticks_ms()
        if utime.ticks_diff(now, self.last_scroll_time_ms) > self.scroll_delay_ms:
            self.last_scroll_time_ms = now
            
            # Display the 4-character slice of the message
            display_slice = self.message[self.index : self.index + 4]
            # Scrolling text does not use colon or degree indicators
            self.display.show(display_slice, colon=False, degree=False)
            
            self.index += 1
            
            # Check if the scroll has finished
            if self.index > len(self.message) - 4:
                if self.loop:
                    self.index = 0  # Loop back to the beginning
                else:
                    self.is_active = False # Scroll is complete
        
        return self.is_active


class ClockApp:
    """The main application logic for the clock."""
    def __init__(self, display):
        self.display = display
        self.scroller = Scroller(display, SCROLL_DELAY_MS)
        self.wlan = None
        self.ip_address = "NO IP"

        # --- State Machine ---
        self.state = 'STARTUP'
        self.next_state_after_scroll = None # Used to track where to go after a scroll finishes
        
        # --- Time/Temp Cycle ---
        self.last_data_update_ms = 0
        self.last_mode_switch_ms = 0
        self.time_temp_mode = 'time'
        self.colon_blink_state = False

        # --- Manual Mode ---
        self.button_state = 0
        self.last_manual_action_ms = 0
        self.manual_mode_index = 0

    def _connect_to_wifi(self):
        # (Implementation unchanged)
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        print(f"Connecting to '{WIFI_SSID}'...")
        max_wait = 10
        while max_wait > 0 and self.wlan.status() < 3:
            max_wait -= 1; print(".", end=""); utime.sleep(1)
        if self.wlan.status() != 3:
            print("\nWi-Fi connection failed.")
            self.ip_address = "NO IP"
            return False
        else:
            self.ip_address = self.wlan.ifconfig()[0]
            print(f"\nConnected! IP: {self.ip_address}")
            return True

    def _sync_time(self):
        # (Implementation unchanged)
        print("Attempting to sync time...")
        try: ntptime.settime(); print("Time synced successfully.")
        except Exception as e: print(f"Time sync error: {e}")

    def _read_temperature(self):
        # (Implementation unchanged)
        adc = machine.ADC(4)
        adc_voltage = adc.read_u16() * (3.3 / 65535)
        return 27 - (adc_voltage - 0.706) / 0.001721
    
    def _format_ip_for_display(self):
        # (Implementation unchanged, no longer adds padding)
        processed_list = []
        i = 0
        while i < len(self.ip_address):
            char = self.ip_address[i]
            if i + 1 < len(self.ip_address) and self.ip_address[i+1] == '.':
                processed_list.append(char + '.')
                i += 2
            else:
                processed_list.append(char)
                i += 1
        return "".join(processed_list)

    def _handle_button_press(self, current_time_ms):
        is_pressed = rp2.bootsel_button()
        if is_pressed and not self.button_state:
            utime.sleep_ms(50) # Debounce
            if rp2.bootsel_button():
                print("BOOTSEL button pressed.")
                self.last_manual_action_ms = current_time_ms
                
                # If a looping scroll was active (IP address), stop it.
                if self.state == 'MANUAL_IP_SCROLL':
                    self.scroller.stop()

                if self.state in ('MANUAL_MODE', 'MANUAL_IP_SCROLL'):
                    self.manual_mode_index = (self.manual_mode_index + 1) % 3
                else: # Entering manual mode
                    self.manual_mode_index = 0

                # Set the new state based on the manual index
                if self.manual_mode_index == 2:
                    self.state = 'MANUAL_IP_SCROLL'
                else:
                    self.state = 'MANUAL_MODE'
                
                print(f"New State: {self.state}, Manual Index: {self.manual_mode_index}")
        self.button_state = is_pressed

    def _update_state_machine(self, current_time_ms):
        """The main state machine logic. Decides what action to take."""
        
        # --- Priority 1: Handle Active Scrolling ---
        # If the scroller is busy, we let it update the display and do nothing else.
        if self.scroller.is_active:
            self.scroller.update()
            return

        # --- Priority 2: Process State Transitions ---
        # If the scroller is NOT active, we can proceed with other logic.
        
        # --- State: STARTUP ---
        if self.state == 'STARTUP':
            self.scroller.start(STARTUP_MESSAGE)
            self.next_state_after_scroll = 'CONNECTING_WIFI'
            self.state = 'AWAIT_SCROLL' # Wait for the scroll to finish
            print(f"State changed to: AWAIT_SCROLL (next: {self.next_state_after_scroll})")
            
        # --- State: AWAIT_SCROLL ---
        elif self.state == 'AWAIT_SCROLL':
            # This state is entered after a scroll starts. We do nothing until the
            # scroller is finished, at which point we transition to the next planned state.
            if not self.scroller.is_active:
                self.state = self.next_state_after_scroll
                print(f"Scroll finished. State changed to: {self.state}")

        # --- State: CONNECTING_WIFI ---
        elif self.state == 'CONNECTING_WIFI':
            self.display.show("CONN")
            if self._connect_to_wifi():
                self._sync_time()
                self.scroller.start(self._format_ip_for_display())
            else:
                self.scroller.start(WIFI_FAIL_MESSAGE)
            
            self.next_state_after_scroll = 'NORMAL_CYCLE'
            self.state = 'AWAIT_SCROLL'
            print(f"State changed to: AWAIT_SCROLL (next: {self.next_state_after_scroll})")

        # --- State: NORMAL_CYCLE ---
        elif self.state == 'NORMAL_CYCLE':
            duration_s = 10 if self.time_temp_mode == 'time' else 5
            if utime.ticks_diff(current_time_ms, self.last_mode_switch_ms) > duration_s * 1000:
                self.last_mode_switch_ms = current_time_ms
                self.time_temp_mode = 'temp' if self.time_temp_mode == 'time' else 'time'

            if utime.ticks_diff(current_time_ms, self.last_data_update_ms) >= 1000:
                self.last_data_update_ms = current_time_ms
                if self.time_temp_mode == 'time':
                    tm = utime.localtime()
                    self.colon_blink_state = not self.colon_blink_state
                    self.display.show(f"{tm[3]:02d}{tm[4]:02d}", colon=self.colon_blink_state, degree=False)
                else:
                    self.display.show(f"{self._read_temperature():4.1f}C", colon=False, degree=True)
        
        # --- State: MANUAL_MODE ---
        elif self.state == 'MANUAL_MODE':
            if utime.ticks_diff(current_time_ms, self.last_manual_action_ms) > MANUAL_MODE_TIMEOUT_S * 1000:
                self.state = 'NORMAL_CYCLE'
                print(f"Manual mode timed out. State changed to: {self.state}")
                return

            if self.manual_mode_index == 0: # Show Time
                tm = utime.localtime()
                self.display.show(f"{tm[3]:02d}{tm[4]:02d}", colon=True, degree=False)
            elif self.manual_mode_index == 1: # Show Temp
                self.display.show(f"{self._read_temperature():4.1f}C", colon=False, degree=True)

        # --- State: MANUAL_IP_SCROLL ---
        elif self.state == 'MANUAL_IP_SCROLL':
            if utime.ticks_diff(current_time_ms, self.last_manual_action_ms) > MANUAL_MODE_TIMEOUT_S * 1000:
                self.scroller.stop() # Stop the scroll before changing state
                self.state = 'NORMAL_CYCLE'
                print(f"Manual mode timed out. State changed to: {self.state}")
                return
            
            # This state's action is to start a looping scroll.
            # The check at the top of the function will then take over.
            self.scroller.start(self._format_ip_for_display(), loop=True)
            print("Started looping IP scroll.")

    def run(self):
        """The main execution loop."""
        print("--- Pico W 7-Segment Clock Starting ---")
        print(f"Initial state: {self.state}")

        while True:
            # Always refresh the display as fast as possible for a flicker-free image.
            self.display.refresh()

            # The rest of the logic can run slightly less frequently.
            current_time_ms = utime.ticks_ms()
            self._handle_button_press(current_time_ms)
            self._update_state_machine(current_time_ms)


# --- Main Execution ---
if __name__ == "__main__":
    try:
        display = SevenSegmentDisplay(PINS, REFRESH_DELAY_US)
        app = ClockApp(display)
        app.run()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        utime.sleep(10)
        machine.reset()