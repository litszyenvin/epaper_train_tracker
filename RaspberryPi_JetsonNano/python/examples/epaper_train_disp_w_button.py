#!/usr/bin/python
# -*- coding:utf-8 -*-

import sys
import os
import json
import time
import hashlib
import subprocess
import requests
import logging
from time import sleep
from datetime import datetime, timedelta
from threading import Timer, Lock

from gpiozero import Button
from PIL import Image, ImageDraw, ImageFont

from train_tracker import (
    collect_train_data,
    calculate_elapsed_minutes,
    is_later_than_current_time,
)

# ----------------------------
# Paths & fonts
# ----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
picdir = os.path.join(BASE_DIR, "pic")
libdir = os.path.join(BASE_DIR, "lib")
if os.path.exists(libdir):
    sys.path.append(libdir)

from waveshare_epd import epd2in7_V2  # requires Waveshare lib installed

# ----------------------------
# Config (tweak as you like)
# ----------------------------
# Default periodic refresh when active
INTERVAL_SECONDS_DEFAULT = 300  # 5 min

# Faster during the key morning window
INTERVAL_SECONDS_MORNING = 120  # 2 min

# Sleep window: pause auto refresh, show sleeping msg
SLEEP_START_HM = (21, 0)  # 21:00
SLEEP_END_HM = (5, 0)     # 05:00 (next day)

# Morning behavior (local time on the Pi)
MORNING_WINDOW_START_HM = (7, 0)   # 07:00
MORNING_WINDOW_END_HM   = (8, 45)  # 08:45
TARGET_DEPART_START_HM  = (7, 45)  # 07:45
TARGET_DEPART_END_HM    = (8, 45)  # 08:45
FAST_MAX_MINUTES = 30
MORNING_FETCH_COUNT = 20  # fetch more so we can filter properly

# Manual wake display duration during sleep window
MANUAL_DISPLAY_SECONDS = 15 * 60  # 15 minutes

# Full clear cadence to reduce ghosting (1 full clear every N updates)
FULL_REFRESH_EVERY = 12

# Trains to show on screen
NUMBER_OF_TRAINS = 4

# RTT settings
url_head = "https://api.rtt.io/api/v1/json/search/"
ORIGIN = "SAC"
DESTINATION = "ZFD"
username = "rttapi_litszyenvin"  # consider env vars
password = "bec5d38d598f2a3518962fedf8345569696cb0bf"  # consider env vars

# ----------------------------
# Buttons (Waveshare 4-key HAT: KEY0..KEY3)
# ----------------------------
BUTTON_PINS = [5, 6, 13, 19]  # BCM numbering
buttons = [Button(p, pull_up=True, bounce_time=0.3) for p in BUTTON_PINS]

# ----------------------------
# Globals
# ----------------------------
epd = epd2in7_V2.EPD()
font14 = ImageFont.truetype(os.path.join(picdir, "Roboto-Regular.ttf"), 14)
font16 = ImageFont.truetype(os.path.join(picdir, "Roboto-Bold.ttf"), 16)
font18 = ImageFont.truetype(os.path.join(picdir, "Roboto-Bold.ttf"), 18)
font20 = ImageFont.truetype(os.path.join(picdir, "Roboto-Bold.ttf"), 20)

_refresh_lock = Lock()
_manual_sleep_timer = None  # revert timer after manual wake
_last_frame_hash = None
_refresh_count = 0

# ----------------------------
# Time helpers
# ----------------------------
def _hm_to_minutes(h, m):
    return h * 60 + m

def _now_minutes():
    now = datetime.now()
    return now.hour * 60 + now.minute

def _hhmm_to_minutes(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[2:])

def _seconds_until(hm):
    h, m = hm
    now = datetime.now()
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()

def _is_between(now_min, start_hm, end_hm):
    start = _hm_to_minutes(*start_hm)
    end = _hm_to_minutes(*end_hm)
    return start <= now_min <= end

def _is_between_wrapped(now_min, start_hm, end_hm):
    """Handles windows that cross midnight (e.g., 15:00–06:00)."""
    start = _hm_to_minutes(*start_hm)
    end = _hm_to_minutes(*end_hm)
    if start <= end:
        return start <= now_min < end
    else:
        return now_min >= start or now_min < end

def _is_sleep_window():
    return _is_between_wrapped(_now_minutes(), SLEEP_START_HM, SLEEP_END_HM)

def _is_morning_window():
    return _is_between(_now_minutes(), MORNING_WINDOW_START_HM, MORNING_WINDOW_END_HM)

def _is_in_target_departure_window(dep_hhmm):
    dep_min = _hhmm_to_minutes(dep_hhmm)
    return (
        _hm_to_minutes(*TARGET_DEPART_START_HM)
        <= dep_min
        <= _hm_to_minutes(*TARGET_DEPART_END_HM)
    )

def _next_interval_seconds():
    """Use faster cadence in morning window, otherwise default."""
    return INTERVAL_SECONDS_MORNING if _is_morning_window() else INTERVAL_SECONDS_DEFAULT

# ----------------------------
# Wi-Fi helpers (toggle radio)
# ----------------------------
def wifi_on():
    try:
        subprocess.run(["rfkill", "unblock", "wifi"], check=False)
        subprocess.run(["ip", "link", "set", "wlan0", "up"], check=False)
        # Wait briefly for link/DHCP
        for _ in range(10):
            try:
                requests.get("https://api.rtt.io", timeout=2)
                return
            except Exception:
                time.sleep(1)
    except Exception as e:
        print(f"wifi_on error: {e}")

def wifi_off():
    try:
        subprocess.run(["ip", "link", "set", "wlan0", "down"], check=False)
        subprocess.run(["rfkill", "block", "wifi"], check=False)
    except Exception as e:
        print(f"wifi_off error: {e}")

# ----------------------------
# Frame display helpers
# ----------------------------
def _buffer_bytes(buf):
    """Normalize epd.getbuffer result to bytes for hashing."""
    try:
        return bytes(buf)
    except Exception:
        # Some drivers already return bytes/bytearray
        return buf if isinstance(buf, (bytes, bytearray)) else bytes(bytearray(buf))

def _prepare_image(image):
    """Rotate the frame 180° to match the panel orientation."""
    try:
        return image.rotate(180)
    except Exception:
        return image

def _maybe_display(Himage):
    """Skip refresh if identical to last frame."""
    global _last_frame_hash, _refresh_count
    epd.init_Fast()
    # Occasional full clear to limit ghosting
    if _refresh_count % FULL_REFRESH_EVERY == 0:
        try:
            epd.Clear()
        except Exception:
            pass

    prepared = _prepare_image(Himage)
    buf = epd.getbuffer(prepared)
    h = hashlib.md5(_buffer_bytes(buf)).hexdigest()
    if h == _last_frame_hash:
        # No visual change; avoid refresh
        epd.init()
        epd.sleep()
        return False

    epd.display_Base(buf)
    _last_frame_hash = h
    _refresh_count += 1
    epd.init()
    epd.sleep()
    return True

def _draw_sleeping_screen():
    """Show 'I'm sleeping...' and put panel to sleep."""
    try:
        epd.init_Fast()
        Himage = Image.new("1", (epd.height, epd.width), 255)
        draw = ImageDraw.Draw(Himage)
        draw.text((30, 60), "I'm sleeping...", font=font20, fill=0)
        draw.text((30, 90), "maybe you should too...", font=font20, fill=0)
        draw.text((30, 120), "(press any button to refresh)", font=font14, fill=0)
        prepared = _prepare_image(Himage)
        epd.display_Base(epd.getbuffer(prepared))
    except Exception as e:
        print(f"Failed to draw sleeping screen: {e}")
    finally:
        try:
            epd.init()
            epd.sleep()
        except Exception:
            pass

def _schedule_manual_sleep_revert():
    """After manual wake during sleep window, revert to sleeping screen."""
    global _manual_sleep_timer
    if _manual_sleep_timer and _manual_sleep_timer.is_alive():
        _manual_sleep_timer.cancel()
    _manual_sleep_timer = Timer(MANUAL_DISPLAY_SECONDS, _sleeping_revert_callback)
    _manual_sleep_timer.start()

def _sleeping_revert_callback():
    _draw_sleeping_screen()

