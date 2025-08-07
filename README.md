
# Raspberry Pi Pico 7-Segment Display Clock

This project displays time and temperature on a YSD-439AY2B-35 4-digit 7-segment display using a Raspberry Pi Pico running MicroPython. The display alternates between showing current time (with colon) and temperature (with degree symbol).

![Raspberry Pi Pico 7-Segment Display Clock](attached_assets/IMG_4442_1753983734378.jpeg)

## Overview

This project demonstrates two distinct approaches to driving a 7-segment display:

1. **Simple Pin-by-Pin Approach (`main_simple.py`)** - Straightforward GPIO control with flexible wiring
2. **Optimized mem32 Approach (`main_mem32.py` & `main_mem32_simple.py`)** - High-performance memory-mapped I/O requiring specific wiring

Choose the approach that best fits your needs and experience level.

---

## Approach 1: Simple Pin-by-Pin Control

### Features
- Easy to understand and modify
- Flexible wiring - pins can be connected in any order
- Good for learning and prototyping
- Uses standard MicroPython GPIO functions

### Hardware Requirements
- Raspberry Pi Pico (or Pico W for WiFi)
- YSD-439AY2B-35 4-digit 7-segment display (Common Anode)
- Breadboard and jumper wires
- 8x 220Ω resistors (recommended for segment current limiting)
- 4x 1kΩ resistors (recommended for digit current limiting)

### Simple Approach Wiring

This approach allows flexible wiring. The pins used in `main_simple.py`:

| Pico Pin | GPIO | Function | Display Pin | Resistor |
|----------|------|----------|-------------|----------|
| 10 | GP7 | Degree Cathode | 9 | - |
| 11 | GP8 | Degree Anode | 10 | - |
| 12 | GP9 | Segment F | 11 | 220Ω |
| 14 | GP10 | Colon Cathode | 12 | - |
| 15 | GP11 | Segment C | 13 | 220Ω |
| 16 | GP12 | Segment A | 14 | 220Ω |
| 17 | GP13 | Segment G | 7 | 220Ω |
| 19 | GP14 | Segment B | 16 | 220Ω |
| 21 | GP16 | Digit 1 | 1 | 1kΩ |
| 22 | GP17 | Digit 2 | 2 | 1kΩ |
| 24 | GP18 | Segment D | 3 | 220Ω |
| 25 | GP19 | Colon Anode | 4 | - |
| 26 | GP20 | Segment E | 5 | 220Ω |
| 27 | GP21 | Digit 3 | 6 | 1kΩ |
| 29 | GP22 | Decimal Point | 15 | 220Ω |
| 31 | GP26 | Digit 4 | 8 | 1kΩ |

### Simple Approach Setup

1. Upload `main_simple.py` to your Pico
2. Create `secrets.py` with your WiFi credentials
3. Wire according to the table above
4. Run the code

### Simple Approach Limitations

- Slower refresh rate may cause visible flicker
- Each GPIO operation requires individual function calls
- Less efficient CPU usage

---

## Approach 2: Optimized mem32 Implementation

### Why mem32?

The simple approach, while functional, has performance limitations. Each GPIO operation requires a function call overhead, limiting refresh rates and potentially causing flicker. The mem32 approach addresses this by:

- **Direct memory access** to GPIO registers for maximum speed
- **Batch operations** that set/clear multiple pins simultaneously
- **Flicker-free display** with much higher refresh rates
- **CPU efficiency** for smoother operation

### Performance Comparison

| Aspect | Simple Approach | mem32 Approach |
|--------|----------------|----------------|
| Refresh Rate | ~100Hz (visible flicker) | >400Hz (flicker-free) |
| GPIO Operations | Individual pin calls | Batch register writes |
| CPU Usage | Higher overhead | Optimized direct access |
| Code Complexity | Simple to understand | More advanced |

### Required Rewiring for mem32

**IMPORTANT:** The mem32 approach requires specific GPIO pin arrangements to enable efficient batch operations. You must rewire your display to use consecutive GPIO regions.

#### mem32 Wiring Configuration

The optimized version uses two consecutive GPIO regions for maximum efficiency:

| Pico Pin | GPIO | Function | Display Pin | Notes |
|----------|------|----------|-------------|--------|
| 4 | GP2 | Segment A | 14 | Consecutive |
| 5 | GP3 | Segment B | 16 | GPIO |
| 6 | GP4 | Segment C | 13 | Region |
| 7 | GP5 | Segment D | 3 | 2-9 |
| 8 | GP6 | Segment E | 5 | |
| 9 | GP7 | Segment F | 11 | |
| 10 | GP8 | Segment G | 7 | |
| 11 | GP9 | Decimal Point | 15 | |
| 14 | GP10 | Degree Cathode | 9 | Special |
| 15 | GP11 | Degree Anode | 10 | LEDs |
| 16 | GP12 | Digit 4 | 8 | Consecutive |
| 17 | GP13 | Colon Cathode | 12 | GPIO |
| 24 | GP18 | Digit 1 | 1 | Region |
| 25 | GP19 | Digit 2 | 2 | 18-21 |
| 26 | GP20 | Colon Anode | 4 | |
| 27 | GP21 | Digit 3 | 6 | |

### mem32 Implementation Versions

#### Full Featured Version (`main_mem32.py`)

- **Object-oriented design** with `SevenSegmentDisplay` and `Scroller` classes
- **State machine** for different operating modes
- **Button interaction** with BOOTSEL button
- **Scrolling text support** for long messages
- **Manual mode** for cycling through displays
- **Modular architecture** - easy to swap display drivers or add features

Key classes:
- `SevenSegmentDisplay`: Hardware abstraction layer for the display
- `Scroller`: Handles text scrolling animations
- `ClockApp`: Main application logic and state management

