# main.py (Standalone & Interactive, Full IP Scroll)
import machine, utime, network, ntptime, rp2
from secrets import SSID, PASSWORD

# --- 1. CONFIGURATION ---
WIFI_SSID, WIFI_PASSWORD = SSID, PASSWORD 
REFRESH_DELAY_US, SCROLL_DELAY_MS, MANUAL_MODE_TIMEOUT_S = 2500, 350, 15
STARTUP_MESSAGE, WIFI_FAIL_MESSAGE = "   HELLO PICO   ", "   WIFI FAILED   "

# --- 2. HARDWARE SETUP ---
PINS = {'a':2,'b':3,'c':4,'d':5,'e':6,'f':7,'g':8,'dp':9,'d1':18,'d2':19,'d3':21,'d4':12,'colon_anode':20,'colon_cathode':13,'deg_anode':11,'deg_cathode':10}
for pin_num in PINS.values(): machine.Pin(pin_num, machine.Pin.OUT)
SEGMENT_ORDER = ['a','b','c','d','e','f','g','dp']
SEGMENT_MAP = {' ':(1,1,1,1,1,1,1,1),'0':(0,0,0,0,0,0,1,1),'1':(1,0,0,1,1,1,1,1),'2':(0,0,1,0,0,1,0,1),'3':(0,0,0,0,1,1,0,1),'4':(1,0,0,1,1,0,0,1),'5':(0,1,0,0,1,0,0,1),'6':(0,1,0,0,0,0,0,1),'7':(0,0,0,1,1,1,1,1),'8':(0,0,0,0,0,0,0,1),'9':(0,0,0,0,1,0,0,1),'A':(0,0,0,1,0,0,0,1),'C':(0,1,1,0,0,0,1,1),'E':(0,1,1,0,0,0,0,1),'F':(0,1,1,1,0,0,0,1),'H':(1,0,0,1,0,0,0,1),'I':(1,1,1,1,0,0,1,1),'L':(1,1,1,0,0,0,1,1),'N':(0,0,1,1,0,1,0,1),'O':(0,0,0,0,0,0,1,1),'P':(0,0,1,1,0,0,0,1),'W':(1,0,0,0,1,0,1,1),'-':(1,1,1,1,1,1,0,1)}
for i in range(10): char = str(i); SEGMENT_MAP[char + '.'] = SEGMENT_MAP[char][:-1] + (0,)

# --- 3. FAST MEM32 SETUP ---
SIO_BASE = 0xd0000000
GPIO_OUT_SET, GPIO_OUT_CLR = SIO_BASE + 0x14, SIO_BASE + 0x18
def get_pin_mask(nums): m=0;[m:=m|(1<<n) for n in nums];return m
SEG_PINS,ANODE_PINS=[PINS[s] for s in SEGMENT_ORDER],[PINS[d] for d in ['d1','d2','d3','d4']]
ALL_ANODES_MASK,ALL_SEGMENTS_MASK=get_pin_mask(ANODE_PINS),get_pin_mask(SEG_PINS)
ANODE_MASKS=[get_pin_mask([n]) for n in ANODE_PINS]
SEG_ON,SEG_OFF={},{}
for c,p in SEGMENT_MAP.items():
    on_m,off_m=0,0
    for i,s in enumerate(SEGMENT_ORDER):
        if p[i]==0:on_m|=1<<PINS[s]
        else:off_m|=1<<PINS[s]
    SEG_ON[c],SEG_OFF[c]=on_m,off_m
CA_M,CC_M=get_pin_mask([PINS['colon_anode']]),get_pin_mask([PINS['colon_cathode']])
DA_M,DC_M=get_pin_mask([PINS['deg_anode']]),get_pin_mask([PINS['deg_cathode']])

# --- 4. HELPER FUNCTIONS ---
def connect_to_wifi():
    wlan=network.WLAN(network.STA_IF);wlan.active(True);wlan.connect(WIFI_SSID,WIFI_PASSWORD)
    print(f"Connecting to '{WIFI_SSID}'...");max_wait=10
    while max_wait>0:
        if wlan.status()<0 or wlan.status()>=3:break
        max_wait-=1;utime.sleep(1)
    if wlan.status()!=3:print("\nWi-Fi connection failed");return None
    else:print("\nConnected! IP:",wlan.ifconfig()[0]);return wlan
def sync_time():
    try:ntptime.settime();print("Time synced.")
    except Exception as e:print("Time sync error:",e)
def read_temp_celsius():return 27-((machine.ADC(4).read_u16()*(3.3/65535))-0.706)/0.001721
def format_ip_for_scrolling(ip_str):
    if ip_str=="NO IP":return list("   NO IP   ")
    p_list,i=[],0
    while i<len(ip_str):
        c=ip_str[i]
        if i+1<len(ip_str)and ip_str[i+1]=='.':p_list.append(c+'.');i+=2
        else:p_list.append(c);i+=1
    return([' ']*3)+p_list+([' ']*3)

# --- 5. MAIN PROGRAM ---
print("--- Pico W 7-Segment Clock ---")
machine.mem32[GPIO_OUT_CLR]=ALL_ANODES_MASK|CA_M|DA_M
machine.mem32[GPIO_OUT_SET]=ALL_SEGMENTS_MASK|CC_M|DC_M
state='STARTUP_SCROLL';disp_buf=[' ']*4;wlan=None;ip="NO IP"
scroll_msg=STARTUP_MESSAGE;scroll_idx=0;last_scroll_ms=0
last_data_ms=0;colon,degree=False,False;tt_mode='time';last_mode_sw_ms=0
btn_state=0;last_manual_ms=0;manual_idx=0
print(f"Initial state: {state}")

