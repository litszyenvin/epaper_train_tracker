#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import requests
import json
from time import sleep
from datetime import datetime
from gpiozero import Button
from threading import Timer
from train_tracker import collect_train_data, calculate_elapsed_minutes, is_later_than_current_time

picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

import logging
from waveshare_epd import epd2in7_V2
from PIL import Image,ImageDraw,ImageFont
import traceback

# logging.basicConfig(level=logging.DEBUG)

INTERVAL_SECONDS = 300
button = Button(5)  # Replace 2 with your button's GPIO pin number
epd = epd2in7_V2.EPD()
font14 = ImageFont.truetype(os.path.join(picdir, 'Roboto-Regular.ttf'), 14)
font16 = ImageFont.truetype(os.path.join(picdir, 'Roboto-Bold.ttf'), 16)
font18 = ImageFont.truetype(os.path.join(picdir, 'Roboto-Bold.ttf'), 18)
font20 = ImageFont.truetype(os.path.join(picdir, 'Roboto-Bold.ttf'), 20)
url_head = "https://api.rtt.io/api/v1/json/search/"
ORIGIN = 'SAC'
DESTINATION = 'STP'
username = "rttapi_litszyenvin"
password = "bec5d38d598f2a3518962fedf8345569696cb0bf"
number_of_trains = 4

def disp_train_info():
    try:
        logging.info("starting to pull train info")
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime("%Y/%m/%d/%H%M")
        url = url_head + ORIGIN + '/to/' + DESTINATION +'/'+ formatted_datetime
        train_data = collect_train_data(number_of_trains, url, username, password)
        epd.init_Fast()
        epd.Clear()
        
        if len(train_data) == 0: # if train data is empty
            Himage = Image.new('1', (epd.height, epd.width), 255)  # 255: clear the frame
            draw = ImageDraw.Draw(Himage)
            draw.text((5, 0), "Could not retrive train information...", font=font14, fill=0)
            draw.text((5, 160), ('updated:' + formatted_datetime), font = font14, fill = 0)
            epd.display_Base(epd.getbuffer(Himage))

        else: #if train_data is not empty
            destination_text = []
            train_time_text = []
            if train_data:
                for train in train_data:
                    destination_text_line = (f"To: {train['destination']},Plat {train['departure_platform']}")
                    train_time_text_line = (f"{train['departure_time']}---->{train['arrival_time']} ({train['journey_length']} min) [{train['departure_status']}]")
                    destination_text.append(destination_text_line)
                    train_time_text.append(train_time_text_line)
                    # Modified formatting for desired output
            else:
                print("Error retrieving train information.")
            # epd.init()
            
            
            # Drawing on the Horizontal image
            # logging.info("4.Drawing on the Horizontal image...")
            Himage = Image.new('1', (epd.height, epd.width), 255)  # 255: clear the frame
            draw = ImageDraw.Draw(Himage)
            y_position = 0
            for destination_print, train_time_print in zip(destination_text, train_time_text):
                draw.text((5, y_position), destination_print, font=font14, fill=0)
                draw.text((5, y_position + 20), train_time_print, font=font16, fill=0)
                y_position += 40
            
            draw.text((5, 160), ('updated:' + formatted_datetime), font = font14, fill = 0)
            epd.display_Base(epd.getbuffer(Himage))

        # logging.info("Clear...")
        epd.init()   
        # logging.info("Goto Sleep...")
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
        Himage = Image.new('1', (epd.height, epd.width), 255)  # 255: clear the frame
        draw = ImageDraw.Draw(Himage)
        draw.text((50, 50), 'initialising...', font = font20, fill = 0)
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


def run_disp_train_info():
    disp_train_info()
    Timer(INTERVAL_SECONDS, run_disp_train_info).start()

if __name__ == "__main__":
    initialising_disp()
    run_disp_train_info()
    try:
        while True:
            sleep(5)
            pass
    except KeyboardInterrupt:
        print("Exiting...")
