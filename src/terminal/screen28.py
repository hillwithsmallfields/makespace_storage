"""
Screen setup for https://docs.waveshare.com/ESP32-S3-Touch-LCD-2.8

Based on the screen.py that is part of
https://dfimg.dfrobot.com/62d52567aa9508d63a4247a1/wikien/d030e7e8a8e4ca2488b32541d7e36cce.zip
ESP32-S3(N16R8) Firmware

but with the numbers from a google AI search for "mosi miso waveshare
esp32" followed by "waveshare esp-32s touch lcd 2.8 connect to screen"

That gave me this data (with the usual caveat that AI may get things wrong):

Internal Display & Touch Pinout (Standard 240×320 Model)

Configure your display library (such as TFT_eSPI, LovyanGFX, or Waveshare's demo code) using these internal pin assignments:
• MOSI (Data): GPIO 45
• MISO: Not connected (the display is write-only)
• SCLK (Clock): GPIO 40
• CS (Chip Select): GPIO 42
• DC (Data/Command): GPIO 41
• RST (Reset): GPIO 39
• BL (Backlight): GPIO 5
• Capacitive Touch (I2C): SDA = GPIO 1, SCL = GPIO 3, INT = GPIO 4, RST = GPIO
"""

import lcd_bus
from micropython import const
import machine
import lcd_utils

spi_bus = machine.SPI.Bus(
    host=1,
    mosi=45,
    sck=40)

display_bus = lcd_bus.SPIBus(
    spi_bus = spi_bus,
    freq = 40000000,
    dc=41,
    cs=45,
    )

import st7789
import lvgl as lv
import task_handler

display = st7789.ST7789(
    data_bus = display_bus,
    display_width = 240,
    display_height = 320,
    backlight_pin = 5,
    reset_pin = 39,
    reset_state = st7789.STATE_LOW,
    color_space = lv.COLOR_FORMAT.RGB565,
    color_byte_order = st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap = True,
    )
