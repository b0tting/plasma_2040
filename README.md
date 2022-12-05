### Plasma 2040 ledrunner
This is a small demo for the Plasma 2040 running the raspberry pi Pico 2040 microcontroller.

![Leds](demo.gif) 

- It starts a simple webserver over wifi and when the <ip>/go URL is connected will spawn a new running led. 
- It will also spawn running leds every now and then without the request.

This is in micropython, using the _thread object to keep the webserver up for new requests while handling the running leds in the background.

Components are the Plasma 2040 W and the Pimoroni "RGB LED Strip with Diffuser", which makes an easy no-solder solution. 

### Setup
To set up: 
- Copy the credentials.py.example to credentials.py, set your SSID/credential and upload it to the 2040
- Copy the main.py to the 2040