while True:
    for i in range(4):
        machine.mem32[GPIO_OUT_CLR]=ALL_ANODES_MASK;c=disp_buf[i].upper()
        if c in SEGMENT_MAP:machine.mem32[GPIO_OUT_SET]=SEG_OFF[c];machine.mem32[GPIO_OUT_CLR]=SEG_ON[c]
        else:machine.mem32[GPIO_OUT_SET]=ALL_SEGMENTS_MASK
        machine.mem32[GPIO_OUT_SET]=ANODE_MASKS[i]
        if i==0:
            if colon:machine.mem32[GPIO_OUT_SET]=CA_M;machine.mem32[GPIO_OUT_CLR]=CC_M
            else:machine.mem32[GPIO_OUT_CLR]=CA_M
            if degree:machine.mem32[GPIO_OUT_SET]=DA_M;machine.mem32[GPIO_OUT_CLR]=DC_M
            else:machine.mem32[GPIO_OUT_CLR]=DA_M
        utime.sleep_us(REFRESH_DELAY_US)
    
    now=utime.ticks_ms();cur_btn=rp2.bootsel_button()
    if cur_btn==1 and btn_state==0:
        utime.sleep_ms(50)
        if rp2.bootsel_button()==1:
            print("BOOTSEL");last_manual_ms=now
            if state in ('MANUAL_MODE','MANUAL_IP_SCROLL'):
                manual_idx=(manual_idx+1)%3
                if manual_idx==2:
                    state='MANUAL_IP_SCROLL';scroll_msg=format_ip_for_scrolling(ip);scroll_idx=0
                else:state='MANUAL_MODE'
            else:state='MANUAL_MODE';manual_idx=0
            print(f"IDX:{manual_idx} STATE:{state}")
    btn_state=cur_btn
    
    if state=='STARTUP_SCROLL':
        colon,degree=False,False
        if utime.ticks_diff(now,last_scroll_ms)>SCROLL_DELAY_MS:
            last_scroll_ms=now;disp_buf=list(scroll_msg[scroll_idx:scroll_idx+4]);scroll_idx+=1
            if scroll_idx>len(scroll_msg)-4:state='CONNECTING_WIFI';print(f"STATE:{state}")
    elif state=='CONNECTING_WIFI':
        disp_buf=['C','O','N','N'];wlan=connect_to_wifi()
        if wlan:sync_time();ip=wlan.ifconfig()[0];scroll_msg=format_ip_for_scrolling(ip);scroll_idx=0;state='SHOWING_IP'
        else:scroll_msg=WIFI_FAIL_MESSAGE;scroll_idx=0;state='WIFI_FAIL'
        print(f"STATE:{state}")
    elif state in ('SHOWING_IP','WIFI_FAIL'):
        colon,degree=False,False
        if utime.ticks_diff(now,last_scroll_ms)>SCROLL_DELAY_MS:
            last_scroll_ms=now;disp_buf=list(scroll_msg[scroll_idx:scroll_idx+4]);scroll_idx+=1
            if scroll_idx>len(scroll_msg)-4:state='NORMAL_CYCLE';print(f"STATE:{state}")
    elif state=='NORMAL_CYCLE':
        dur=10 if tt_mode=='time' else 5
        if utime.ticks_diff(now,last_mode_sw_ms)>dur*1000:
            last_mode_sw_ms=now;tt_mode='temp' if tt_mode=='time' else 'time'
        if utime.ticks_diff(now,last_data_ms)>=1000:
            last_data_ms=now
            if tt_mode=='time':
                tm=utime.localtime();colon=not colon;degree=False
                disp_buf=[str(tm[3]//10),str(tm[3]%10),str(tm[4]//10),str(tm[4]%10)]
            else:
                t=read_temp_celsius();colon=False;degree=True
                u,d=int(abs(t)%10),int((abs(t)*10)%10)
                disp_buf=[str(int(abs(t)/10))if abs(t)>=10 else('-'if t<0 else' '),str(u)+'.',str(d),'C']
    elif state=='MANUAL_MODE':
        if utime.ticks_diff(now,last_manual_ms)>MANUAL_MODE_TIMEOUT_S*1000:
            state='NORMAL_CYCLE';print(f"Timeout->STATE:{state}");continue
        if manual_idx==0:
            tm=utime.localtime();colon=True;degree=False
            disp_buf=[str(tm[3]//10),str(tm[3]%10),str(tm[4]//10),str(tm[4]%10)]
        elif manual_idx==1:
            t=read_temp_celsius();colon=False;degree=True
            u,d=int(abs(t)%10),int((abs(t)*10)%10)
            disp_buf=[str(int(abs(t)/10))if abs(t)>=10 else('-'if t<0 else' '),str(u)+'.',str(d),'C']
    elif state=='MANUAL_IP_SCROLL':
        colon,degree=False,False
        if utime.ticks_diff(now,last_manual_ms)>MANUAL_MODE_TIMEOUT_S*1000:
            state='NORMAL_CYCLE';print(f"Timeout->STATE:{state}");continue
        if utime.ticks_diff(now,last_scroll_ms)>SCROLL_DELAY_MS:
            last_scroll_ms=now;disp_buf=scroll_msg[scroll_idx:scroll_idx+4];scroll_idx+=1
            if scroll_idx>len(scroll_msg)-4:scroll_idx=0