#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
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

    logging.info("epd2in7 Demo")   
    epd = epd2in7_V2.EPD()
    
    '''2Gray(Black and white) display'''
    logging.info("init and Clear")
    epd.init()
    epd.Clear()
    font24 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 24)
    font18 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 18)
    font35 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 35)
    
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
    draw.text((10, 0), 'hello world', font = font24, fill = 0)
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
    epd.Clear()
    logging.info("Goto Sleep...")
    epd.sleep()
        
except IOError as e:
    logging.info(e)
    
except KeyboardInterrupt:    
    logging.info("ctrl + c:")
    epd2in7_V2.epdconfig.module_exit(cleanup=True)
    exit()
