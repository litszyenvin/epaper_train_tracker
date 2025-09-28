#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import requests
import json
from time import sleep
from datetime import datetime
from gpiozero import Button
from threading import Timer, Lock
from train_tracker import collect_train_data, calculate_elapsed_minutes, is_later_than_current_time

picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

import logging
from waveshare_epd import epd2in7_V2
from PIL import Image, ImageDraw, ImageFont
import traceback

# logging.basicConfig(level=logging.DEBUG)

INTERVAL_SECONDS = 300  # periodic refresh (5 min)

# ---- Buttons (Waveshare 4-key HAT: KEY0..KEY3) ----
BUTTON_PINS = [5, 6, 13, 19]  # BCM numbering
buttons = [Button(p, pull_up=True, bounce_time=0.3) for p in BUTTON_PINS]

# Prevent overlapping refreshes
_refresh_lock = Lock()

epd = epd2in7_V2.EPD()
font14 = ImageFont.truetype(os.path.join(picdir, 'Roboto-Regular.ttf'), 14)
font16 = ImageFont.truetype(os.path.join(picdir, 'Roboto-Bold.ttf'), 16)
font18 = ImageFont.truetype(os.path.join(picdir, 'Roboto-Bold.ttf'), 18)
font20 = ImageFont.truetype(os.path.join(picdir, 'Roboto-Bold.ttf'), 20)
url_head = "https://api.rtt.io/api/v1/json/search/"
ORIGIN = 'SAC'
DESTINATION = 'ZFD'
username = "rttapi_litszyenvin"
password = "bec5d38d598f2a3518962fedf8345569696cb0bf"
number_of_trains = 4

def disp_train_info():
    """One-shot fetch + render + put panel to sleep."""
    try:
        logging.info("starting to pull train info")
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime("%Y/%m/%d/%H%M")
        url = url_head + ORIGIN + '/to/' + DESTINATION + '/' + formatted_datetime

        train_data = collect_train_data(number_of_trains, url, username, password)

        epd.init_Fast()
        epd.Clear()

        if len(train_data) == 0:
            Himage = Image.new('1', (epd.height, epd.width), 255)
            draw = ImageDraw.Draw(Himage)
            draw.text((5, 0), "Could not retrive train information...", font=font14, fill=0)
            draw.text((5, 160), ('updated:' + formatted_datetime), font=font14, fill=0)
            epd.display_Base(epd.getbuffer(Himage))
        else:
            destination_text = []
            train_time_text = []
            for train in train_data:
                destination_text.append(f"To: {train['destination']},Plat {train['departure_platform']}")
                train_time_text.append(f"{train['departure_time']}---->{train['arrival_time']} ({train['journey_length']} min) [{train['departure_status']}]")

            Himage = Image.new('1', (epd.height, epd.width), 255)
            draw = ImageDraw.Draw(Himage)
            y = 0
            for destination_print, train_time_print in zip(destination_text, train_time_text):
                draw.text((5, y), destination_print, font=font14, fill=0)
                draw.text((5, y + 20), train_time_print, font=font16, fill=0)
                y += 40
            draw.text((5, 160), ('updated:' + formatted_datetime), font=font14, fill=0)
            epd.display_Base(epd.getbuffer(Himage))

        epd.init()
        epd.sleep()

    except IOError as e:
        logging.info(e)
    except KeyboardInterrupt:
        logging.info("ctrl + c:")
        epd2in7_V2.epdconfig.module_exit(cleanup=True)
        exit()

def initialising_disp():
    try:
        epd.init_Fast()
        epd.Clear()
        Himage = Image.new('1', (epd.height, epd.width), 255)
        draw = ImageDraw.Draw(Himage)
        draw.text((50, 50), 'initialising...', font=font20, fill=0)
        epd.display_Base(epd.getbuffer(Himage))
        sleep(2)
        epd.init()
        epd.sleep()
    except IOError as e:
        logging.info(e)
    except KeyboardInterrupt:
        logging.info("ctrl + c:")
        epd2in7_V2.epdconfig.module_exit(cleanup=True)
        exit()

# ---- Manual + periodic refresh machinery ----
def _safe_refresh(trigger="timer"):
    """Run disp_train_info() if not already running."""
    if _refresh_lock.acquire(blocking=False):
        try:
            print(f"Refreshing ({trigger})...")
            disp_train_info()
        finally:
            _refresh_lock.release()
    else:
        print(f"Skip refresh ({trigger}): another update is in progress")

def _button_pressed_cb(pin):
    print(f"Button on GPIO{pin} pressed -> manual refresh requested")
    _safe_refresh(trigger=f"button{pin}")

def run_disp_train_info():
    # schedule the next periodic refresh and run one now
    _safe_refresh(trigger="timer")
    Timer(INTERVAL_SECONDS, run_disp_train_info).start()

def setup_button_callbacks():
    for b in buttons:
        # Use a closure to capture the pin number
        b.when_pressed = (lambda pin=b.pin.number: (lambda: _button_pressed_cb(pin)))()

def cleanup_buttons():
    for b in buttons:
        try:
            b.close()
        except Exception:
            pass

if __name__ == "__main__":
    setup_button_callbacks()
    initialising_disp()
    run_disp_train_info()
    try:
        while True:
            sleep(5)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        cleanup_buttons()
