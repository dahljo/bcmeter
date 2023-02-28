#!/bin/bash

APINSTALLED=/tmp/bcmeter_ap_installed

if [ -f "$APINSTALLED" ]; then
    echo "Accesspoint already installed. remove /tmp/bcmeter_ap_installed if you really want to run this script again. "
    exit
fi

if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi

apt install dnsmasq hostapd -y 
systemctl stop dnsmasq && systemctl stop hostapd

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
	dhcp-range=192.168.18.8,192.168.18.254,255.255.255.0,24h
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


chmod +x /home/pi/bcMeter_ap_control_loop.py
touch /lib/systemd/system/bcMeter_ap_control_loop.service

tee /lib/systemd/system/bcMeter_ap_control_loop.service <<EOF
[Unit]
Description=bcMeter manage-access point & connections to wifi
After=multi-user.target

[Service]
Type=idle
ExecStart=/usr/bin/python3 /home/pi/bcMeter_ap_control_loop.py

[Install]
WantedBy=multi-user.target
EOF

chmod 644 /lib/systemd/system/bcMeter_ap_control_loop.service

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
sed -i -e 's/listen \[::\]:80 default_server;/#listen \[::\]:80 default_server;/g' /etc/nginx/sites-enabled/default
sed -i '1 s/$/ ipv6.disable=1/' /boot/cmdline.txt
echo "net.ipv6.conf.all.disable_ipv6=1" | tee -a /etc/sysctl.conf
sysctl -p
touch $APINSTALLED
echo "done installing accesspoint, activating services and rebooting - connection will be lost and hotspot bcMeter will be there in a few minutes!!"

systemctl unmask hostapd && systemctl enable hostapd && systemctl start hostapd && systemctl start dnsmasq 
systemctl daemon-reload && systemctl enable bcMeter_ap_control_loop.service && systemctl enable bcMeter.service
reboot now