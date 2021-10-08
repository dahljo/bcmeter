#!/bin/bash

if (( $EUID != 0 )); then
    echo "Run with sudo"
    exit
fi
echo "Installing/Updating software packages needed to run bcMeter. This will take a while and is dependent on your internet connection. "
apt update && apt install -y i2c-tools zram-tools python3-pip python3-smbus python3-dev python3-rpi.gpio python3-numpy nginx screen git && pip3 install gpiozero adafruit-blinka tabulate && systemctl enable zramswap.service  

echo "Installing common Temperature sensors (DHT22/DHT11 and BMP180/280)"
apt install -y git && git clone https://github.com/coding-world/Python_BMP.git && cd Python_BMP/ &&  python3 setup.py install 
git clone --recursive https://github.com/freedom27/MyPyDHT && cd MyPyDHT/ &&  python3 setup.py install

echo "Configuring"

raspi-config nonint do_boot_behaviour B2
echo "enabled autologin - you can disable this with sudo rasp-config anytime"
raspi-config nonint do_i2c 0
echo "enabled i2c"

replace='root /home/pi/logs;'
search='root /var/www/html;'
filename='/etc/nginx/sites-enabled/default'
sed -i "s#$search#$replace#" $filename

echo "enabled webserver"

read -p "which hostname / address should be used for access (user interface in browser, ssh)? (for example: bcmeter01):" hostname  
raspi-config nonint do_hostname $hostname

echo "Downloading/Updating Script"
wget -N -nH https://raw.githubusercontent.com/bcmeter/bcmeter/main/bcMeter.py -P /home/pi/

echo "Downloading/Updating interface"
wget -N -r -nH --cut-dirs=1  bcmeter.org/interface-test/ -P /home/pi/logs/

chmod -R 755 /home/pi/logs/

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

