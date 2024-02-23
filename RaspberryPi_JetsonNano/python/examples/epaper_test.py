#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import requests
import json
from datetime import datetime
from train_tracker import read_https_endpoint, calculate_elapsed_minutes, is_later_than_current_time

picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

import logging
from waveshare_epd import epd2in7_V2
import time
from PIL import Image,ImageDraw,ImageFont
import traceback

logging.basicConfig(level=logging.DEBUG)

try:

    logging.info("starting to pull train info")
    url_head = "https://api.rtt.io/api/v1/json/search/"
    origin = 'SAC'
    destination = 'STP'
    username = "rttapi_litszyenvin"
    password = "bec5d38d598f2a3518962fedf8345569696cb0bf"
    number_of_trains = 4
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%Y/%m/%d/%H%M")
    url = url_head + origin + '/to/' + destination +'/'+ formatted_datetime
    # url = 'https://api.rtt.io/api/v1/json/search/SAC/to/STP/2024/02/21/1310'
    train_data = read_https_endpoint(number_of_trains, url, username, password)
    logging.info("finished to pull train info")
    
    logging.info("epd2in7 Demo")   
    epd = epd2in7_V2.EPD()
    
    '''2Gray(Black and white) display'''
    logging.info("init and Clear")
    epd.init()
    epd.Clear()
    font12 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 12)
    font18 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 18)
    font20 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 20)
    
    # Quick refresh
    logging.info("Quick refresh demo")
    # epd.init_Fast()

    
    # Normal refresh
    logging.info("Normal refresh demo")
    epd.init()

    
    # Drawing on the Horizontal image
    logging.info("4.Drawing on the Horizontal image...")
    Himage = Image.new('1', (epd.height, epd.width), 255)  # 255: clear the frame
    draw = ImageDraw.Draw(Himage)


    destination_text = []
    train_time_text = []
    if train_data:
        for train in train_data:
            destination_text_line = (f"Destination: {train['destination']}")
            train_time_text_line = (f"{train['departure_time']}---->{train['arrival_time']} ({train['journey_length']} minutes) [{train['departure_status']}]")
            destination_text.append(destination_text_line)
            train_time_text.append(train_time_text_line)
            # Modified formatting for desired output
        else:
            print("Error retrieving train information.")

    draw.text((5, 0), destination_text[0], font = font12, fill = 0)
    draw.text((5, 20), train_time_text[0], font = font12, fill = 0)
    draw.text((5, 40), destination_text[1], font = font12, fill = 0)
    draw.text((5, 60), train_time_text[1], font = font12, fill = 0)
    draw.text((5, 80), destination_text[2], font = font12, fill = 0)
    draw.text((5, 100), train_time_text[2], font = font12, fill = 0)
    draw.text((5, 120), destination_text[3], font = font12, fill = 0)
    draw.text((5, 140), train_time_text[3], font = font12, fill = 0)
    epd.display_Base(epd.getbuffer(Himage))
    time.sleep(2)

    # # partial update
    # logging.info("5.show time")
    # epd.init()   
    # '''
    # # If you didn't use the EPD_2IN7_V2_Display_Base() function to refresh the image before,
    # # use the EPD_2IN7_V2_Display_Base_color() function to refresh the background color, 
    # # otherwise the background color will be garbled 
    # '''
    # # epd.display_Base_color(0xff)
    # # Himage = Image.new('1', (epd.height ,epd.width), 0xff)
    # # draw = ImageDraw.Draw(time_image)
    # num = 0
    # while (True):
    #     draw.rectangle((10, 110, 120, 150), fill = 255)
    #     draw.text((10, 110), time.strftime('%H:%M:%S'), font = font24, fill = 0)
    #     newimage = Himage.crop([10, 110, 120, 150])
    #     Himage.paste(newimage, (10,110)) 
    #     epd.display_Partial(epd.getbuffer(Himage),110, epd.height - 120, 150, epd.height - 10)
    #     num = num + 1
    #     if(num == 10):
    #         break

    logging.info("Clear...")
    epd.init()   
    logging.info("Goto Sleep...")
    epd.sleep()
        
except IOError as e:
    logging.info(e)
    
except KeyboardInterrupt:    
    logging.info("ctrl + c:")
    epd2in7_V2.epdconfig.module_exit(cleanup=True)
    exit()
