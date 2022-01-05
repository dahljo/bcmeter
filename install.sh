#!/bin/bash

if (( $EUID != 0 )); then
    echo "Run with sudo"
    exit
fi


echo "Installing/Updating software packages needed to run bcMeter. This will take a while and is dependent on your internet connection, the amount of updates and the speed of your pi."
apt update && apt upgrade -y && apt install -y i2c-tools zram-tools python3-pip python3-smbus python3-dev python3-rpi.gpio python3-numpy nginx php php-fpm php-pear php-common php-cli php-gd screen git && pip3 install gpiozero adafruit-blinka tabulate && systemctl enable zramswap.service  

git clone https://github.com/bcmeter/bcmeter.git /home/pi
mv bcmeter/* .
rm -rf gerbers/ stl/

mkdir /home/pi/logs
touch /home/pi/logs/log_current.csv
chmod -R 755 /home/pi/logs/

echo "Installing common Temperature sensors (DHT22/DHT11 and BMP180/280)"
apt install -y git && git clone https://github.com/coding-world/Python_BMP.git && cd Python_BMP/ &&  python3 setup.py install 
pip3 install Adafruit_Python_DHT

echo "Configuring"

raspi-config nonint do_boot_behaviour B2
echo "enabled autologin - you can disable this with sudo rasp-config anytime"
raspi-config nonint do_i2c 0
echo "enabled i2c"

mv nginx-bcMeter.conf /etc/nginx/sites-enabled/default

usermod -aG sudo www-data
usermod -aG sudo pi

echo "www-data  ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/www-data
echo "pi  ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/pi

systemctl start nginx

echo "enabled webserver."
tput setaf 1; echo "!if you get a 502 bad gateway error, check PHP-FPM version in /etc/nginx/sites-enabled/default is corresponding to installed php version!"

read -p "which hostname / address should be used for access (user interface in browser, ssh)? (for example: bcmeter01):" hostname  
raspi-config nonint do_hostname $hostname

echo "configuration complete. default timezone is UTC+0 - you can change it with 'sudo raspi-config'. "

if ! grep -q "bcMeter.py" /home/pi/.bashrc; then
 read -p "Do you wish to autostart the script with every bootup?" yn
    case $yn in
        [Yy]* ) echo -e "#autostart bcMeter \n if ! pgrep -f "bcMeter.py" > /dev/null \n then sudo screen python3 /home/pi/bcMeter.py \n else python3 /home/pi/output.py \n fi " >> /home/pi/.bashrc; break;;
        [Nn]* ) break;;
        * ) echo "Please answer yes or no.";;
    esac
fi

read -p "Do you wish to start the script NOW? You can always stop it by pressing ctrl+c. " yn
    case $yn in
        [Yy]* ) screen python3 /home/pi/bcMeter.py; break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac



read -p "After Reboot the device will be available via the hostname you entered above. Ready to reboot?" yn
    case $yn in
        [Yy]* ) screen python3 /home/pi/bcMeter.py; break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac

