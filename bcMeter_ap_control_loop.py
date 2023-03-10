
#heavily adapted telraams work 

import socket
import subprocess
import signal
import os
import time
import re
import signal
import requests
import uuid
import json
import bcMeterConf
import importlib


# endpoint for checking internet connection (this is Google's public DNS server)
DNS_HOST = "8.8.8.8"
DNS_PORT = 53
DNS_TIME_OUT = 3

#status constants
STATUS_OK=1
STATUS_NOK=0
keep_running=False

# sleep timeintervals
SERVICE_WAIT_TIME = 3 			

DONTSTARTTHEBCMETER = False

#wifi credentials file
WIFI_CREDENTIALS_FILE='/home/pi/bcMeter_wifi.json'
AP_LOG_FILE = '/home/pi/ap_control_loop.log'


#stop hotspot from being active after 10 Minutes of running (can be overridden by parameter run_hotspot=True)
hotspot_maxtime = 600
#var and function for the interrupt from php // not used for bcMeter but might be handy later

def check_exit_status(service):
	status =""
	output =str(subprocess.run(["systemctl", "status", service], capture_output=True, text=True).stdout.strip("\n"))
	output=output.splitlines()
	for line in output:
		if "Process:" in line:
			status = str(line.split("code=")[1]).split(",")[0]
			break
	return status


def print_to_file(string):
	print(string)
	file = AP_LOG_FILE
	current_time = time.localtime()
	timestamp = "["+ time.strftime("%Y-%m-%d %H:%M:%S", current_time) +"]"
	string = timestamp + " " + str(string) + "\n"
	with open(file, 'a+') as f:
		f.write(string)



def run_bcMeter_service():
	p = subprocess.call(["sudo", "systemctl", "enable", "bcMeter"])
	p = subprocess.call(["sudo", "systemctl", "start", "bcMeter"])
	time.sleep(SERVICE_WAIT_TIME)
	#print_to_file("bcMeter service activated.")


def stop_bcMeter_service():
	DONTSTARTTHEBCMETER = True
	p = subprocess.call(["sudo", "systemctl", "stop", "bcMeter"])
	p = subprocess.call(["sudo", "systemctl", "disable", "bcMeter"])
	time.sleep(SERVICE_WAIT_TIME)
	#print_to_file("bcMeter service disabled.")

def activate_dnsmasq_service():
	p = subprocess.call(["sudo", "systemctl", "enable", "dnsmasq"])
	p = subprocess.call(["sudo", "systemctl", "start", "dnsmasq"])
	time.sleep(SERVICE_WAIT_TIME)
	#print_to_file("Dnsmasq service activated.")


def deactivate_dnsmasq_service():
	p = subprocess.call(["sudo", "systemctl", "stop", "dnsmasq"])
	p = subprocess.call(["sudo", "systemctl", "disable", "dnsmasq"])
	time.sleep(SERVICE_WAIT_TIME)
	#print_to_file("Dnsmasq service deactivated.")


def force_wlan0_reset():
	print_to_file("forcing wlan0 reset")
	subprocess.call(["sudo", "ip", "link", "set", "wlan0", "down"])
	time.sleep(20)
	subprocess.call(["sudo", "ip", "link", "set", "wlan0", "up"])


def setup_access_point():
	# reset the config file with a static IP
	# first delete anything that was written after #bcMeterConfig
	file = open('/etc/dhcpcd.conf', 'r+')
	data = file.readlines()
	pos = 0
	for line in data:
		pos += len(line)
		if line == '#bcMeterConfig\n':
			file.seek(pos, os.SEEK_SET)
			file.truncate()
			break
	file.close()
	print_to_file("edited dhcpcd")
	process = subprocess.run(['systemctl', 'status', 'dnsmasq'], stdout=subprocess.PIPE)
	if 'active (running)' not in process.stdout.decode('utf-8'):
		activate_dnsmasq_service()
	# rewrite the last 3 lines (always after #bcMeterConfig)
	file = open("/etc/dhcpcd.conf", "a")
	file.write("interface wlan0\n")
	file.write("  static ip_address=192.168.18.8/24\n")
	file.write("  nohook wpa_supplicant")
	file.close()
	print_to_file("started dnsmasq")
	p = subprocess.Popen(["sudo", "systemctl", "daemon-reload"])
	p.communicate()
	print_to_file("daemon reloaded")
	p = subprocess.Popen(["sudo", "service", "dhcpcd", "restart"])
	p.communicate()
	# restart the AP
	p = subprocess.Popen(["sudo", "systemctl", "start", "hostapd"])
	p.communicate()
	print_to_file("hostapd started")

