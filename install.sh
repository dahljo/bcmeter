#!/bin/bash

if (( $EUID != 0 )); then
    echo "Run with sudo"
    exit
fi
echo "Installing/Updating software packages needed to run bcMeter. This will take a while and is dependent on your internet connection. "
#apt update && apt install -y i2c-tools zram-tools python3-pip python3-smbus python3-dev python3-rpi.gpio  python3-numpy nginx screen && pip3 install gpiozero adafruit-blinka &&  systemctl enable zramswap.service

raspi-config nonint get_autologin
echo "enabled autologin - you can disable this with sudo rasp-config anytime"
raspi-config nonint do_i2c 0
echo "enabled i2c"
read -p "Now configuring webserver. Press any key to continue... " -n1 -s

replace='root /home/pi/logs;'
search='root /var/www/html;'
filename='/etc/nginx/sites-enabled/default'
sed -i "s#$search#$replace#" $filename



echo "Downloading/Updating Script"
wget -N -nH bcmeter.org/bcMeter.py -P /home/pi/

echo "Downloading/Updating interface"
wget -N -r -nH --cut-dirs=1  bcmeter.org/interface-test/ -P /home/pi/logs/


if ! grep -q "bcMeter.py" /home/pi/.bashrc
 read -p "Do you wish to autostart the script?" yn
    case $yn in
        [Yy]* ) echo -e "if ! pgrep -f "bcMeter.py" > /dev/null \n then sudo screen python3 /home/pi/bcMeter.py \n fi" >> /home/pi/.bashrc; break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac
fi
 read -p "Do you wish to start the script now?" yn
    case $yn in
        [Yy]* ) screen python3 /home/pi/bcMeter.py; break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac

