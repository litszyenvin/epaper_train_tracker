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
import typing
from time import sleep
from datetime import datetime, timedelta
from threading import Timer, Lock

try:
    from gpiozero import Button
except Exception:
    # gpiozero not available (development machine). We'll still define Button
    # name so later code can instantiate dummy placeholders.
    class _DummyButtonClass:
        def __init__(self, *a, **k):
            pass

    Button = _DummyButtonClass
from PIL import Image, ImageDraw, ImageFont

from train_tracker import (
    collect_train_data,
    calculate_elapsed_minutes,
    is_later_than_current_time,
)

# ----------------------------
# Paths & fonts
# ----------------------------
# Keep BASE_DIR local to this script folder (we put app files under epaper_app/)
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
picdir = os.path.join(BASE_DIR, "pic")
libdir = os.path.join(BASE_DIR, "lib")
if os.path.exists(libdir):
    sys.path.append(libdir)

from waveshare_epd import epd2in7_V2  # local stub package in epaper_app/waveshare_epd

# ----------------------------
# Config (tweak as you like)
# ----------------------------
INTERVAL_SECONDS_DEFAULT = 300  # 5 min
INTERVAL_SECONDS_MORNING = 120  # 2 min
SLEEP_START_HM = (21, 0)
SLEEP_END_HM = (5, 0)
MORNING_WINDOW_START_HM = (7, 0)
MORNING_WINDOW_END_HM = (8, 45)
TARGET_DEPART_START_HM = (7, 45)
TARGET_DEPART_END_HM = (8, 45)
FAST_MAX_MINUTES = 30
MORNING_FETCH_COUNT = 20
MANUAL_DISPLAY_SECONDS = 15 * 60
FULL_REFRESH_EVERY = 12
NUMBER_OF_TRAINS = 4
url_head = "https://api.rtt.io/api/v1/json/search/"
ORIGIN = "SAC"
DESTINATION = "ZFD"
username = "rttapi_litszyenvin"
password = ""  # prefer using config or env var


def _load_toml_config(config_path: str) -> dict:
    try:
        try:
            import tomllib as _toml
        except Exception:
            import toml as _toml

        if hasattr(_toml, "loads") and hasattr(_toml, "load"):
            try:
                with open(config_path, "rb") as f:
                    return _toml.load(f)
            except Exception:
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        return _toml.load(f)
                except Exception:
                    return {}
        else:
            return {}
    except Exception as e:
        logging.info(f"TOML loader not available or failed to read {config_path}: {e}")
        return {}


# Look for config.toml next to this file, then fall back to repo root
_example_cfg_path = os.path.join(os.path.dirname(__file__), "config.toml")
if not os.path.exists(_example_cfg_path):
    # parent of this directory is repo root (we expect config.toml at repo root)
    candidate = os.path.join(os.path.dirname(__file__), os.pardir, "config.toml")
    candidate = os.path.abspath(candidate)
    if os.path.exists(candidate):
        _example_cfg_path = candidate

_cfg = _load_toml_config(_example_cfg_path) if os.path.exists(_example_cfg_path) else {}


def _cfg_get(key, default=None):
    return _cfg.get(key, default)


def _cfg_get_hm(key, default):
    v = _cfg.get(key)
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        try:
            return (int(v[0]), int(v[1]))
        except Exception:
            return default
    return default


INTERVAL_SECONDS_DEFAULT = int(_cfg_get("INTERVAL_SECONDS_DEFAULT", INTERVAL_SECONDS_DEFAULT))
INTERVAL_SECONDS_MORNING = int(_cfg_get("INTERVAL_SECONDS_MORNING", INTERVAL_SECONDS_MORNING))
SLEEP_START_HM = _cfg_get_hm("SLEEP_START_HM", SLEEP_START_HM)
SLEEP_END_HM = _cfg_get_hm("SLEEP_END_HM", SLEEP_END_HM)
MORNING_WINDOW_START_HM = _cfg_get_hm("MORNING_WINDOW_START_HM", MORNING_WINDOW_START_HM)
MORNING_WINDOW_END_HM = _cfg_get_hm("MORNING_WINDOW_END_HM", MORNING_WINDOW_END_HM)
TARGET_DEPART_START_HM = _cfg_get_hm("TARGET_DEPART_START_HM", TARGET_DEPART_START_HM)
TARGET_DEPART_END_HM = _cfg_get_hm("TARGET_DEPART_END_HM", TARGET_DEPART_END_HM)
FAST_MAX_MINUTES = int(_cfg_get("FAST_MAX_MINUTES", FAST_MAX_MINUTES))
MORNING_FETCH_COUNT = int(_cfg_get("MORNING_FETCH_COUNT", MORNING_FETCH_COUNT))
MANUAL_DISPLAY_SECONDS = int(_cfg_get("MANUAL_DISPLAY_SECONDS", MANUAL_DISPLAY_SECONDS))
FULL_REFRESH_EVERY = int(_cfg_get("FULL_REFRESH_EVERY", FULL_REFRESH_EVERY))
NUMBER_OF_TRAINS = int(_cfg_get("NUMBER_OF_TRAINS", NUMBER_OF_TRAINS))
url_head = str(_cfg_get("url_head", url_head))
ORIGIN = str(_cfg_get("ORIGIN", ORIGIN))
DESTINATION = str(_cfg_get("DESTINATION", DESTINATION))
username = str(_cfg_get("username", username))
password = str(_cfg_get("password", password))


