
# main.py (Refactored with improved display API and clean decimal point handling)
import machine
import utime
import network
import ntptime
import rp2
from secrets import SSID, PASSWORD
import usocket as socket
import ujson

# --- 1. CONFIGURATION ---
# User-configurable settings for the clock.
# --------------------------------------------------------------------------
WIFI_SSID = SSID
WIFI_PASSWORD = PASSWORD

# --- Display Behavior ---
REFRESH_DELAY_US = 2500
SCROLL_DELAY_MS = 350
MANUAL_MODE_TIMEOUT_S = 15

# --- Messages ---
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
    """ Manages a 4-digit, 7-segment display with multiplexing and clean decimal point handling. """
    
    # Base segment patterns (without decimal point)
    BASE_SEGMENT_MAP = {
        ' ': (1, 1, 1, 1, 1, 1, 1), '0': (0, 0, 0, 0, 0, 0, 1),
        '1': (1, 0, 0, 1, 1, 1, 1), '2': (0, 0, 1, 0, 0, 1, 0),
        '3': (0, 0, 0, 0, 1, 1, 0), '4': (1, 0, 0, 1, 1, 0, 0),
        '5': (0, 1, 0, 0, 1, 0, 0), '6': (0, 1, 0, 0, 0, 0, 0),
        '7': (0, 0, 0, 1, 1, 1, 1), '8': (0, 0, 0, 0, 0, 0, 0),
        '9': (0, 0, 0, 0, 1, 0, 0), 'A': (0, 0, 0, 1, 0, 0, 0),
        'B': (1, 1, 0, 0, 0, 0, 0), 'C': (0, 1, 1, 0, 0, 0, 1), 
        'E': (0, 1, 1, 0, 0, 0, 0), 'F': (0, 1, 1, 1, 0, 0, 0), 
        'H': (1, 0, 0, 1, 0, 0, 0), 'I': (1, 1, 1, 1, 0, 0, 1), 
        'L': (1, 1, 1, 0, 0, 0, 1), 'N': (0, 0, 1, 1, 0, 1, 0), 
        'O': (0, 0, 0, 0, 0, 0, 1), 'P': (0, 0, 1, 1, 0, 0, 0), 
        'S': (0, 1, 0, 0, 1, 0, 0), 'U': (1, 1, 0, 0, 0, 1, 1), 
        'W': (1, 0, 0, 0, 1, 0, 1), '-': (1, 1, 1, 1, 1, 1, 0),
    }

    def __init__(self, pin_map, refresh_delay_us):
        self._pins = pin_map
        self.refresh_delay_us = refresh_delay_us
        self._display_data = [(' ', False)] * 4  # (character, has_decimal_point)
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
        
        # Setup digit control masks
        anode_pins_list = ['d1', 'd2', 'd3', 'd4']
        self._ALL_ANODES_MASK = self._get_pin_mask(anode_pins_list)
        self._ANODE_MASKS = [self._get_pin_mask([d]) for d in anode_pins_list]
        
        # Setup segment control masks
        segment_pins_list = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        self._ALL_SEGMENTS_MASK = self._get_pin_mask(segment_pins_list)
        self._DP_MASK = self._get_pin_mask(['dp'])
        
        # Pre-compute segment patterns for each character
        self._SEG_ON_MASKS, self._SEG_OFF_MASKS = {}, {}
        for char, pattern in self.BASE_SEGMENT_MAP.items():
            on_mask, off_mask = 0, 0
            for i, pin_state in enumerate(pattern):
                pin_num = self._pins[segment_pins_list[i]]
                if pin_state == 0: 
                    on_mask |= (1 << pin_num)
                else: 
                    off_mask |= (1 << pin_num)
            self._SEG_ON_MASKS[char] = on_mask
            self._SEG_OFF_MASKS[char] = off_mask
        
        # Setup special LED masks
        self._COLON_ANODE_MASK = self._get_pin_mask(['colon_anode'])
        self._COLON_CATHODE_MASK = self._get_pin_mask(['colon_cathode'])
        self._DEG_ANODE_MASK = self._get_pin_mask(['deg_anode'])
        self._DEG_CATHODE_MASK = self._get_pin_mask(['deg_cathode'])
        
        # Initialize all pins to safe state
        machine.mem32[self._GPIO_OUT_CLR] = self._ALL_ANODES_MASK | self._COLON_ANODE_MASK | self._DEG_ANODE_MASK
        machine.mem32[self._GPIO_OUT_SET] = self._ALL_SEGMENTS_MASK | self._DP_MASK | self._COLON_CATHODE_MASK | self._DEG_CATHODE_MASK

    def show_text(self, text, colon=None, degree=None):
        """
        Display text on the 7-segment display.
        
        Args:
            text (str): Text to display (up to 4 characters). Can include decimal points.
            colon (bool, optional): Show colon between digits 2 and 3
            degree (bool, optional): Show degree symbol
        """
        # Parse text and handle decimal points
        self._display_data = [(' ', False)] * 4
        text_pos = 0
        display_pos = 0
        
        while text_pos < len(text) and display_pos < 4:
            char = text[text_pos].upper()
            has_dp = False
            
            # Check if next character is a decimal point
            if text_pos + 1 < len(text) and text[text_pos + 1] == '.':
                has_dp = True
                text_pos += 1  # Skip the decimal point character
            
            self._display_data[display_pos] = (char, has_dp)
            text_pos += 1
            display_pos += 1
        
        # Update special indicators
        if colon is not None:
            self._colon_on = colon
        if degree is not None:
            self._degree_on = degree

    def show_time(self, hour, minute, colon_blink=True):
        """
        Display time in HH:MM format.
        
        Args:
            hour (int): Hour (0-23)
            minute (int): Minute (0-59)
            colon_blink (bool): Whether to show the colon
        """
        time_str = f"{hour:02d}{minute:02d}"
        self.show_text(time_str, colon=colon_blink, degree=False)

    def show_temperature(self, temp_celsius):
        """
        Display temperature with degree symbol.
        
        Args:
            temp_celsius (float): Temperature in Celsius
        """
        if temp_celsius >= 100:
            temp_str = f"{temp_celsius:4.0f}"
        elif temp_celsius >= 10:
            temp_str = f"{temp_celsius:4.1f}"
        elif temp_celsius >= 0:
            temp_str = f" {temp_celsius:3.1f}"
        else:
            temp_str = f"{temp_celsius:4.1f}"
        
        # Replace last character with 'C' and add degree symbol
        if len(temp_str) >= 4:
            temp_str = temp_str[:3] + 'C'
        
        self.show_text(temp_str, colon=False, degree=True)

    def clear(self):
        """Clear the display."""
        self.show_text("    ", colon=False, degree=False)

    def refresh(self):
        """Refresh the display by multiplexing through all digits."""
        for i in range(4):
            # Turn off all digits first
            machine.mem32[self._GPIO_OUT_CLR] = self._ALL_ANODES_MASK
            
            char, has_dp = self._display_data[i]
            
            # Set segment pattern
            if char in self._SEG_ON_MASKS:
                machine.mem32[self._GPIO_OUT_SET] = self._SEG_OFF_MASKS[char]
                machine.mem32[self._GPIO_OUT_CLR] = self._SEG_ON_MASKS[char]
            else:
                # Unknown character - turn off all segments
                machine.mem32[self._GPIO_OUT_SET] = self._ALL_SEGMENTS_MASK
            
            # Handle decimal point
            if has_dp:
                machine.mem32[self._GPIO_OUT_CLR] = self._DP_MASK
            else:
                machine.mem32[self._GPIO_OUT_SET] = self._DP_MASK
            
            # Turn on current digit
            machine.mem32[self._GPIO_OUT_SET] = self._ANODE_MASKS[i]
            
            # Handle special LEDs on first digit cycle
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
            self.display.show_text(text)
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
            self.display.show_text(display_slice, colon=False, degree=False)
            
            self.index += 1
            
            # Check if the scroll has finished
            if self.index > len(self.message) - 4:
                if self.loop:
                    self.index = 0  # Loop back to the beginning
                else:
                    self.is_active = False # Scroll is complete
        
        return self.is_active


class RestApiServer:
    """Minimal HTTP server to control the display over WiFi."""
    def __init__(self, app):
        self._app = app
        self._sock = None
        self._is_listening = False

    def start(self):
        if self._is_listening:
            return
        try:
            addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
            self._sock = socket.socket()
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception:
                pass
            self._sock.bind(addr)
            self._sock.listen(2)
            # Non-blocking accept
            try:
                self._sock.settimeout(0)
            except Exception:
                pass
            self._is_listening = True
            print("REST API listening on :80")
        except Exception as e:
            print("REST API start error:", e)
            self._sock = None
            self._is_listening = False

    def _url_decode(self, s):
        try:
            res = ''
            i = 0
            while i < len(s):
                c = s[i]
                if c == '+':
                    res += ' '
                    i += 1
                elif c == '%' and i + 2 < len(s):
                    try:
                        res += chr(int(s[i+1:i+3], 16))
                        i += 3
                    except Exception:
                        res += c
                        i += 1
                else:
                    res += c
                    i += 1
            return res
        except Exception:
            return s

    def _parse_request(self, data):
        try:
            text = data.decode('utf-8')
        except Exception:
            text = str(data)
        lines = text.split('\r\n')
        request_line = lines[0] if lines else ''
        parts = request_line.split(' ')
        method = parts[0] if len(parts) > 0 else 'GET'
        target = parts[1] if len(parts) > 1 else '/'
        path, query = target.split('?', 1) if '?' in target else (target, '')

        headers = {}
        i = 1
        while i < len(lines) and lines[i]:
            if ':' in lines[i]:
                k, v = lines[i].split(':', 1)
                headers[k.strip().lower()] = v.strip()
            i += 1

        body = ''
        if method == 'POST':
            try:
                content_length = int(headers.get('content-length', '0'))
            except Exception:
                content_length = 0
            try:
                raw = text.split('\r\n\r\n', 1)[1]
            except Exception:
                raw = ''
            if len(raw) < content_length:
                pass
            body = raw[:content_length]

        params = {}
        if query:
            for pair in query.split('&'):
                if not pair:
                    continue
                if '=' in pair:
                    k, v = pair.split('=', 1)
                else:
                    k, v = pair, ''
                params[self._url_decode(k)] = self._url_decode(v)

        json_payload = None
        if body:
            try:
                json_payload = ujson.loads(body)
            except Exception:
                json_payload = None

        return method, path, params, headers, body, json_payload

    def _send_json(self, conn, status_code, payload_dict):
        try:
            body = ujson.dumps(payload_dict)
        except Exception:
            body = '{"ok":false}'
        status_text = 'OK' if status_code == 200 else 'ERROR'
        headers = [
            'HTTP/1.1 %d %s' % (status_code, status_text),
            'Content-Type: application/json',
            'Connection: close',
            'Content-Length: %d' % len(body),
            '',
            ''
        ]
        try:
            conn.send('\r\n'.join(headers))
            conn.send(body)
        except Exception:
            pass

    def poll(self):
        if not self._is_listening or self._sock is None:
            return
        try:
            conn, addr = self._sock.accept()
        except OSError:
            return
        except Exception:
            return
        try:
            try:
                conn.settimeout(0.5)
            except Exception:
                pass
            data = conn.recv(1024)
            method, path, params, headers, body, json_payload = self._parse_request(data or b'')

            def get_param(name, default=None):
                if json_payload and name in json_payload:
                    return json_payload.get(name, default)
                return params.get(name, default)

            if path == '/api/status':
                self._send_json(conn, 200, {
                    'ok': True,
                    'ip': self._app.ip_address,
                    'state': self._app.state,
                    'mode': self._app.time_temp_mode,
                })
                return

            if path == '/api/clear':
                self._app.scroller.stop()
                self._app.display.clear()
                self._app.exit_api_mode()
                self._send_json(conn, 200, {'ok': True})
                return

            if path == '/api/display':
                text = get_param('text', '')
                if not isinstance(text, str):
                    text = str(text)
                colon = get_param('colon', None)
                degree = get_param('degree', None)
                duration_s = get_param('duration', 15)
                try:
                    duration_s = int(duration_s)
                except Exception:
                    duration_s = 15
                self._app.api_show_text(text, self._to_bool(colon) if colon is not None else None, self._to_bool(degree) if degree is not None else None, duration_s)
                self._send_json(conn, 200, {'ok': True})
                return

            if path == '/api/scroll':
                text = get_param('text', '')
                if not isinstance(text, str):
                    text = str(text)
                loop = self._to_bool(get_param('loop', False))
                duration_s = get_param('duration', 15)
                try:
                    duration_s = int(duration_s)
                except Exception:
                    duration_s = 15
                self._app.api_scroll_text(text, loop, duration_s)
                self._send_json(conn, 200, {'ok': True})
                return

            # Default root
            self._send_json(conn, 200, {
                'ok': True,
                'message': 'Pico 7-seg API',
                'endpoints': ['/api/status', '/api/display', '/api/scroll', '/api/clear']
            })
        except Exception as e:
            try:
                self._send_json(conn, 500, {'ok': False, 'error': str(e)})
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _to_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ('1', 'true', 'yes', 'on'): return True
            if v in ('0', 'false', 'no', 'off', ''): return False
        return bool(value)


