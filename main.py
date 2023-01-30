wlan_capable = True
try:
    import socket
    import network
except ImportError:
    wlan_capable = False

from random import random, randint, choice
import plasma
from plasma import plasma2040
import machine
import time
import struct
import _thread
try:
    from settings import *
except ImportError:
    print("Please create a settings.py file with your wifi credentials")
    raise


ntp_success = False


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


def http_server(ip):
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

    def __init__(self, led_count, rgbw=False):
        self.led_count = led_count
        self.leds = [[0, 0, 0] for _ in range(led_count)]
        self.led_strip = plasma.WS2812(led_count, 0, 0, plasma2040.DAT, rgbw=rgbw)
        self.led_strip.start()
        self.mean = [0.07, 0.1, 0.0]

    def loop(self):
        self.creep_into_mean()
        for led_number in range(self.led_count):
            self.led_strip.set_hsv(led_number, *self.leds[led_number])

    def set_color(self, led_number, hsv_tuple):
        try:
            if self.leds[led_number][2] > 0.0:
                hsv_tuple[1] = (hsv_tuple[1] - self.leds[led_number][1])
                hsv_tuple[2] = min((hsv_tuple[2] + self.leds[led_number][2]), self.DEFAULT_BRIGHTNESS)
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

    def black_out(self):
        for led in self.leds:
            led[1] = 0.0
            led[2] = 0.0
        self.loop()


class LedRunner:
    def __init__(self, led_manager, reverse=False):
        self.led_manager = led_manager
        self.color = self.get_random_color()
        self.wait_time = 0
        self.wait_time_max = 500
        self.done = False
        self.forward = not reverse
        self.led_index = 0 if self.forward else NUM_LEDS - 1

    def get_random_color(self):
        color = choice(list(self.led_manager.HSV_COLORS.values()))
        return list(color)

    def step(self):
        self.led_manager.set_color(self.led_index, self.color.copy())
        if self.forward:
            self.led_index += 1
            if self.led_index >= NUM_LEDS:
                self.done = True
        else:
            self.led_index -= 1
            if self.led_index < 0:
                self.done = True


class OpeningHours:
    SLEEP_TIME = 1 * 60 # minutes * seconds
    def __init__(self, open_from, open_until, wlan_capable=True):
        self.wlan_capable = wlan_capable
        self.open_from = open_from
        self.open_until = open_until
        self.rtc = None
        self.am_sleeping = False

    def set_time(self):
        try:
            NTP_QUERY = bytearray(48)
            NTP_QUERY[0] = 0x1B
            addr = socket.getaddrinfo(NTP_HOST, 123)[0][-1]
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.settimeout(3)
                res = s.sendto(NTP_QUERY, addr)
                msg = s.recv(48)
            finally:
                s.close()
            val = struct.unpack("!I", msg[40:44])[0]
            t = val - NTP_DELTA
            tm = time.gmtime(t)
            print(f"Current UTC time: {tm}")
            self.rtc = machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
        except Exception as e:
            print(f"Failed to set time from NTP from {e}, using default")

    def is_open(self):
        if not self.wlan_capable:
            return True
        if not self.rtc:
            now = machine.RTC().datetime()
        else:
            now = self.rtc.datetime()

        hours = now[4]
        is_open = False
        if hours >= START_HOUR_UTC:
            is_open = True
            if START_HOUR_UTC < STOP_HOUR_UTC < hours:
                is_open = False

        if is_open and self.am_sleeping:
            print("Waking up!")
            self.am_sleeping = False
        return is_open

    def sleep(self):
        if not self.am_sleeping:
            self.am_sleeping = True
            print("Going to sleep")
        if DEEP_SLEEP_MODE_ENABLED:
            machine.deepsleep(self.SLEEP_TIME * 1000)
        else:
            time.sleep(self.SLEEP_TIME)

def run_ledrunners():
    plm = PlasmaLedManager(NUM_LEDS, RGWB)
    ledrunners = [LedRunner(plm), LedRunner(plm, reverse=True)]
    global first_run

    while True:
        if oh.is_open():
            # Update the LEDs
            plm.loop()

            for ledrunner in ledrunners:
                ledrunner.step()
                if ledrunner.done:
                    ledrunners.remove(ledrunner)

            # Small chance to add a new runner
            chance = randint(0, RUNNER_CHANCE)
            if first_run or chance == 0:
                reverse = REVERSIBLE and randint(0, 1) == 0
                ledrunners.append(LedRunner(plm, reverse))
                first_run = False

            # Wait for the next update
            time.sleep(1.0 / UPDATES)
        else:
            plm.black_out()
            oh.sleep()

first_run = True
oh = OpeningHours(START_HOUR_UTC, STOP_HOUR_UTC, wlan_capable)
ledrunners_thread = _thread.start_new_thread(run_ledrunners, ())

# Networky stuff
if wlan_capable:
    ip = connect_to_wifi()
    oh.set_time()
    http_server(ip)
