#!/bin/bash
if (( $EUID != 0 )); then
    echo "Exiting: Re-Run with sudo!"
    exit 1
fi

APT_PACKAGES="\
    i2c-tools \
    zram-tools \
    python3-pip \
    python3-dev \
    python3-pigpio \
    python3-scipy \
    python3-smbus \
    python3-rpi.gpio \
    python3-numpy \
    iptables \
    nginx \
    php-fpm \
    php-pear \
    php-common \
    php-cli \
    php-gd \
    screen \
    git \
    openssl \
    dnsmasq \
    hostapd \
    rsyslog \
    dhcpcd5"

PYTHON_PACKAGES="\
    wifi \
    gpiozero \
    tabulate \
    adafruit-blinka \
    adafruit-circuitpython-sht4x \
    oled-text \
    requests \
    flask-cors"

INSTALLER_VERSION=0.75

BCMINSTALLLOG="/home/pi/maintenance_logs/bcMeter_install.log"
mkdir -p "$(dirname "$BCMINSTALLLOG")"
touch "$BCMINSTALLLOG"
echo "$(date) installation/update log" >> $BCMINSTALLLOG

exec > >(tee -a $BCMINSTALLLOG) 2>&1
echo "checking if the base system is up to date"

apt update && apt upgrade -y 
apt install -y $APT_PACKAGES

echo "enabling syslog [deprecated]"
systemctl enable rsyslog
systemctl start rsyslog



echo "installing/updating python3 packages"
# Install Python packages globally
pip3 install --upgrade pip --break-system-packages
pip3 install $PYTHON_PACKAGES --break-system-packages

if ! grep -q "PIGPIO_ADDR=soft" /etc/environment; then
 sh -c "echo 'PIGPIO_ADDR=soft' >> /etc/environment"
fi

if ! grep -q "PIGPIO_PORT=8888" /etc/environment; then
        sh -c "echo 'PIGPIO_PORT=8888' >> /etc/environment"
fi

# Enable zramswap.service
systemctl enable zramswap.service
systemctl start zramswap.service

BCMINSTALLED=/tmp/bcmeter_installed
UPDATING=/tmp/bcmeter_updating

if [ -f "$UPDATING" ]; then
    echo "script is in update procedure. remove /tmp/bcmeter_updating if you really know that this is not true to run this script again. "
    exit
fi

if [ "$1" == "revert" ]; then
echo "reverting"

fi

# resize the root partition when it is smaller than 3GB
SIZE=$(df -h --output=size,target | grep "/" | awk '{print $1}' |  head -1)
SIZE=$(echo $SIZE | sed 's/[^0-9]//g')
TOCOMPARE=3

if [ $SIZE -lt $TOCOMPARE ]; then
    raspi-config nonint do_expand_rootfs
    echo "resizing partition to full size"
fi

alias_bcd="alias bcd='sudo python3 bcMeter.py debug'"
alias_bcc="alias bcc='sudo python3 bcMeter.py cal'"

bashrc_file="/home/pi/.bashrc"

# Function to check if an alias exists in the .bashrc
check_and_add_alias() {
    local alias_line="$1"
    local alias_name=$(echo "$alias_line" | awk '{print $2}')  # Extract the alias name

    if grep -q "$alias_name" "$bashrc_file"; then
        echo "Alias $alias_name already exists in $bashrc_file"
    else
        echo "$alias_line" >> "$bashrc_file"
        echo "Alias $alias_name added to $bashrc_file"
    fi
}

# Check and add the aliases
check_and_add_alias "$alias_bcd"
check_and_add_alias "$alias_bcc"

# Source the .bashrc file to apply the changes
source "$bashrc_file"

if [ "$1" == "update" ]; then

