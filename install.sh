#!/bin/bash

# Check if /home/bcMeter exists, otherwise default to /home/pi
BASE_DIR="/home/pi"
if [ -d "/home/bcMeter" ]; then
    BASE_DIR="/home/bcMeter"
fi

if (( $EUID != 0 )); then
    echo "Exiting: Re-Run with sudo!"
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
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
    rfkill \
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

INSTALLER_VERSION="0.85 24-11-22"

BCMINSTALLLOG="$BASE_DIR/maintenance_logs/bcMeter_install.log"
mkdir -p "$(dirname "$BCMINSTALLLOG")"
touch "$BCMINSTALLLOG"
echo "$(date) installation/update log" >> "$BCMINSTALLLOG"

exec > >(tee -a "$BCMINSTALLLOG") 2>&1
echo "Checking if the base system is up to date..."



apt update

if [ "$1" == "noupgrade" ]; then
    echo "Skipping apt upgrade due to 'noupgrade' parameter."
else
    apt upgrade -y
fi
apt install -y $APT_PACKAGES

echo "Enabling syslog"
systemctl enable rsyslog
systemctl start rsyslog

echo "Installing/updating python3 packages"
# Install Python packages globally
pip3 install --upgrade pip --break-system-packages
pip3 install $PYTHON_PACKAGES --break-system-packages

if ! grep -q "PIGPIO_ADDR=soft" /etc/environment; then
    echo 'PIGPIO_ADDR=soft' >> /etc/environment
fi

if ! grep -q "PIGPIO_PORT=8888" /etc/environment; then
    echo 'PIGPIO_PORT=8888' >> /etc/environment
fi

# Enable zramswap.service
systemctl enable zramswap.service
systemctl start zramswap.service

BCMINSTALLED=/tmp/bcmeter_installed
UPDATING=/tmp/bcmeter_updating

if [ -f "$UPDATING" ]; then
    echo "Script is in update procedure. Remove /tmp/bcmeter_updating if this is not true to run this script again."
    exit
fi

if [ "$1" == "revert" ]; then
    echo "Reverting"
    rm "$UPDATING"
    rm "$BASE_DIR/logs/*"
    rm "$BASE_DIR/maintenance_logs*"
    touch "$BASE_DIR/log_current.csv"
fi

# Resize the root partition when it is smaller than 3GB
SIZE=$(df -h --output=size,target | grep "/" | awk '{print $1}' | head -1)
SIZE=$(echo "$SIZE" | sed 's/[^0-9]//g')
TOCOMPARE=3

if [ "$SIZE" -lt "$TOCOMPARE" ]; then
    raspi-config nonint do_expand_rootfs
    echo "Resizing partition to full size"
fi

alias_bcd="alias bcd='python3 bcMeter.py debug'"
alias_bcc="alias bcc='python3 bcMeter.py cal'"

bashrc_file="$BASE_DIR/.bashrc"

# Function to check if an alias exists in the .bashrc
check_and_add_alias() {
    local alias_line="$1"
    local alias_name
    alias_name=$(echo "$alias_line" | awk '{print $2}')  # Extract the alias name

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


echo "Configuring Nginx"
hostname=$(hostname)  # Capture the current system hostname
NGINX_CONF="/etc/nginx/sites-available/default"
cat > "$NGINX_CONF" << EOL
server {
    listen 80 default_server;
    server_name \$host;

    # Set the root directory
    root $BASE_DIR;

    # Disable caching
    expires -1;
    proxy_no_cache 1;
    proxy_cache_bypass 1;

    # Set the default index files
    index index.html index.htm index.php;

    # Redirect the root URL to your specific page
    location = / {
        rewrite ^/$ /interface/index.php redirect;
    }

    # Serve files or return a 404 if not found
    location / {
        try_files \$uri \$uri/ =404;
    }

    # PHP handling
    location ~ \.php$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php8.2-fpm.sock;
    }

    # Deny access to hidden files
    location ~ /\. {
        deny all;
    }

    # Enable directory listing for /logs
    location /logs/ {
        autoindex on;
    }
}
EOL


# Restart services to apply changes
echo "Restarting dnsmasq and nginx..."
systemctl restart dnsmasq
systemctl restart nginx

echo "All configurations for iptables, dnsmasq, and nginx have been applied successfully."

