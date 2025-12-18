# Raspberry Pi Zero W E-Paper Train Tracker Setup

This project displays live UK train departure information on a Waveshare
2.7″ e-Paper HAT (V2) using a Raspberry Pi Zero W.\
It connects to the Realtime Trains API, updates automatically every few
minutes, and lets you manually refresh at any time using any of the four
buttons on the e-Paper HAT.

------------------------------------------------------------------------

## Requirements

-   Raspberry Pi Zero W\
-   micro-SD card (8 GB or larger)\
-   Waveshare 2.7″ e-Paper HAT (V2): [Amazon UK
    link](https://www.amazon.co.uk/dp/B075FQKSZ9)\
-   Stable 5 V 2 A power supply\
-   Wi-Fi network credentials\
-   A computer with [Raspberry Pi
    Imager](https://www.raspberrypi.com/software/)

------------------------------------------------------------------------

## 1. Flash Raspberry Pi OS Lite

1.  Download and open Raspberry Pi Imager:
    [raspberrypi.com/software](https://www.raspberrypi.com/software)\
2.  Choose:
    -   Device: Raspberry Pi Zero W\
    -   OS: Raspberry Pi OS Lite (32-bit)\
    -   Storage: your SD card\
3.  Click the settings icon and enable:
    -   Set hostname (e.g. `raspberrypi`)\
    -   Enable SSH\
    -   Configure Wi-Fi (SSID, password, and country = UK)\
    -   Set username `pi` and a password\
4.  Write the image, then insert the card into the Pi.

------------------------------------------------------------------------

## 2. First boot

1.  Power on the Pi Zero W.\

2.  Wait about one minute for Wi-Fi to connect.\

3.  SSH into the Pi from your computer:

    ``` bash
    ssh pi@raspberrypi.local
    ```

4.  Update the system:

    ``` bash
    sudo apt update && sudo apt full-upgrade -y
    ```

------------------------------------------------------------------------

## 3. Enable SPI

``` bash
sudo raspi-config
```

Then select: - Interface Options → SPI → Enable\
- Finish and reboot

------------------------------------------------------------------------

## 4. Install dependencies

``` bash
sudo apt install -y python3-pip git python3-pil python3-gpiozero python3-requests python3-spidev fonts-roboto
pip install waveshare-epd
```

------------------------------------------------------------------------

## 5. Clone this repository

``` bash
cd ~
git clone https://github.com/litszyenvin/epaper_train_tracker.git
cd epaper_train_tracker/RaspberryPi_JetsonNano/python/examples
```

------------------------------------------------------------------------

## 6. Test the script manually

``` bash
python3 epaper_train_disp_w_button.py
```

You should see "initialising..." on the display, followed by live train
information.

------------------------------------------------------------------------

## 7. Set up auto-start on boot

Create the service:

``` bash
sudo nano /etc/systemd/system/epaper.service
```

Paste the following:

``` ini
[Unit]
Description=E-paper Train Display
After=network.target dev-spidev0.0.device
Wants=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=traintrackpi
WorkingDirectory=/home/traintrackpi/epaper_train_tracker/RaspberryPi_JetsonNano/python/examples
Environment=PYTHONUNBUFFERED=1
ExecStartPre=/bin/sh -c 'until ip route | grep -q "^default "; do sleep 1; done'
ExecStart=/usr/bin/python3 -u /home/traintrackpi/epaper_train_tracker/RaspberryPi_JetsonNano/python/examples/epaper_train_disp_w_button.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

⚠️ **Important:** Before saving, modify the following to match your setup:
- `User=traintrackpi` — change to your actual username (e.g., `pi`)
- `WorkingDirectory` path — update if your cloned directory is in a different location
- `ExecStart` path — must match your `WorkingDirectory`

Enable it:

``` bash
sudo systemctl daemon-reload
sudo systemctl enable --now epaper.service
```

------------------------------------------------------------------------

## 8. Verify operation

``` bash
systemctl status epaper.service
journalctl -u epaper.service -f
```

You should see logs showing the script running and the display updating.

------------------------------------------------------------------------

## 9. Manual refresh

Press any of the four buttons on the Waveshare HAT to trigger an
immediate refresh of the train data.

------------------------------------------------------------------------

## 10. Finished

Your Raspberry Pi Zero W now boots straight into the train tracker
display, automatically updates every few minutes, and supports manual
refresh via the buttons.