#### Compact Version (`main_mem32_simple.py`)

- **Single file implementation** with minimal structure
- **Same performance benefits** as the full version
- **Reduced code size** for simpler deployment
- **All features included** but in a more compact form

### mem32 Technical Details

#### Memory-Mapped I/O Registers

```python
SIO_BASE = 0xd0000000
GPIO_OUT_SET = SIO_BASE + 0x14  # Set GPIO pins HIGH
GPIO_OUT_CLR = SIO_BASE + 0x18  # Set GPIO pins LOW
```

#### Batch Operations

Instead of individual pin operations:
```python
# Simple approach (slow)
pin.value(1)
pin.value(0)
```

The mem32 approach uses bitmasks:
```python
# mem32 approach (fast)
machine.mem32[GPIO_OUT_SET] = pin_mask  # Set multiple pins
machine.mem32[GPIO_OUT_CLR] = pin_mask  # Clear multiple pins
```

#### Pre-computed Masks

All segment patterns are pre-calculated into bitmasks for instant lookup:
```python
SEG_ON_MASKS['8'] = 0b11111110  # Segments to turn ON for '8'
SEG_OFF_MASKS['8'] = 0b00000001 # Segments to turn OFF for '8'
```

---

## Display Hardware Specifications

**Model:** YSD-439AY2B-35 (Common Anode)
**Datasheet:** https://strawberry-linux.com/pub/YSD-439AY2B-35.pdf

### Display Pinout
```
Top View:
[16][15][14][13][12][11][10][09]

[01][02][03][04][05][06][07][08]
```

### Pin Functions
- **Pin 1:** Digit 1 (leftmost)
- **Pin 2:** Digit 2  
- **Pin 3:** Segment D
- **Pin 4:** Colon Anode (+)
- **Pin 5:** Segment E
- **Pin 6:** Digit 3
- **Pin 7:** Segment G
- **Pin 8:** Digit 4 (rightmost)
- **Pin 9:** Degree Cathode (-)
- **Pin 10:** Degree Anode (+)
- **Pin 11:** Segment F
- **Pin 12:** Colon Cathode (-)
- **Pin 13:** Segment C
- **Pin 14:** Segment A
- **Pin 15:** Decimal Point
- **Pin 16:** Segment B

### 7-Segment Layout
```
    ---A---
   |       |
   F       B
   |       |
    ---G---
   |       |
   E       C
   |       |
    ---D---   . DP
```

---

## Software Setup

### 1. Install MicroPython on Pico
1. Download the latest MicroPython UF2 file for Raspberry Pi Pico
2. Hold BOOTSEL button while connecting Pico to computer
3. Drag the UF2 file to the RPI-RP2 drive
4. Pico will restart with MicroPython

### 2. Create secrets.py
Create a `secrets.py` file with your WiFi credentials:
```python
SSID = "Your_WiFi_Network"
PASSWORD = "Your_WiFi_Password"
```

### 3. Choose and Upload Your Approach
- **Simple:** Upload `main_simple.py` and `secrets.py`
- **Optimized:** Upload `main_mem32.py` (or `main_mem32_simple.py`) and `secrets.py`

---

## Using the Modular Architecture (mem32 versions)

### Swapping Display Drivers

The `SevenSegmentDisplay` class provides a clean interface that can be replaced with other display types:

```python
class MyCustomDisplay:
    def __init__(self, pin_map, refresh_delay_us):
        # Initialize your display hardware
        pass
    
    def show(self, text, colon=None, degree=None):
        # Update display buffer
        pass
    
    def refresh(self):
        # Render current buffer to hardware
        pass

# Use with existing ClockApp
display = MyCustomDisplay(PINS, REFRESH_DELAY_US)
app = ClockApp(display)
app.run()
```

### Creating Custom Applications

The display driver can be used independently:

```python
from main_mem32 import SevenSegmentDisplay, PINS, REFRESH_DELAY_US

display = SevenSegmentDisplay(PINS, REFRESH_DELAY_US)

while True:
    display.show("HELLO")
    display.refresh()
```

---

## Operation

Both approaches provide the same user experience:

### Display Modes
1. **Time Mode:** Shows current time in HH:MM format with colon LED active (10 seconds)
2. **Temperature Mode:** Shows temperature in Celsius with degree symbol LED active (5 seconds)

### Interactive Features (mem32 versions)
- **BOOTSEL Button:** Cycle through manual modes
  - Press once: Show time
  - Press twice: Show temperature  
  - Press third time: Scroll IP address
  - Auto-return to normal cycle after 15 seconds

---

## Troubleshooting

### Common Issues
1. **Display not lighting up:** Check power connections and resistor values
2. **Flicker (simple approach):** Normal behavior - consider upgrading to mem32 approach
3. **No response (mem32):** Verify rewiring to consecutive GPIO regions
4. **WiFi connection fails:** Check SSID/password in secrets.py
5. **Incorrect segments:** Verify wiring against the appropriate pinout table

### Performance Issues
- **Simple approach flicker:** Expected due to slower refresh rate
- **mem32 approach:** Should be completely flicker-free

### Migration from Simple to mem32
1. **Rewire** according to mem32 pinout table
2. **Update** pin configuration in code if using custom pins
3. **Test** with multimeter to verify connections

---

## Choosing Your Approach

| Choose Simple If: | Choose mem32 If: |
|------------------|------------------|
| Learning MicroPython | Want maximum performance |
| Prototyping quickly | Building a finished project |
| Don't mind some flicker | Need flicker-free display |
| Want flexible wiring | Can commit to specific wiring |
| Prefer simpler code | Want modular architecture |

---

## License

This project is open source. Feel free to modify and distribute.
