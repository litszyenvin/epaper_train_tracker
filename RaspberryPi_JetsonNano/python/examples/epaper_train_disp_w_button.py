#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import requests
import json
from time import sleep
from datetime import datetime, timedelta
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

# ---- CONFIG ----
INTERVAL_SECONDS = 300  # periodic refresh (5 min)

# Morning behavior windows (local time on the Pi)
MORNING_WINDOW_START_HM = (7, 0)    # 07:00
MORNING_WINDOW_END_HM   = (8, 15)   # 08:15
TARGET_DEPART_START_HM  = (7, 45)   # 07:45
TARGET_DEPART_END_HM    = (8, 15)   # 08:15
FAST_MAX_MINUTES = 30
MORNING_FETCH_COUNT = 20  # fetch more so we can filter

# Battery-saving sleep window
SLEEP_START_HM = (15, 0)  # 15:00
SLEEP_END_HM   = (6, 0)   # 06:00 (next day)

# Show info for 15 minutes on manual wake, then revert to sleeping screen
MANUAL_DISPLAY_SECONDS = 15 * 60

# ---- Buttons (Waveshare 4-key HAT: KEY0..KEY3) ----
BUTTON_PINS = [5, 6, 13, 19]  # BCM numbering
buttons = [Button(p, pull_up=True, bounce_time=0.3) for p in BUTTON_PINS]

# Prevent overlapping refreshes
_refresh_lock = Lock()
_manual_sleep_timer = None  # timer that reverts to "I'm sleeping..." after manual wake

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
number_of_trains = 4  # default display count

# ---- time helpers ----
def _hm_to_minutes(h, m): return h * 60 + m
def _now_minutes():
    now = datetime.now()
    return now.hour * 60 + now.minute
def _hhmm_to_minutes(hhmm): return int(hhmm[:2]) * 60 + int(hhmm[2:])

def _is_between(now_min, start_hm, end_hm):
    start = _hm_to_minutes(*start_hm); end = _hm_to_minutes(*end_hm)
    return start <= now_min <= end

def _is_between_wrapped(now_min, start_hm, end_hm):
    start = _hm_to_minutes(*start_hm); end = _hm_to_minutes(*end_hm)
    if start <= end:
        return start <= now_min < end
    else:
        return now_min >= start or now_min < end

def _seconds_until(hm):
    h, m = hm
    now = datetime.now()
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now: target += timedelta(days=1)
    return (target - now).total_seconds()

def _is_morning_window(): return _is_between(_now_minutes(), MORNING_WINDOW_START_HM, MORNING_WINDOW_END_HM)
def _is_sleep_window():   return _is_between_wrapped(_now_minutes(), SLEEP_START_HM, SLEEP_END_HM)

def _is_in_target_departure_window(dep_hhmm):
    dep_min = _hhmm_to_minutes(dep_hhmm)
    return _hm_to_minutes(*TARGET_DEPART_START_HM) <= dep_min <= _hm_to_minutes(*TARGET_DEPART_END_HM)

def _apply_morning_filter(train_list):
    filtered = []
    for t in train_list:
        dep = t.get('departure_time'); jl = t.get('journey_length')
        if not dep or not isinstance(dep, str) or len(dep) < 4: continue
        try:
            if jl is not None and int(jl) < FAST_MAX_MINUTES and _is_in_target_departure_window(dep):
                filtered.append(t)
        except Exception:
            continue
    return filtered

# ---- sleeping screen ----
def _show_sleeping_screen():
    msg = "I'm sleeping..."
    try:
        epd.init_Fast()
        epd.Clear()
        Himage = Image.new('1', (epd.height, epd.width), 255)
        draw = ImageDraw.Draw(Himage)
        # Simple centred-ish placement
        draw.text((30, 60), msg, font=font20, fill=0)
        draw.text((30, 90), "(press any button to refresh)", font=font14, fill=0)
        epd.display_Base(epd.getbuffer(Himage))
        epd.init()
        epd.sleep()
    except Exception as e:
        print(f"Failed to draw sleeping screen: {e}")

def _schedule_manual_sleep_revert():
    global _manual_sleep_timer
    # cancel previous timer if any
    if _manual_sleep_timer and _manual_sleep_timer.is_alive():
        _manual_sleep_timer.cancel()
    _manual_sleep_timer = Timer(MANUAL_DISPLAY_SECONDS, _show_sleeping_screen)
    _manual_sleep_timer.start()

def disp_train_info():
    """One-shot fetch + render + put panel to sleep."""
    try:
        logging.info("starting to pull train info")
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime("%Y/%m/%d/%H%M")
        url = url_head + ORIGIN + '/to/' + DESTINATION + '/' + formatted_datetime

        fetch_count = MORNING_FETCH_COUNT if _is_morning_window() else number_of_trains
        all_trains = collect_train_data(fetch_count, url, username, password)

        if _is_morning_window():
            target_trains = _apply_morning_filter(all_trains)
            if not target_trains:
                target_trains = all_trains[:number_of_trains]
            else:
                target_trains = target_trains[:number_of_trains]
        else:
            target_trains = all_trains[:number_of_trains]

        epd.init_Fast()
        epd.Clear()

        if not target_trains:
            Himage = Image.new('1', (epd.height, epd.width), 255)
            draw = ImageDraw.Draw(Himage)
            draw.text((5, 0), "Could not retrieve train information...", font=font14, fill=0)
            draw.text((5, 160), ('updated:' + formatted_datetime), font=font14, fill=0)
            epd.display_Base(epd.getbuffer(Himage))
        else:
            Himage = Image.new('1', (epd.height, epd.width), 255)
            draw = ImageDraw.Draw(Himage)
            y = 0
            for train in target_trains:
                destination_print = f"To: {train.get('destination','?')},Plat {train.get('departure_platform','?')}"
                train_time_print = (
                    f"{train.get('departure_time','????')}---->"
                    f"{train.get('arrival_time','????')} "
                    f"({train.get('journey_length','?')} min) "
                    f"[{train.get('departure_status','?')}]"
                )
                draw.text((5, y), destination_print, font=font14, fill=0)
                draw.text((5, y + 20), train_time_print, font=font16, fill=0)
                y += 40
            draw.text((5, 160), ('updated:' + formatted_datetime), font=font14, fill=0)
            epd.display_Base(epd.getbuffer(Himage))

        # Always sleep the panel after drawing (ePaper retains image)
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
    # If we're in the sleep window, keep the info visible for 15 minutes,
    # then show "I'm sleeping..." again.
    if _is_sleep_window():
        _schedule_manual_sleep_revert()

def run_disp_train_info():
    # If entering or within the sleep window: show "I'm sleeping..." then keep panel asleep.
    if _is_sleep_window():
        print("Sleep window (15:00–06:00): pausing auto refresh and sleeping panel.")
        _show_sleeping_screen()  # <- draw message before sleep so no stale info lingers
        # Wake scheduler at SLEEP_END_HM to resume normal operation
        Timer(_seconds_until(SLEEP_END_HM), run_disp_train_info).start()
        return

    # Active window: perform one refresh now and schedule the next
    _safe_refresh(trigger="timer")
    Timer(INTERVAL_SECONDS, run_disp_train_info).start()

def setup_button_callbacks():
    for b in buttons:
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