# ----------------------------
# Data filtering (morning fast-train mode)
# ----------------------------
def _apply_morning_filter(train_list):
    """Keep trains with journey < FAST_MAX_MINUTES and departure in 07:45–08:45."""
    filtered = []
    for t in train_list:
        dep = t.get("departure_time")
        jl = t.get("journey_length")
        if not dep or not isinstance(dep, str) or len(dep) < 4:
            continue
        try:
            if jl is not None and int(jl) < FAST_MAX_MINUTES and _is_in_target_departure_window(dep):
                filtered.append(t)
        except Exception:
            continue
    return filtered

# ----------------------------
# Main fetch + render
# ----------------------------
def disp_train_info():
    """One-shot fetch + render; panel always sleeps at end (ePaper retains image)."""
    try:
        now = datetime.now()
        formatted_datetime = now.strftime("%Y/%m/%d/%H%M")
        url = f"{url_head}{ORIGIN}/to/{DESTINATION}/{formatted_datetime}"

        # Fetch more during morning window so we can subset to 07:45–08:45
        fetch_count = MORNING_FETCH_COUNT if _is_morning_window() else NUMBER_OF_TRAINS
        trains = collect_train_data(fetch_count, url, username, password)

        # Morning filter
        if _is_morning_window():
            target = _apply_morning_filter(trains)
            if not target:
                target = trains[:NUMBER_OF_TRAINS]
            else:
                target = target[:NUMBER_OF_TRAINS]
        else:
            target = trains[:NUMBER_OF_TRAINS]

        # Build frame
        Himage = Image.new("1", (epd.height, epd.width), 255)
        draw = ImageDraw.Draw(Himage)

        if not target:
            draw.text((5, 0), "Could not retrieve train information...", font=font14, fill=0)
        else:
            y = 0
            for t in target:
                platform = t.get("departure_platform", "?")
                destination = t.get("destination", "?")
                dep = t.get("departure_time", "????")
                arr = t.get("arrival_time", "????")
                journey = t.get("journey_length", "?")
                status = t.get("departure_status", "?")

                line1 = f"{dep} -> {arr}   [{journey} min]   Plat {platform}"
                line2 = f"{destination} [{status}]"

                draw.text((5, y), line1, font=font16, fill=0)
                draw.text((5, y + 20), line2, font=font14, fill=0)
                y += 40

        draw.text((5, 160), "updated:" + formatted_datetime, font=font14, fill=0)

        # Display (skips if unchanged)
        _maybe_display(Himage)

    except Exception as e:
        logging.info(f"disp_train_info error: {e}")

# ----------------------------
# Scheduler + buttons
# ----------------------------
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
    print(f"Button on GPIO{pin} pressed")
    if _is_sleep_window():
        # Manual wake: fetch, display, then revert after 15 min
        _safe_refresh(trigger=f"button{pin}")
        _schedule_manual_sleep_revert()
    else:
        _safe_refresh(trigger=f"button{pin}")

def run_loop():
    """Main repeating scheduler with sleep-window gating and dynamic intervals."""
    if _is_sleep_window():
        print("Sleep window (21:00–05:00): showing sleeping screen and pausing auto refresh.")
        _draw_sleeping_screen()
        # Schedule a wake-up at SLEEP_END_HM
        Timer(_seconds_until(SLEEP_END_HM), run_loop).start()
        return

    # Active window: perform scheduled refreshes while awake.
    _safe_refresh(trigger="timer")

    # Schedule next run with dynamic interval
    Timer(_next_interval_seconds(), run_loop).start()

def setup_button_callbacks():
    for b in buttons:
        # Capture each pin in a closure
        b.when_pressed = (lambda pin=b.pin.number: (lambda: _button_pressed_cb(pin)))()

def cleanup_buttons():
    for b in buttons:
        try:
            b.close()
        except Exception:
            pass

def initialising_disp():
    try:
        epd.init_Fast()
        Himage = Image.new("1", (epd.height, epd.width), 255)
        draw = ImageDraw.Draw(Himage)
        draw.text((40, 60), "initialising...", font=font20, fill=0)
        prepared = _prepare_image(Himage)
        epd.display_Base(epd.getbuffer(prepared))
    except Exception as e:
        print(f"initialising_disp error: {e}")
    finally:
        try:
            epd.init()
            epd.sleep()
        except Exception:
            pass

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    setup_button_callbacks()
    initialising_disp()
    run_loop()
    try:
        while True:
            sleep(5)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        cleanup_buttons()