touch $UPDATING
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
        echo "Backing up old Parameters and WiFi"
        cp /home/pi/bcMeter_config.json  /home/pi/bcMeter_config.orig
        cp /home/pi/bcMeter_wifi.json  /home/pi/bcMeter_wifi.json.orig
        echo "Updating from github"
        rm -rf /home/pi/bcmeter/ /home/pi/interface/
        git clone https://github.com/bcmeter/bcmeter.git /home/pi/bcmeter
        mv /home/pi/bcmeter/* /home/pi/
        rm -rf /home/pi/gerbers/ /home/pi/stl/
        echo "Restoring Parameters"
        mv /home/pi/bcMeter_config.orig /home/pi/bcMeter_config.json
        mv /home/pi/bcMeter_wifi.json.orig /home/pi/bcMeter_wifi.json  
        systemctl restart bcMeter_ap_control_loop
     else echo "most recent version installed"
    fi
fi

if [ "$1" != "update" ]; then
echo "Updating the system"

    if [ -f "$BCMINSTALLED" ]; then
        echo "script already installed. remove /tmp/bcmeter_installed if you really want to run this script again. "
        exit
    fi

    echo "Installing software packages needed to run bcMeter. This will take a while and is dependent on your internet connection, the amount of updates and the speed of your pi."

    GITCLONE=0
    read -p "Clone from git? Hit Enter to continue or type no to copy manually " yn
    yn=${yn:-yes}  # If no input is provided, set 'yn' to 'yes'

    case $yn in
        [Yy]*|yes|YES ) GITCLONE=1;;
        [Nn]*|no|NO ) GITCLONE=0;;
        * ) echo "Please answer yes or no."; exit 1;;
    esac

if [ $GITCLONE -eq 1 ]; then
    git clone https://github.com/bcmeter/bcmeter.git /home/pi/bcmeter && mv /home/pi/bcmeter/* /home/pi/ && rm -rf /home/pi/gerbers/ /home/pi/stl/
fi

    mkdir /home/pi/logs
    touch /home/pi/logs/log_current.csv

    echo "Configuring bcMeter"
    raspi-config nonint do_onewire 0
    if ! grep -q "dtoverlay=w1-gpio,gpiopin=5" /boot/config.txt; then
    sh -c "echo 'dtoverlay=w1-gpio,gpiopin=5' >> /boot/config.txt"
    

    fi
    raspi-config nonint do_boot_behaviour B2
    echo "enabled autologin - you can disable this with sudo raspi-config anytime"
    raspi-config nonint do_i2c 0
    echo "enabled i2c"
    raspi-config nonint do_hostname "bcMeter"
    raspi-config nonint do_net_names 0

    cp /usr/share/dhcpcd/hooks/10-wpa_supplicant /lib/dhcpcd/dhcpcd-hooks/10-wpa_supplicant
    mv /home/pi/nginx-bcMeter.conf /etc/nginx/sites-enabled/default

    usermod -aG sudo www-data
    usermod -aG sudo pi

    echo "www-data  ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/www-data
    echo "pi  ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/pi

    systemctl start nginx

    echo "enabled webserver."
    echo "\e[104m!if you get a 502 bad gateway error in browser when accessing the interface, check PHP-FPM version in /etc/nginx/sites-enabled/default is corresponding to installed php version!"

    echo "configuration complete."



fi

rm -rf /home/pi/bcmeter
chmod -R 777 /home/pi/*

touch $BCMINSTALLED 
rm $UPDATING

tee /etc/network/interfaces.d/wlan0_wifi <<EOF
auto wlan0
iface wlan0 inet dhcp
EOF

tee -a /etc/dhcpcd.conf <<EOF
#bcMeterConfig
interface wlan0
    static ip_address=192.168.18.8/24
    nohook wpa_supplicant
EOF

cp /etc/dnsmasq.conf /etc/dnsmasq.conf.orig

tee -a /etc/dnsmasq.conf <<EOF
#bcMeterConfig
interface=wlan0
    dhcp-range=192.168.18.9,192.168.18.254,255.255.255.0,24h
EOF

cp /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.orig
tee -a /etc/hostapd/hostapd.conf <<EOF
interface=wlan0
driver=nl80211
ssid=bcMeter
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=bcMeterbcMeter
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

sed -i '/#DAEMON_CONF/c\DAEMON_CONF="/etc/hostapd/hostapd.conf"' /etc/default/hostapd

sed -i '/#net.ipv4.ip_forward=1/c\net.ipv4.ip_forward=1' /etc/sysctl.conf
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE && iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
sh -c "iptables-save > /etc/iptables.ipv4.nat"

sed -i '/^exit 0/c\#ifconfig eth0 down\niptables-restore < /etc/iptables.ipv4.nat\nexit 0' /etc/rc.local

    if [ ! -f "$APINSTALLED" ]; then 

    sed -i -e 's/listen \[::\]:80 default_server;/#listen \[::\]:80 default_server;/g' /etc/nginx/sites-enabled/default
    sed -i '1 s/$/ ipv6.disable=1/' /boot/cmdline.txt
    echo "net.ipv6.conf.all.disable_ipv6=1" | tee -a /etc/sysctl.conf
    fi
echo "Finalizing installation, adding services"

touch $APINSTALLED

chmod 777 -R /home/pi

systemctl stop bcMeter_ap_control_loop
systemctl stop bcMeter
# Remove existing service files if they exist and create new ones
rm /lib/systemd/system/bcMeter_ap_control_loop.service
touch /lib/systemd/system/bcMeter_ap_control_loop.service
tee /lib/systemd/system/bcMeter_ap_control_loop.service <<EOF
[Unit]
Description=bcMeter manage-access point & connections to wifi
After=multi-user.target

[Service]
Type=idle
ExecStart=/usr/bin/python3 /home/pi/bcMeter_ap_control_loop.py
KillSignal=SIGINT
StandardOutput=journal
StandardError=journal
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
chmod 644 /lib/systemd/system/bcMeter_ap_control_loop.service
echo "Set up bcMeter_ap_control_loop service"

rm /lib/systemd/system/bcMeter.service
touch /lib/systemd/system/bcMeter.service
tee /lib/systemd/system/bcMeter.service <<EOF
[Unit]
Description=bcMeter.org service
After=multi-user.target

[Service]
Type=idle
ExecStart=/usr/bin/python3 /home/pi/bcMeter.py
KillSignal=SIGINT
StandardOutput=journal
StandardError=journal
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
chmod 644 /lib/systemd/system/bcMeter.service
echo "Set up bcMeter service"

rm /lib/systemd/system/bcMeter_flask.service
touch /lib/systemd/system/bcMeter_flask.service
tee /lib/systemd/system/bcMeter_flask.service <<EOF
[Unit]
Description=bcMeter.org flask webservice
After=multi-user.target

[Service]
Type=idle
ExecStart=/usr/bin/python3 /home/pi/app.py
KillSignal=SIGINT
StandardOutput=journal
StandardError=journal
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
chmod 644 /lib/systemd/system/bcMeter_flask.service
echo "Set up bcMeter_flask service"

rm /etc/wpa_supplicant/wpa_supplicant.conf

systemctl enable bcMeter_ap_control_loop
systemctl enable bcMeter_flask
systemctl daemon-reload 
systemctl unmask hostapd
systemctl enable hostapd

touch /home/pi/maintenance_logs/compair_frost_upload.log

if [ "$1" != "update" ]; then

echo "Installation will now finalize and cut the network connection."
echo "bcMeter will within 2-5 minutes boot into configuration hotspot you'll need to connect to:"
echo "WiFi Name: bcMeter - Password: bcMeterbcMeter"

systemctl stop NetworkManager

apt purge -y network-manager
apt autoremove -y
reboot now

fi
