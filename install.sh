#!/bin/bash

BCMINSTALLED=/tmp/bcmeter_installed

if (( $EUID != 0 )); then
    echo "Run with sudo"
    exit
fi


if [ "$1" == "update" ]; then
    echo "Backing up old Parameters"
    cp /home/pi/bcMeterConf.py  /home/pi/bcMeterConf.orig
    echo "Updating from github"
    rm -rf /home/pi/bcmeter/ /home/pi/interface/
    git clone https://github.com/bcmeter/bcmeter.git /home/pi/bcmeter
    mv /home/pi/bcmeter/* /home/pi/
    rm -rf /home/pi/gerbers/ /home/pi/stl/

    echo "Restoring Parameters"
    mv /home/pi/bcMeterConf.orig /home/pi/bcMeterConf.py

fi


if [ "$1" != "update" ]; then
echo "Updating the system"
apt update && apt upgrade -y && apt autoremove -y;


    if [ -f "$BCMINSTALLED" ]; then
        echo "script already installed. remove /tmp/bcmeter_installed if you really want to run this script again. "
        exit
        fi

    echo "Installing software packages needed to run bcMeter. This will take a while and is dependent on your internet connection, the amount of updates and the speed of your pi."
    apt install -y i2c-tools zram-tools python3-pip python3-smbus python3-dev python3-rpi.gpio python3-numpy nginx php php-fpm php-pear php-common php-cli php-gd screen git openssl && pip3 install gpiozero adafruit-blinka tabulate && systemctl enable zramswap.service  


    GITCLONE=0
    read -p "Clone from git? Not necessary if you copied the files yourself. (yes or no)" yn
        case $yn in
            [Yy]* ) GITCLONE=1;;
            [Nn]* ) break;;
            * ) echo "Please answer yes or no.";;
        esac

    if ($GITCLONE=1); then
        git clone https://github.com/bcmeter/bcmeter.git /home/pi/bcmeter
        mv /home/pi/bcmeter/* /home/pi/
        rm -rf /home/pi/gerbers/ /home/pi/stl/
    fi


fi


if [ "$1" != "update" ]; then
    mkdir /home/pi/logs
    touch /home/pi/logs/log_current.csv



echo "Configuring"
raspi-config nonint do_onewire 1
sh -c "echo 'dtoverlay=w1-gpio,gpiopin=5' >> /boot/config.txt"
raspi-config nonint do_boot_behaviour B2
echo "enabled autologin - you can disable this with sudo raspi-config anytime"
raspi-config nonint do_i2c 0
echo "enabled i2c"


    mv /home/pi/nginx-bcMeter.conf /etc/nginx/sites-enabled/default

    usermod -aG sudo www-data
    usermod -aG sudo pi

    echo "www-data  ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/www-data
    echo "pi  ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/pi

    systemctl start nginx

    echo "enabled webserver."
    echo "\e[104m!if you get a 502 bad gateway error in browser when accessing the interface, check PHP-FPM version in /etc/nginx/sites-enabled/default is corresponding to installed php version!"

    echo "configuration complete."


touch /lib/systemd/system/bcMeter.service
tee -a /lib/systemd/system/bcMeter.service <<EOF
[Unit]
Description=bcMeter.org service
After=multi-user.target

[Service]
Type=idle
ExecStart=/usr/bin/python3 /home/pi/bcMeter.py

[Install]
WantedBy=multi-user.target
EOF

chmod 644 /lib/systemd/system/bcMeter.service
systemctl daemon-reload && systemctl enable bcMeter.service

fi

rm -rf /home/pi/bcmeter
chmod -R 777 /home/pi/*

# resize the root partition when it is smaller than 3GB

FLAG_FILE=/tmp/rootfs_resized

if [ ! -f "$FLAG_FILE" ]; then
  # Create flag file
  touch $FLAG_FILE

SIZE=$(df -h --output=size,target | grep "/" | awk '{print $1}' |  head -1)
SIZE=$(echo $SIZE | sed 's/[^0-9]//g')

TOCOMPARE=3

if [ $SIZE -lt $TOCOMPARE ]; then
    raspi-config nonint do_expand_rootfs
    echo "partition resized, please reboot to have the changes take an effect when this script is finished."
fi
fi

touch $BCMINSTALLED 
if [ "$1" != "update" ]; then

    read -p "Basically the bcMeter is now set up. It is recommended to install the WiFi Accesspoint. It will create an own WiFi if no known WiFi is available. Continue? " yn
        case $yn in
            [Yy]* ) bash accesspoint-install.sh; break;;
            [Nn]* ) exit;;
            * ) echo "Please answer yes (y) or no (n).";;
        esac
    fi