# ----------------------------
# Buttons (try to gracefully handle missing gpiozero on non-Pi platforms)
# ----------------------------
BUTTON_PINS = [5, 6, 13, 19]
try:
    buttons = [Button(p, pull_up=True, bounce_time=0.3) for p in BUTTON_PINS]
except Exception:
    # Create dummy placeholders if gpiozero not available; each entry must
    # provide a .close() method and .pin.number for callback messages.
    class _DummyButton:
        def __init__(self, pin):
            self.pin = type("P", (), {"number": pin})
        def close(self):
            pass

    buttons = [_DummyButton(p) for p in BUTTON_PINS]


# ----------------------------
# Globals
# ----------------------------
epd = epd2in7_V2.EPD()

# Try to load fonts but fall back to the default PIL font when not available
def _load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


font14 = _load_font(os.path.join(picdir, "Roboto-Regular.ttf"), 14)
font16 = _load_font(os.path.join(picdir, "Roboto-Bold.ttf"), 16)
font18 = _load_font(os.path.join(picdir, "Roboto-Bold.ttf"), 18)
font20 = _load_font(os.path.join(picdir, "Roboto-Bold.ttf"), 20)

_refresh_lock = Lock()
_manual_sleep_timer = None
_last_frame_hash = None
_refresh_count = 0

# ----------------------------
# (rest of original functions unchanged, trimmed for brevity in this copy)
# I'll include the original logic intact below but unchanged except for minor
# path/config/font fallbacks implemented above.

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
    return INTERVAL_SECONDS_MORNING if _is_morning_window() else INTERVAL_SECONDS_DEFAULT

def wifi_on():
    try:
        subprocess.run(["rfkill", "unblock", "wifi"], check=False)
        subprocess.run(["ip", "link", "set", "wlan0", "up"], check=False)
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

def _buffer_bytes(buf):
    try:
        return bytes(buf)
    except Exception:
        return buf if isinstance(buf, (bytes, bytearray)) else bytes(bytearray(buf))

def _prepare_image(image):
    try:
        return image.rotate(180)
    except Exception:
        return image

def _maybe_display(Himage):
    global _last_frame_hash, _refresh_count
    epd.init_Fast()
    if _refresh_count % FULL_REFRESH_EVERY == 0:
        try:
            epd.Clear()
        except Exception:
            pass

    prepared = _prepare_image(Himage)
    buf = epd.getbuffer(prepared)
    h = hashlib.md5(_buffer_bytes(buf)).hexdigest()
    if h == _last_frame_hash:
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
    global _manual_sleep_timer
    if _manual_sleep_timer and _manual_sleep_timer.is_alive():
        _manual_sleep_timer.cancel()
    _manual_sleep_timer = Timer(MANUAL_DISPLAY_SECONDS, _sleeping_revert_callback)
    _manual_sleep_timer.start()

def _sleeping_revert_callback():
    _draw_sleeping_screen()

def _apply_morning_filter(train_list):
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

def disp_train_info():
    try:
        now = datetime.now()
        formatted_datetime = now.strftime("%Y/%m/%d/%H%M")
        url = f"{url_head}{ORIGIN}/to/{DESTINATION}/{formatted_datetime}"

        fetch_count = MORNING_FETCH_COUNT if _is_morning_window() else NUMBER_OF_TRAINS
        trains = collect_train_data(fetch_count, url, username, password)

        if _is_morning_window():
            target = _apply_morning_filter(trains)
            if not target:
                target = trains[:NUMBER_OF_TRAINS]
            else:
                target = target[:NUMBER_OF_TRAINS]
        else:
            target = trains[:NUMBER_OF_TRAINS]

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

        try:
            od_line = f"{ORIGIN} -> {DESTINATION}  updated: {formatted_datetime}"
        except Exception:
            od_line = "updated:" + formatted_datetime
        draw.text((5, 160), od_line, font=font14, fill=0)

        _maybe_display(Himage)

    except Exception as e:
        logging.info(f"disp_train_info error: {e}")

def _safe_refresh(trigger="timer"):
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
        _safe_refresh(trigger=f"button{pin}")
        _schedule_manual_sleep_revert()
    else:
        _safe_refresh(trigger=f"button{pin}")

def run_loop():
    if _is_sleep_window():
        print("Sleep window (21:00–05:00): showing sleeping screen and pausing auto refresh.")
        _draw_sleeping_screen()
        Timer(_seconds_until(SLEEP_END_HM), run_loop).start()
        return

    _safe_refresh(trigger="timer")
    Timer(_next_interval_seconds(), run_loop).start()

def setup_button_callbacks():
    for b in buttons:
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
