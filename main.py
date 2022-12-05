import socket
from random import random, randint, choice

import plasma
import network
from plasma import plasma2040
import time
import _thread
from credentials import WIFI_SSID, WIFI_PASSWORD

# Set how many LEDs you have
NUM_LEDS = 96

# The speed that the LEDs will start cycling at
DEFAULT_SPEED = 10

# How many times the LEDs will be updated per second
UPDATES = 30

# Chances of a new runner being added each update
# Higher means fewer runners
RUNNER_CHANCE = 250


def connect_to_wifi():
    ip = None
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    # Wait for connect or fail
    while True:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        print('waiting for connection...')
        time.sleep(1)
        if wlan.status() != 3:
            print('network connection failed, waiting 5 seconds and trying again')
            time.sleep(5)

    print('connected')
    status = wlan.ifconfig()
    ip = status[0]
    print('ip = ' + status[0])
    return ip


def http_server():
    ip = connect_to_wifi()
    address = (ip, 80)
    connection = socket.socket()
    connection.bind(address)
    connection.listen(1)
    client = None
    global go
    while True:
        try:
            client = connection.accept()[0]
            request = client.recv(1024)
            print("client connected")
            led_on = request.decode().find('/go')
            if led_on > 0:
                go = True
                response = "Thank you for your request"
            else:
                response = f"Please go to http://{ip}/go to start the light show"
            client.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
            client.send(response)
            client.close()
        except OSError as e:
            pass
        finally:
            if client:
                client.close()
            print('connection closed')


class PlasmaLedManager:
    HUE_DETERIORATION = 0.005
    SATURATION_DETERIORATION = 0.04
    BRIGHTNESS_DETERIORATION = 0.01

    DEFAULT_BRIGHTNESS = 0.4
    HSV_COLORS = {
        "red": (0, 1, DEFAULT_BRIGHTNESS),
        "orange": (0.1, 1, DEFAULT_BRIGHTNESS),
        "yellow": (0.2, 1, DEFAULT_BRIGHTNESS),
        "green": (0.3, 1, DEFAULT_BRIGHTNESS),
        "blue": (0.6, 1, DEFAULT_BRIGHTNESS),
        "purple": (0.8, 1, DEFAULT_BRIGHTNESS),
        "pink": (0.9, 1, DEFAULT_BRIGHTNESS),
    }

    def __init__(self, led_count):
        self.led_count = led_count
        self.leds = [[0, 0, 0] for _ in range(led_count)]
        self.led_strip = plasma.WS2812(led_count, 0, 0, plasma2040.DAT, rgbw=False)
        self.led_strip.start()
        self.mean = [0.07, 0.1, 0.0]

    def loop(self):
        self.creep_into_mean()
        for led_number in range(self.led_count):
            self.led_strip.set_hsv(led_number, *self.leds[led_number])

    def set_color(self, led_number, hsv_tuple):
        try:
            self.leds[led_number] = hsv_tuple
        except IndexError:
            # Let's be nice and not crash
            print(f"LED {led_number} is out of range")

    def revert_number_to_mean(self, target, current, step):
        if target < current:
            current -= step
            current = max(current, target)
        elif target > current:
            current += step
            current = min(current, target)
        return current

    def creep_into_mean(self):
        for led in self.leds:
            led[0] = self.revert_number_to_mean(self.mean[0], led[0], self.HUE_DETERIORATION)
            led[1] = self.revert_number_to_mean(self.mean[1], led[1], self.SATURATION_DETERIORATION)
            led[2] = self.revert_number_to_mean(self.mean[2], led[2], self.BRIGHTNESS_DETERIORATION)


class LedRunner:
    def __init__(self, led_manager):
        self.led_manager = led_manager
        self.led_index = 0
        self.color = self.get_random_color()
        self.wait_time = 0
        self.wait_time_max = 500
        self.done = False

    def get_random_color(self):
        color = choice(list(self.led_manager.HSV_COLORS.values()))
        return list(color)

    def step(self):
        self.led_manager.set_color(self.led_index, self.color.copy())
        self.led_index += 1
        if self.led_index >= NUM_LEDS:
            self.done = True


def run_ledrunners():
    plm = PlasmaLedManager(NUM_LEDS)
    ledrunners = [LedRunner(plm)]
    global go

    while True:
        # Update the LEDs
        plm.loop()

        for ledrunner in ledrunners:
            ledrunner.step()
            if ledrunner.done:
                ledrunners.remove(ledrunner)

        # Small chance to add a new runner
        chance = randint(0, RUNNER_CHANCE)
        if go or chance == 0:
            ledrunners.append(LedRunner(plm))
            go = False

        # Wait for the next update
        time.sleep(1.0 / UPDATES)


go = True
ledrunners_thread = _thread.start_new_thread(run_ledrunners, ())
http_server()