#updating
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

    if [ "$major_version" -lt "$git_major_version" ] || [ "$minor_version" -lt "$git_minor_version" ] || [ "$patch_version" -lt "$git_patch_version" ]; then
        echo "Running update"
        echo "Backing up old Parameters and WiFi"
        cp "$BASE_DIR/bcMeter_config.json" "$BASE_DIR/bcMeter_config.orig"
        cp "$BASE_DIR/bcMeter_wifi.json" "$base_dir/bcMeter_wifi.json.orig"
        
        echo "Updating from GitHub"
        rm -rf "$BASE_DIR/bcmeter/" "$BASE_DIR/interface/"
        git clone https://github.com/bcmeter/bcmeter.git "$base_dir/bcmeter"
        
        # Move cloned files to the base directory
        mv "$BASE_DIR/bcmeter/"* "$BASE_DIR/"
        
        # Clean up unnecessary folders
        rm -rf "$BASE_DIR/gerbers/" "$BASE_DIR/stl/"
        
        echo "Restoring Parameters"
        mv "$BASE_DIR/bcMeter_config.orig" "$BASE_DIR/bcMeter_config.json"
        mv "$BASE_DIR/bcMeter_wifi.json.orig" "$BASE_DIR/bcMeter_wifi.json"
        
        # Restart the service
        systemctl restart bcMeter_ap_control_loop
    else
        echo "Most recent version installed"
    fi

fi



get_config_file() {
    if [ -f "/boot/firmware/config.txt" ]; then
        echo "/boot/firmware/config.txt"
    else
        echo "/boot/config.txt"
    fi
}

CONFIG_FILE=$(get_config_file)

# Function to append configurations if not already present
append_config() {
    local config_line="$1"
    if ! grep -qF "$config_line" "$CONFIG_FILE"; then
        echo "$config_line" | tee -a "$CONFIG_FILE"
    fi
}

# Append necessary configurations
append_config "dtoverlay=disable-bt"



if ls /sys/bus/w1/devices/ | grep -q "28"; then
    echo "temperature sensor on onewire bus found."
    # Enable OneWire interface if not already enabled
    if ! raspi-config nonint get_onewire | grep -q "1"; then
        raspi-config nonint do_onewire 1
        # Ensure the dtoverlay line is in config.txt
        append_config "dtoverlay=w1-gpio,gpiopin=5"
    fi
else
    echo "No temperature sensor on onewire bus found."
    # Disable OneWire interface if enabled
    if raspi-config nonint get_onewire | grep -q "1"; then
        raspi-config nonint do_onewire 0
        # Remove the dtoverlay line from config.txt
        sed -i '/dtoverlay=w1-gpio,gpiopin=5/d' /boot/config.txt
    fi
fi



# installing System
if [ -f "$BCMINSTALLED" ]; then
    echo "Script already installed. Remove /tmp/bcmeter_installed if you really want to run this script again."
    exit
fi

echo "Installing software packages needed to run bcMeter. This will take a while and is dependent on your internet connection, the amount of updates, and the speed of your Pi."

GITCLONE=0
read -p "Clone from git (y) or already downloaded (n) (y/n): " yn
yn=${yn:-y}  # If no input is provided, set 'yn' to 'y'

case $yn in
    [Yy]* ) GITCLONE=1;;
    [Nn]* ) GITCLONE=0;;
    * ) echo "Please answer y or n."; exit 1;;
esac

if [ "$GITCLONE" -eq 1 ]; then
    git clone https://github.com/bcmeter/bcmeter.git "$BASE_DIR/bcmeter" && mv "$BASE_DIR/bcmeter/*" "$BASE_DIR/" && rm -rf "$BASE_DIR/gerbers/" "$BASE_DIR/stl/"
fi
mkdir "$BASE_DIR/logs"
touch "$BASE_DIR/logs/log_current.csv"

echo "Configuring bcMeter"
raspi-config nonint do_boot_behaviour B2
echo "Enabled autologin - you can disable this with sudo raspi-config anytime"
raspi-config nonint do_i2c 0
echo "Enabled i2c"
raspi-config nonint do_hostname "bcMeter"
raspi-config nonint do_net_names 0

cp /usr/share/dhcpcd/hooks/10-wpa_supplicant /lib/dhcpcd/dhcpcd-hooks/10-wpa_supplicant

usermod -aG sudo www-data
usermod -aG sudo pi