class ClockApp:
    """The main application logic for the clock."""
    def __init__(self, display):
        self.display = display
        self.scroller = Scroller(display, SCROLL_DELAY_MS)
        self.wlan = None
        self.ip_address = "NO IP"
        self.api_server = RestApiServer(self)

        # --- State Machine ---
        self.state = 'STARTUP'
        self.next_state_after_scroll = None # Used to track where to go after a scroll finishes
        
        # --- Time/Temp Cycle ---
        self.last_data_update_ms = 0
        self.last_mode_switch_ms = 0
        self.time_temp_mode = 'time'
        self.colon_blink_state = False
        self.api_mode_end_ms = 0

        # --- Manual Mode ---
        self.button_state = 0
        self.last_manual_action_ms = 0
        self.manual_mode_index = 0

    def _connect_to_wifi(self):
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
            try:
                self.api_server.start()
            except Exception as e:
                print("API server start failed:", e)
            return True

    def _sync_time(self):
        print("Attempting to sync time...")
        try: 
            ntptime.settime()
            print("Time synced successfully.")
        except Exception as e: 
            print(f"Time sync error: {e}")

    def _read_temperature(self):
        adc = machine.ADC(4)
        adc_voltage = adc.read_u16() * (3.3 / 65535)
        return 27 - (adc_voltage - 0.706) / 0.001721
    
    def _format_ip_for_display(self):
        """Format IP address for scrolling display, handling decimal points properly."""
        if self.ip_address == "NO IP":
            return self.ip_address
        
        # Replace dots with periods that will be handled by the display system
        return self.ip_address.replace('.', '.')

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
            self.display.show_text("CONN")
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
                    self.display.show_time(tm[3], tm[4], self.colon_blink_state)
                else:
                    self.display.show_temperature(self._read_temperature())

        # --- State: API_STATIC ---
        elif self.state == 'API_STATIC':
            if utime.ticks_diff(current_time_ms, self.api_mode_end_ms) >= 0:
                self.state = 'NORMAL_CYCLE'
                print("API static display expired. Returning to NORMAL_CYCLE")
                return

        # --- State: API_SCROLL ---
        elif self.state == 'API_SCROLL':
            if utime.ticks_diff(current_time_ms, self.api_mode_end_ms) >= 0:
                self.scroller.stop()
                self.state = 'NORMAL_CYCLE'
                print("API scroll expired. Returning to NORMAL_CYCLE")
                return

    # --- API helpers ---
    def _enter_api_mode(self, duration_s):
        now_ms = utime.ticks_ms()
        self.api_mode_end_ms = utime.ticks_add(now_ms, int(duration_s) * 1000)

    def exit_api_mode(self):
        self.api_mode_end_ms = 0
        if self.state in ('API_STATIC', 'API_SCROLL'):
            self.state = 'NORMAL_CYCLE'

    def api_show_text(self, text, colon=None, degree=None, duration_s=15):
        self.scroller.stop()
        try:
            self.display.show_text(text, colon=bool(colon) if colon is not None else None, degree=bool(degree) if degree is not None else None)
        except Exception:
            self.display.show_text(str(text))
        self._enter_api_mode(duration_s)
        self.state = 'API_STATIC'
        print("API: show text:", text)

    def api_scroll_text(self, text, loop=False, duration_s=15):
        self.scroller.start(text, loop=bool(loop))
        self._enter_api_mode(duration_s)
        self.state = 'API_SCROLL'
        print("API: scroll text:", text, "loop=", loop)
        

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
            # Poll REST API (non-blocking)
            try:
                self.api_server.poll()
            except Exception:
                pass


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