def stop_access_point():
	print_to_file("Stopping access point...")
	p = subprocess.Popen(["sudo", "systemctl", "stop", "hostapd"])
	p.communicate()

def check_connection():
	connection_ok = False
	current_time = 0
	while current_time < 5:
		try:
			socket.setdefaulttimeout(DNS_TIME_OUT)
			socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((DNS_HOST, DNS_PORT))
			connection_ok = True
			break
		except Exception:
			current_time += 1
			time.sleep(1)
	

	
	return connection_ok

def get_uptime():
	with open('/proc/uptime', 'r') as f:
		uptime = float(f.readline().split()[0])
		return uptime
	return None

def get_wifi_credentials():
	#print_to_file('Getting wifi credentials from file')
	try:
		with open(WIFI_CREDENTIALS_FILE) as wifi_file:
			data=json.load(wifi_file)
			return data['wifi_ssid'], data['wifi_pwd']
	except FileNotFoundError as e:
		print_to_file('FileNotFoundError:\n{}'.format(e))
		with open(WIFI_CREDENTIALS_FILE, 'w') as f:
			f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
		os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
	print_to_file("no file/ssid/pwd!")
	return '', ''

def get_wifi_bssid(ssid):
	print_to_file('... Getting wifi bssid for ssid={}'.format(ssid))
	ap_list=[]
	out_newlines=None
	for i in range(5):              #try max 5 times
		print_to_file('\ttrying... {}'.format(i))
		scan_cmd='sudo iw dev wlan0 scan ap-force'
		process = subprocess.Popen([scan_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		out, err = process.communicate()
		if(len(err)==0):                                                #the command did not produce an error so e can process the list of access points
			out_newlines=str(out).replace('\\n', '\n')                  #because of the bytes to str conversion newlines are \\n instead of \n
			break
		else:
			print_to_file('\terror: {}'.format(err))
		time.sleep(2)                                                   #sleep before retrying
		
	if(not out_newlines):                                               #the command produced an error every time, return no bssid
		return None
		
	split_str=re.findall('BSS.*\n.*\n.*\n.*\n.*\n.*\n.*\n.*\n.*SSID.*\n', out_newlines, re.MULTILINE)

	for cell in split_str:     
		ap={}
		ap['bssid']=None
		ap['frequency']=None
		ap['signal']=None
		ap['ssid']=None
		
		m=re.search('BSS\s*([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})', cell)
		if(m):
			ap['bssid']=m.group(1)

		m=re.search('freq:\s*(\d+)', cell)
		if(m):
			ap['frequency']=int(m.group(1))
		
		m=re.search('signal:\s*(-?\d+\.\d+)\s*dBm', cell)
		if(m):
			ap['signal']=float(m.group(1))
		
		m=re.search('SSID:\s*(.+)', cell)
		if(m):
			ap['ssid']=m.group(1)
		
		ap_list.append(ap)

	ap_list=[x for x in ap_list if x['ssid']==ssid]                     #filter for ssid
	
	print_to_file('Access points found for ssid={}:'.format(ssid))
	for ap in ap_list:
		ap_list=[x for x in ap_list if x['frequency']<2500]                 #filter for 2.4 GHz wifi band -> freqs lower than 2500 MHz
		ap_list=sorted(ap_list, key=lambda x: x['signal'], reverse=True)    #sort on signal_level
	
	if(len(ap_list)>0):
		print_to_file('Using access point: {}'.format(ap_list[0]))
		return ap_list[0]['bssid']
	else:
		print_to_file('Did not find any access points')
		return None

stop_bcMeter_service() #if service was enabled and device was not shutdown properly (=service disabled), it will startup immediately even if we dont want to		

print_to_file("Starting new session")

connection_ok= check_connection()

if(connection_ok is False):
	status = STATUS_NOK
	keep_running = False
	print_to_file("no connection on startup, so here is the accesspoint!")
	setup_access_point()
else:
	wifi_ssid, wifi_pwd=get_wifi_credentials()
	if (len(wifi_ssid) > 0):
		print_to_file("online at startup, starting bcMeter service")
		deactivate_dnsmasq_service()
		stop_access_point()
		run_bcMeter_service()
		status = STATUS_OK
	else:
		print_to_file("no wifi credentials given, discarding wpa_supplicant and opening accesspoint")
		file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
		file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
		file.close()
		p = subprocess.Popen(["sudo", "systemctl", "daemon-reload"])
		p.communicate()
		setup_access_point()
		status = STATUS_NOK
		keep_running = False



while True:
	importlib.reload(bcMeterConf)
	uptime=get_uptime()
	if (status == STATUS_NOK) and (bcMeterConf.run_hotspot is False): #no connection but in contious hotspot mode? Dont dare to connect to a wifi!
		if (uptime >=hotspot_maxtime) and (keep_running is False): #make sure to shutdown after 10 minutes but keep running if connection lost for other reasons
			print_to_file("up too long go sleep")
			stop_access_point()
			stop_bcMeter_service()
			os.system("shutdown now -h")
		wifi_ssid, wifi_pwd=get_wifi_credentials()
		if (len(wifi_ssid) > 0) :
			print_to_file("trying to establishing connection to wifi")
			wifi_bssid = None
			# SSID is new, so replace the conf file
			file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
			file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
			file.write("\nnetwork={\n")
			if(not wifi_bssid): 
				file.write("\tssid=\"" + wifi_ssid + "\"\n")
			else:
				file.write("\tbssid=" + wifi_bssid + "\n")
			file.write("\tpsk=\"" + wifi_pwd + "\"\n")
			file.write("\tscan_ssid=1\n")
			file.write("}")
			file.close()
			print_to_file("created wpa_supplicant.conf and stopping hostapd now")
			# stop the AP
			p = subprocess.Popen(["sudo", "systemctl", "stop", "hostapd"])
			p.communicate()
			# remove the static IP  (last 3 lines of dhcpcd.conf file)
			file = open('/etc/dhcpcd.conf', 'r+')
			data = file.readlines()
			pos = 0
			for line in data:
				pos += len(line)
				if line == '#bcMeterConfig\n':
					file.seek(pos, os.SEEK_SET)
					file.truncate()
					break
			file.close()
			p = subprocess.Popen(["sudo", "systemctl", "daemon-reload"])
			p.communicate()

			print_to_file("restarting dhcpd to connect to wifi")
			p = subprocess.Popen(["sudo", "service", "dhcpcd", "restart"])
			p.communicate()
			# wait until the wifi is connected
			wait_time = 10
			print_to_file("dhcpcd is restarting")
			time.sleep(wait_time)
			# check connection
			connection_ok= check_connection()
			try:
				if not connection_ok:
					print_to_file("Connection not OK, retry")
					time.sleep(10)
					connection_ok= check_connection()
					if not connection_ok:
						force_wlan0_reset()
						connection_ok= check_connection()
						if not connection_ok:
							raise Exception
				else:
					stop_access_point()
					status = STATUS_OK
					deactivate_dnsmasq_service()
					print_to_file("Connection OK, starting bcMeter Service")
					keep_running=True
					run_bcMeter_service()
				
			except Exception:
				print_to_file("Connection problems persist")
				file = open("/etc/wpa_supplicant/wpa_supplicant.conf", "w")
				file.write("ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n")
				file.close()
				if (uptime >=hotspot_maxtime):
					print_to_file("shutting down hotspot because more than max tries.")
					stop_access_point()	
				if (uptime <=hotspot_maxtime):
					print_to_file("Deleting wifi credentials")
					with open(WIFI_CREDENTIALS_FILE, 'w') as f:
						f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
					os.chmod(WIFI_CREDENTIALS_FILE, 0o777)
					print_to_file("setting up access point again")
					setup_access_point()
					#print_to_file("rebooting")
					#os.system("sudo reboot now")
					#print_to_file("not rebooted b/c of permissions")
		else:
			print_to_file("checking status of hostapd")
			exit_status = check_exit_status("hostapd")
			print_to_file(exit_status)
			#print_to_file("this should only be readable when hotspot is running and no wifi credentials are entered")
			time.sleep(5)
	else:
		time.sleep(10)
		#print_to_file("checking status")
		#exit_status = check_exit_status("bcMeter")
		#if (exit_status == "killed"):
		#	print_to_file("unintended interruption detected. restarting service")
		#	run_bcMeter_service()
		connection_ok= check_connection()
		if(connection_ok is False):
			status = STATUS_NOK
		else:
			keep_running= True #if connection set up once, do not stop everything later just because for example weak wifi signal. 