echo "www-data  ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/www-data
echo "pi  ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/pi

systemctl start nginx
echo "Enabled webserver."
echo "If you get a 502 bad gateway error in the browser when accessing the interface, check PHP-FPM version in /etc/nginx/sites-enabled/default is corresponding to installed php version!"

echo "Configuration complete."


rm -rf "$BASE_DIR/bcmeter"
chmod -R 777 "$BASE_DIR"/*

touch "$BCMINSTALLED" 

if [ -f "$UPDATING" ]; then
    rm "$UPDATING"
else
    echo "File $UPDATING does not exist, skipping removal."
fi




configure_network_interfaces() {
    NETWORK_CONF="/etc/network/interfaces.d/wlan0_wifi"
    
    # Check if the content already exists in the file
    if ! grep -q "^auto wlan0" "$NETWORK_CONF"; then
        # Write the configuration if not already present
        tee "$NETWORK_CONF" <<EOF > /dev/null
auto wlan0
iface wlan0 inet dhcp
EOF
    fi
}

configure_network_interfaces

configure_dhcpcd() {
    DHCPCD_CONF="/etc/dhcpcd.conf"
    
    # Check if the first line already exists in the file
    if ! grep -q "^#bcMeterConfig" "$DHCPCD_CONF"; then
        # Append the bcMeterConfig settings if not already present
        tee -a "$DHCPCD_CONF" <<EOF > /dev/null
#bcMeterConfig
interface wlan0
    static ip_address=192.168.18.8/24
    nohook wpa_supplicant
EOF
    fi
}

configure_dhcpcd

mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig

configure_dnsmasq() {
    DNSMASQ_CONF="/etc/dnsmasq.conf"

    # Append the bcMeterConfig settings to the dnsmasq config
    tee -a "$DNSMASQ_CONF" <<EOF > /dev/null
#bcMeterConfig
interface=wlan0
    dhcp-range=192.168.18.9,192.168.18.254,255.255.255.0,24h
EOF

    # Disable DNS caching if not already disabled
    if ! grep -q "^cache-size=0" "$DNSMASQ_CONF"; then
        if grep -q "^cache-size" "$DNSMASQ_CONF"; then
            sed -i 's/^cache-size=.*/cache-size=0/' "$DNSMASQ_CONF"
        else
            echo "cache-size=0" | tee -a "$DNSMASQ_CONF" > /dev/null
        fi
    fi
}

# Run the combined function
configure_dnsmasq

mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.orig
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

#sed -i '/#DAEMON_CONF/c\DAEMON_CONF="/etc/hostapd/hostapd.conf"' /etc/default/hostapd


CMDLINE_FILE="/boot/cmdline.txt"
if [ -f /boot/firmware/cmdline.txt ]; then
    CMDLINE_FILE="/boot/firmware/cmdline.txt"
fi

if ! grep -q 'ipv6.disable=1' "$CMDLINE_FILE"; then
    sed -i '1 s/$/ ipv6.disable=1/' "$CMDLINE_FILE"
fi
if ! grep -q 'net.ipv6.conf.all.disable_ipv6=1' /etc/sysctl.conf; then
    echo "net.ipv6.conf.all.disable_ipv6=1" | tee -a /etc/sysctl.conf
fi





chmod 777 -R "$BASE_DIR"

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
ExecStart=/usr/bin/python3 $BASE_DIR/bcMeter_ap_control_loop.py
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
ExecStart=/usr/bin/python3 $BASE_DIR/bcMeter.py
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
ExecStart=/usr/bin/python3 $BASE_DIR/app.py
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

systemctl disable hciuart
systemctl enable bcMeter_ap_control_loop
systemctl enable bcMeter_flask
systemctl daemon-reload 
systemctl unmask hostapd
systemctl enable hostapd

touch "$BASE_DIR/maintenance_logs/compair_frost_upload.log"

if [ "$1" != "update" ]; then
    echo "Installation will now finalize silently, cut the network connection and then reboot. This takes a while."
    echo "bcMeter will create a hotspot in about 5 minutes you'll need to connect to:"
    echo "WiFi Name: bcMeter - Password: bcMeterbcMeter"

    systemctl stop NetworkManager
    apt purge -y network-manager
    apt autoremove -y
    echo "bcMeter Setup complete. Rebooting."

    reboot now
fi
apt autoremove -y
echo "bcMeter Update complete."