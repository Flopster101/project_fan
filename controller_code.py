import board
import busio
import digitalio
import adafruit_ssd1306
import simpleio
import time
import json
import os
import asyncio
import pulseio
import countio
import adafruit_irremote
from adafruit_debouncer import Debouncer
from adafruit_onewire.bus import OneWireBus
from adafruit_ds18x20 import DS18X20

# Initialize one-wire bus on board pin GP22.
ow_bus = OneWireBus(board.GP22)

# Scan for sensors and grab the first one found.
ds18b20 = DS18X20(ow_bus, ow_bus.scan()[0])

# Define pins
relay_pins = [board.GP18, board.GP17, board.GP16]
aux_pin = board.GP19
display_i2c_pins = {'scl': board.GP21, 'sda': board.GP20}
buttons_pins = [board.GP6, board.GP7, board.GP8, board.GP9]
tsense_pin = board.GP22
beep_pin = board.GP15
ir_pin = board.GP2

# Define default variables
default_vars = {
    "default_current_speed": 1,
    "default_temp_control": True,
    "default_temp_safe_threshold": 60,
    "default_power_state": True,
    "default_beep_en": True,
}

# Define variables
current_speed = None
temp_control = None
temp_safe_threshold = None
power_state = None
beep_en = True
panic_state = False
first_boot = None
init_done = False

# Define current temperature variable and initialize it to 0.
current_temp = 0

# Define speed messages globally
speed_messages = ["Low", "Mid", "High"]

# Initialize relays and buttons
relays = [digitalio.DigitalInOut(pin) for pin in relay_pins]
for relay in relays:
    relay.direction = digitalio.Direction.OUTPUT
    relay.value = True

aux_relay = digitalio.DigitalInOut(aux_pin)
aux_relay.direction = digitalio.Direction.OUTPUT
aux_relay.value = True # Aux relay is off when high.

# Define the pins for the buttons
button_0 = digitalio.DigitalInOut(buttons_pins[0])
button_0.direction = digitalio.Direction.INPUT
button_0.pull = digitalio.Pull.UP

button_1 = digitalio.DigitalInOut(buttons_pins[1])
button_1.direction = digitalio.Direction.INPUT
button_1.pull = digitalio.Pull.UP

button_2 = digitalio.DigitalInOut(buttons_pins[2])
button_2.direction = digitalio.Direction.INPUT
button_2.pull = digitalio.Pull.UP

button_3 = digitalio.DigitalInOut(buttons_pins[3])
button_3.direction = digitalio.Direction.INPUT
button_3.pull = digitalio.Pull.UP
    
# Create Debouncer objects for each button
debouncer_0 = Debouncer(button_0)
debouncer_1 = Debouncer(button_1)
    
credits_pin = board.GP14
credits_button = digitalio.DigitalInOut(credits_pin)
credits_button.direction = digitalio.Direction.INPUT
credits_button.pull = digitalio.Pull.UP

# Initialize display
i2c = busio.I2C(display_i2c_pins['scl'], display_i2c_pins['sda'])
display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)

# Setup IR receiver
pulsein = pulseio.PulseIn(ir_pin, maxlen=120, idle_state=True)
decoder = adafruit_irremote.GenericDecode()

key_codes = {
    "EXIT": {"code": 0xef11a758, "function": lambda: reset()},
    "POWER": {"code": 0xef112fd0, "function": lambda: power_toggle()},
    "ONE": {"code": 0xef117788, "function": lambda: set_speed(1)},
    "TWO": {"code": 0xef11b748, "function": lambda: set_speed(2)},
    "THREE": {"code": 0xef1137c8, "function": lambda: set_speed(3)},
    "ZERO": {"code": 0xef11f708, "function": lambda: beep_toggle()},
    "MUTE": {"code": 0xef113bc4, "function": lambda: beep_toggle()},
    "INFO": {"code": 0xef117f80, "function": lambda: credits()},
    "SIGNAL": {"code": 0xef119b64, "function": lambda: tcon_toggle()},
    "UP_ARROW": {"code": 0xef115fa0, "function": lambda: increment_speed()},
    "DOWN_ARROW": {"code": 0xef119f60, "function": lambda: decrement_speed()},
    "LEFT_ARROW": {"code": 0xef111fe0, "function": lambda: decrement_speed()},
    "RIGHT_ARROW": {"code": 0xef11ef10, "function": lambda: increment_speed()}
}

def receive_decode_ir():
    pulses = decoder.read_pulses(pulsein)
    try:
        # Attempt to convert received pulses into numbers
        received_code = decoder.decode_bits(pulses)
        # Now we will convert it into NEC hex code
        if len(received_code) > 3:
            hex_code = (received_code[0]<<24) + (received_code[1]<<16) + (received_code[2]<<8) + received_code[3]
            return hex_code
    except adafruit_irremote.IRNECRepeatException:
        pass
    except adafruit_irremote.IRDecodeException as e:
        pass
        
# Beep function
def beep():
    if beep_en:
        simpleio.tone(beep_pin, 440, duration=0.1)
        
# Function to set a fixed speed to the relays (IR only)
def set_speed(value):
    global current_speed
    print(f"setting speed to {value}")
    current_speed = value
    update_relays()
    update_display()
    beep()
    save_settings()

# Function to increment speed relays
def increment_speed():
    global current_speed
    if current_speed < 3:
        current_speed += 1
        update_relays()
        update_display()
        beep()
        save_settings()
        return True
    return False

# Function to decrement speed relays
def decrement_speed():
    global current_speed
    if current_speed > 1:
        current_speed -= 1
        update_relays()
        update_display()
        beep()
        save_settings()
        return True
    return False

# Function to update they status of the relays after a change
def update_relays():
    if power_state:
        aux_relay.value = True # Turn on aux relay briefly.
        time.sleep(0.05) # Wait for 50ms.
        aux_relay.value = False # Turn off aux relay.
        
        for i in range(3):
            relays[i].value = i != current_speed - 1 # Set relays according to current speed.
    else:
        aux_relay.value = True # Turn off aux relay.
        
        for i in range(3):
            relays[i].value = True # Turn off all speed relays.

def update_display():
    # Clear the display.
    display.fill(0)
    
    # Display messages on the left half of the screen.
    display.text("Speed:" + speed_messages[current_speed - 1], 0, 0, 1)
    display.text("Tcon:" + ("ON" if temp_control else "OFF"), 0, 10, 1)
    
    if panic_state:
        display.text("Temp:" + str(current_temp) + "C !", 0, 20, 1)
    else:
        display.text("Temp:" + str(current_temp) + "C", 0, 20, 1)
    
    # Draw a dividing line.
    display.line(64, 0, 64, display.height - 1, 1)
    
    # Display message on the right half of the screen.
    display.text("Power:" + ("ON" if power_state else "OFF"), 68, 0, 1)
    
    # Display beep status on the right half of the screen.
    display.text("Beep:" + ("ON" if beep_en else "OFF"), 68, 10, 1)
    
    # Update the display.
    display.show()

def config_init():
    global current_speed, temp_control, temp_safe_threshold, power_state, beep_en
    
    try:
        os.remove('settings.json')
    except OSError:
        pass
    
    current_speed = default_vars["default_current_speed"]
    temp_control = default_vars["default_temp_control"]
    temp_safe_threshold = default_vars["default_temp_safe_threshold"]
    power_state = default_vars["default_power_state"]
    beep_en = default_vars["default_beep_en"]
    
    save_settings()

def load_settings():
    global current_speed, temp_control, temp_safe_threshold, power_state, beep_en
    
    with open('settings.json', 'r') as f:
        settings_data = json.load(f)
        
        current_speed = settings_data["current_speed"]
        temp_control = settings_data["temp_control"]
        temp_safe_threshold = settings_data["temp_safe_threshold"]
        power_state = settings_data["power_state"]
        beep_en = settings_data["beep_en"]

def save_settings():
    settings_data = {
        "current_speed": current_speed,
        "temp_control": temp_control,
        "temp_safe_threshold": temp_safe_threshold,
        "power_state": power_state,
        "beep_en": beep_en,
    }
    
    with open('settings.json', 'w') as f:
        json.dump(settings_data, f)

def panic_temp():
    global power_state
    power_state = False
    update_relays()
    update_display()

async def update_temp():
    global current_temp
    global panic_state
    current_temp = int(ds18b20.temperature)
    
    if init_done:
        # Clear the line that shows the temperature value.
        display.fill_rect(0, 20, 50, 8, 0)
        
        if panic_state:
            display.text("Temp:" + str(current_temp) + "C !", 0, 20, 1)
        else:
            display.text("Temp:" + str(current_temp) + "C", 0, 20, 1)
        
        # Update the display.
        display.show()
    
    if current_temp > temp_safe_threshold:
        panic_state = True
        
        if temp_control:
            panic_temp()

