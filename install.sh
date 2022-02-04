#!/bin/bash

if (( $EUID != 0 )); then
    echo "Run with sudo"
    exit
fi

if [ $1 == "update" ]; then
echo "Updating"
rm -rf /home/pi/bcmeter/ /home/interface/
git clone https://github.com/bcmeter/bcmeter.git /home/pi/bcmeter


fi

if [ $1 != "update" ]; then


echo "\e[34mInstalling software packages needed to run bcMeter. This will take a while and is dependent on your internet connection, the amount of updates and the speed of your pi."
apt update && apt upgrade -y && apt install -y i2c-tools zram-tools python3-pip python3-smbus python3-dev python3-rpi.gpio python3-numpy nginx php php-fpm php-pear php-common php-cli php-gd screen git && pip3 install gpiozero adafruit-blinka tabulate && systemctl enable zramswap.service  
git clone https://github.com/bcmeter/bcmeter.git /home/pi
  
fi


mv bcmeter/* .
rm -rf gerbers/ stl/
if [ $1 != "update" ]; then
mkdir /home/pi/logs
touch /home/pi/logs/log_current.csv

echo "\e[34mInstalling common Temperature sensors (DHT22/DHT11 and BMP180/280)"
git clone https://github.com/coding-world/Python_BMP.git && cd Python_BMP/ &&  python3 setup.py install 
pip3 install Adafruit_Python_DHT
fi
echo "\e[34mConfiguring"
raspi-config nonint do_onewire 0
sh -c "echo 'dtoverlay=w1-gpio,gpiopin=5' >> /boot/config.txt"
raspi-config nonint do_boot_behaviour B2
echo "\e[34menabled autologin - you can disable this with sudo raspi-config anytime"
raspi-config nonint do_i2c 0
echo "\e[34menabled i2c"
if [ $1 != "update" ]; then
mv nginx-bcMeter.conf /etc/nginx/sites-enabled/default

usermod -aG sudo www-data
usermod -aG sudo pi

echo "www-data  ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/www-data
echo "pi  ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/pi

systemctl start nginx

echo "\e[34menabled webserver."
echo "\e[104m!if you get a 502 bad gateway error in browser, check PHP-FPM version in /etc/nginx/sites-enabled/default is corresponding to installed php version!"

read -p "which hostname / address should be used for access (user interface in browser, ssh)? (for example: bcmeter01):" hostname  
raspi-config nonint do_hostname $hostname

echo "\e[34mconfiguration complete. default timezone is UTC+0 - you can change it with 'sudo raspi-config'. "
fi

if [ $1 != "update" ]; then
if ! grep -q "bcMeter.py" /home/pi/.bashrc; then
 read -p "Do you wish to autostart the script with every bootup?" yn
    case $yn in
        [Yy]* ) echo -e "#autostart bcMeter \n if ! pgrep -f "bcMeter.py" > /dev/null \n then sudo screen python3 /home/pi/bcMeter.py \n else python3 /home/pi/output.py \n fi " >> /home/pi/.bashrc; break;;
        [Nn]* ) break;;
        * ) echo "\e[34mPlease answer yes or no.";;
    esac
fi

read -p "\e[34mDo you wish to start the script NOW? You can always stop it by pressing ctrl+c. " yn
    case $yn in
        [Yy]* ) screen python3 /home/pi/bcMeter.py; break;;
        [Nn]* ) exit;;
        * ) echo "\e[34mPlease answer yes or no.";;
    esac
fi
if [ $1 == "update" ]; then
screen python3 /home/pi/bcMeter.py
fi
chmod -R 777 .


