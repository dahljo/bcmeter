#!/bin/bash

BCMINSTALLED=/tmp/bcmeter_installed

if (( $EUID != 0 )); then
    echo "Run with sudo"
    exit
fi


if [ "$1" == "update" ]; then
    version=''
    localfile=bcMeter.py

    for((i=1; i<=50; i++))
    do
      line=$(head -$i $localfile | tail -1)
      if [[ $line == bcMeter_version* ]]
      then
        version=$(echo $line | cut -d '"' -f2)
        break
      else
         version='0.9.20' #every version before was not set as variable so it has to be older. force update then.
      fi
    done

    version_parts=($(echo $version | tr '.' ' '))

    major_version=${version_parts[0]}
    minor_version=${version_parts[1]}
    patch_version=${version_parts[2]}

    echo "installed version: " $major_version $minor_version $patch_version
    wget -q  -P /tmp/ https://raw.githubusercontent.com/dahljo/bcmeter/main/bcMeter.py

    localfile=/tmp/bcMeter.py
    echo "checking" $localfile

    for((i=1; i<=50; i++))
    do
      line=$(head -$i $localfile | tail -1)
      if [[ $line == bcMeter_version* ]]
      then
        version=$(echo $line | cut -d '"' -f2)
        break
        else
         version='0.9.19' #if not found more recent online, dont update
      fi

    done

    version_parts=($(echo $version | tr '.' ' '))

    git_major_version=${version_parts[0]}
    git_minor_version=${version_parts[1]}
    git_patch_version=${version_parts[2]}

    echo "available version: " $git_major_version $git_minor_version $git_patch_version
    rm /tmp/bcMeter*
    if [ "$major_version" -lt "$git_major_version" ] || [ "$minor_version" -lt "$git_minor_version" ] || [ "$patch_version" -lt "$git_patch_version" ]
    then
        echo "running update"
        systemctl stop bcMeter_ap_control_loop
        systemctl stop bcMeter
        rm /home/pi/ap_control_loop.log
        echo "Backing up old Parameters and WiFi"
        cp /home/pi/bcMeterConf.py  /home/pi/bcMeterConf.orig
        cp /home/pi/bcMeter_wifi.json  /home/pi/bcMeter_wifi.json.orig
        echo "Updating from github"
        rm -rf /home/pi/bcmeter/ /home/pi/interface/
        git clone https://github.com/bcmeter/bcmeter.git /home/pi/bcmeter
        mv /home/pi/bcmeter/* /home/pi/
        rm -rf /home/pi/gerbers/ /home/pi/stl/
        echo "Restoring Parameters"
        mv /home/pi/bcMeterConf.orig /home/pi/bcMeterConf.py
        mv /home/pi/bcMeter_wifi.json.orig /home/pi/bcMeter_wifi.json  
        systemctl start bcMeter_ap_control_loop
        systemctl start bcMeter
     else echo "most recent version installed"
    fi
fi


if [ "$1" != "update" ]; then
echo "Updating the system"
apt update && apt upgrade -y && apt autoremove -y;


    if [ -f "$BCMINSTALLED" ]; then
        echo "script already installed. remove /tmp/bcmeter_installed if you really want to run this script again. "
        exit
        fi

    echo "Installing software packages needed to run bcMeter. This will take a while and is dependent on your internet connection, the amount of updates and the speed of your pi."
    apt install -y i2c-tools zram-tools python3-pip python3-smbus python3-dev python3-rpi.gpio python3-numpy nginx php php-fpm php-pear php-common php-cli php-gd screen git openssl && pip3 install gpiozero tabulate && systemctl enable zramswap.service  


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
tee /lib/systemd/system/bcMeter.service <<EOF
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
    systemctl daemon-reload 

fi

rm -rf /home/pi/bcmeter
chmod -R 777 /home/pi/*

# resize the root partition when it is smaller than 3GB
SIZE=$(df -h --output=size,target | grep "/" | awk '{print $1}' |  head -1)
SIZE=$(echo $SIZE | sed 's/[^0-9]//g')
TOCOMPARE=3

if [ $SIZE -lt $TOCOMPARE ]; then
    sudo raspi-config nonint do_expand_rootfs
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