# Credits easter egg
def credits():
    display.fill(0)
    display.text("Fan Control Module v1.0", 0, 0, 1)
    display.text("Nahuel Gomez", 0, 10, 1)
    display.text("2023 - Flopster101", 0, 20, 1)
    display.show()
    time.sleep(3)
    update_display()

# Enable/disable beeper
def beep_toggle():
    global beep_en
    beep_en = not beep_en
    print(f"beep status set to {beep_en}")
    update_display()
    save_settings()
    
# Toggle power state
def power_toggle():
    global power_state
    power_state = not power_state
    beep()
    print(f"power status set to {power_state}")
    update_display()
    update_relays()
    save_settings()

# Toggle temperature control
def tcon_toggle():
    global temp_control
    temp_control = not temp_control
    beep()
    print(f"temp control status set to {temp_control}")
    update_display()
    save_settings()
    
# Reset device and configuration
def reset():
    global init_done
    global first_boot
    print("Resetting...")
    display.fill(0)
    display.text("Resetting...", 0, 0, 1)
    display.show()
    beep()
    first_boot = True
    init_done = False
    init_controller()

# Initialization routine
def init_controller():
    global init_done, first_boot

    if not credits_button.value: # If button GP14 is grounded.
        credits()
    
    if not init_done:
        if first_boot:
            config_init()
        
        load_settings()
        
        beep()
        
        # Display initialization message.
        display.fill(0)
        display.text("Initializing...", 0, 0, 1)
        display.show()
        
        time.sleep(0.3)
        
        update_display()
        update_relays()
        
        init_done = True
        print("Controller initialized")

        # Start main loop
        main()

def main():
    global temp_control
    button3_press_time = 0
    button2_press_time = 0
    last_temp_update = time.monotonic()

    while True:
        current_time = time.monotonic()
        last_num_pulses = len(pulsein)
        
        ## Speed control buttons
        # Update the state of the speed change buttons
        debouncer_0.update()
        debouncer_1.update()
        
        # And check if any of those buttons is pressed to perform the corresponding action.
        
        ## Button 0 (speed decrease)
        if debouncer_0.fell:
            decrement_speed()
            print("gp6 press")
            time.sleep(0.05)
            
        ## Button 1  (speed increase)
        if debouncer_1.fell:
            increment_speed()
            print("gp7 press")
            time.sleep(0.05)
            
        ## Button 2 (reset/tcon toggle)
        if not button_2.value:  # Button is pressed
            print("gp8 press")
            if button2_press_time == 0:
                button2_press_time = time.monotonic()
            elif time.monotonic() - button2_press_time > 1:  # Button held for > 1 second
                tcon_toggle()
                button2_press_time = 0
                while not button_2.value:
                    pass
                time.sleep(0.1)
        else:  # Button is not pressed
            if button2_press_time != 0:
                reset()
                button2_press_time = 0
            
        ## Button 3 (power/beep toggle)
        if not button_3.value:  # Button is pressed
            print("gp9 press")
            if button3_press_time == 0:
                button3_press_time = time.monotonic()
            elif time.monotonic() - button3_press_time > 1:  # Button held for > 1 second
                beep_toggle()
                button3_press_time = 0
                while not button_3.value:
                    pass
                time.sleep(0.1)
        else:  # Button is not pressed
            if button3_press_time != 0:
                power_toggle()
                button3_press_time = 0
        
        num_pulses = len(pulsein)
        if num_pulses != last_num_pulses:  # Check if there are new pulses
            print("pulse received")
            last_num_pulses = num_pulses
            # Check for received codes.
            hex_code = receive_decode_ir()
        
            if hex_code is not None:
                for key, value in key_codes.items():
                    if hex_code == value["code"]:
                        print(f"Key pressed: {key}")
                        value["function"]()  # Call the associated function

        # Update temperature every second.
        if current_time - last_temp_update > 5:
            print("temp updated")
            asyncio.run(update_temp())
            last_temp_update = current_time

# Check for the existence of settings.json.
try:
    with open('settings.json', 'r') as f:
        first_boot = False
except OSError:
    first_boot = True

# Initialize controller.
init_controller()