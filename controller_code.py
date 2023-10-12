import board
import busio
import digitalio
import adafruit_ssd1306
import simpleio
import time
import json
import os

# Define pins
relay_pins = [board.GP18, board.GP17, board.GP16]
aux_pin = board.GP19
display_i2c_pins = {'scl': board.GP21, 'sda': board.GP20}
buttons_pins = [board.GP6, board.GP7, board.GP8, board.GP9]
tsense_pin = board.GP22
beep_pin = board.GP15

# Define default variables
default_vars = {
    "default_current_speed": 1,
    "default_temp_control": True,
    "default_temp_safe_threshold": 60,
    "default_power_state": True,
}

# Define variables
current_speed = None
temp_control = None
temp_safe_threshold = None
power_state = None
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
aux_relay.value = False # Aux relay is off when high.

buttons = [digitalio.DigitalInOut(pin) for pin in buttons_pins]
for button in buttons:
    button.direction = digitalio.Direction.INPUT
    button.pull = digitalio.Pull.UP

# Initialize display
i2c = busio.I2C(display_i2c_pins['scl'], display_i2c_pins['sda'])
display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)

def beep():
    simpleio.tone(beep_pin, 440, duration=0.1)

def increment_speed():
    global current_speed
    if current_speed < 3:
        current_speed += 1
        update_relays()
        update_display()
        beep()
        time.sleep(0.05)
        save_settings()
        return True
    return False

def decrement_speed():
    global current_speed
    if current_speed > 1:
        current_speed -= 1
        update_relays()
        update_display()
        beep()
        time.sleep(0.05)
        save_settings()
        return True
    return False

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
    display.text("Temp:" + str(current_temp) + "C", 0, 20, 1)
    
    # Draw a dividing line.
    display.line(64, 0, 64, display.height - 1, 1)
    
    # Display message on the right half of the screen.
    display.text("Power:" + ("ON" if power_state else "OFF"), 68, 0, 1)
    
    # Update the display.
    display.show()

def config_init():
    global current_speed, temp_control, temp_safe_threshold, power_state
    
    try:
        os.remove('settings.json')
    except OSError:
        pass
    
    current_speed = default_vars["default_current_speed"]
    temp_control = default_vars["default_temp_control"]
    temp_safe_threshold = default_vars["default_temp_safe_threshold"]
    power_state = default_vars["default_power_state"]
    
    save_settings()

def load_settings():
    global current_speed, temp_control, temp_safe_threshold, power_state
    
    with open('settings.json', 'r') as f:
        settings_data = json.load(f)
        
        current_speed = settings_data["current_speed"]
        temp_control = settings_data["temp_control"]
        temp_safe_threshold = settings_data["temp_safe_threshold"]
        power_state = settings_data["power_state"]

def save_settings():
    settings_data = {
        "current_speed": current_speed,
        "temp_control": temp_control,
        "temp_safe_threshold": temp_safe_threshold,
        "power_state": power_state,
    }
    
    with open('settings.json', 'w') as f:
        json.dump(settings_data, f)

def init_controller():
    global init_done, first_boot
    
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
        
        main()

def main():
    while True:
        if not buttons[0].value: # If button GP6 was pressed.
            decrement_speed()

        if not buttons[1].value: # If button GP7 was pressed.
            increment_speed()

# Check for the existence of settings.json.
try:
    with open('settings.json', 'r') as f:
        first_boot = False
except OSError:
    first_boot = True

# Initialize controller.
init_controller()