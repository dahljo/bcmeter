#!/usr/bin/env python3
# bcMeter AP Control Loop v2.3.0 2026-01-08 - NetworkManager Edition

import socket
import subprocess
import os
import time
import re
import signal
import json
from datetime import datetime
from threading import Thread, Event

from bcMeter_shared import config_json_handler, check_connection, manage_bcmeter_status, show_display, setup_logging, get_pi_revision, run_command, send_email

ctrl_lp_ver = "2.3.0 2026-01-08"

logger = setup_logging("ap_control_loop")
logger.info(f"bcMeter Network Handler started for {socket.gethostname()} (v{ctrl_lp_ver})")
logger.info(get_pi_revision())

devicename = socket.gethostname()

time_synced = False
in_happy_state = False
last_happy_state_check = 0
internet_wait_start_time = 0
internet_wait_timeout = 120
connection_retries = 0
wifi_recovery_attempts = 0
manage_wifi_guard_until = 0


keep_hotspot_alive_without_successful_connection = 3600

base_dir = "/home/bcmeter" if os.path.isdir("/home/bcmeter") else "/home/bcMeter" if os.path.isdir("/home/bcMeter") else "/home/pi"

AP_CON_NAME = "bcMeter-ap"
STA_CON_NAME = "bcMeter-sta"

last_sta_error = ""
last_sta_error_time = 0
current_datetime_timestamp = time.time()

def sh(cmd, timeout=30):
	try:
		r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
		return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
	except subprocess.TimeoutExpired:
		return 1, "", "timeout"
	except Exception as e:
		return 1, "", str(e)

def nmcli(args, timeout=30):
	return sh(["nmcli", "--colors", "no"] + args, timeout=timeout)

def systemctl(args, timeout=30):
	return sh(["systemctl"] + args, timeout=timeout)

class ServiceManager:
	def __init__(self):
		self.max_retries = 3
		self.service_timeouts = {"bcMeter": 20, "bcMeter_flask": 10, "NetworkManager": 20}

	def check_running(self, service_name, wait_for_state=None, timeout=None):
		timeout = timeout or self.service_timeouts.get(service_name, 10)
		if wait_for_state is None:
			rc, out, _ = systemctl(["is-active", service_name], timeout=timeout)
			return rc == 0 and out.strip() == "active"
		start = time.time()
		while time.time() - start < timeout:
			rc, out, _ = systemctl(["is-active", service_name], timeout=timeout)
			state = out.strip()
			if wait_for_state == "active" and state == "active":
				return True
			if wait_for_state == "inactive" and state in ("inactive", "failed", "unknown"):
				return True
			time.sleep(0.5)
		return False

	def start_service(self, service_name):
		for _ in range(self.max_retries):
			run_command(f"sudo systemctl start {service_name}")
			if self.check_running(service_name, wait_for_state="active"):
				return True
			time.sleep(2)
		return False

	def stop_service(self, service_name):
		for _ in range(self.max_retries):
			run_command(f"sudo systemctl stop {service_name}")
			if self.check_running(service_name, wait_for_state="inactive"):
				run_command(f"sudo systemctl reset-failed {service_name}")
				return True
			time.sleep(2)
		run_command(f"sudo systemctl reset-failed {service_name}")
		return True

	def restart_service(self, service_name):
		self.stop_service(service_name)
		time.sleep(1)
		return self.start_service(service_name)

class WifiManager:
	def __init__(self):
		self.credentials_file = os.path.join(base_dir, "bcMeter_wifi.json")
		self.max_connection_retries = 3

	def validate_credentials(self, ssid, pwd):
		if ssid is None or pwd is None:
			return False
		if not (1 <= len(ssid) <= 32):
			return False
		if not (8 <= len(pwd) <= 63):
			return False
		if not all(32 <= ord(c) <= 126 for c in pwd):
			return False
		return True

	def get_credentials(self):
		try:
			with open(self.credentials_file) as f:
				data = json.load(f)
			ssid = data.get("wifi_ssid")
			pwd = data.get("wifi_pwd")
			if not self.validate_credentials(ssid, pwd):
				return None, None
			return ssid, pwd
		except Exception:
			return None, None

	def delete_credentials(self):
		try:
			with open(self.credentials_file, "w") as f:
				f.write('{\n\t"wifi_ssid": "",\n\t"wifi_pwd": ""\n}')
			os.chmod(self.credentials_file, 0o777)
		except Exception:
			pass
		logger.debug("Reset WiFi Configs")

	def get_current_network(self):
		rc, out, _ = nmcli(["-t", "-f", "ACTIVE,SSID", "dev", "wifi"], timeout=15)
		if rc == 0:
			for line in out.splitlines():
				parts = line.split(":", 1)
				if len(parts) == 2 and parts[0] == "yes":
					return parts[1] or None
		for _ in range(3):
			try:
				ssid = subprocess.check_output(["iwgetid", "-r"], timeout=5).decode("utf-8").strip()
				if ssid:
					return ssid
			except Exception:
				pass
			time.sleep(1)
		return None

	def get_best_signal_for_ssid(self, wifi_name, do_rescan=True):
		if not wifi_name:
			return None
		if do_rescan:
			nmcli(["dev", "wifi", "rescan"], timeout=15)
			time.sleep(2)
		rc, out, _ = nmcli(["-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list"], timeout=15)
		if rc != 0:
			return None
		best = None
		for line in out.splitlines():
			parts = line.split(":", 1)
			if len(parts) != 2:
				continue
			ssid, sig = parts[0].strip().replace(r"\:", ":"), parts[1].strip()
			if ssid != wifi_name:
				continue
			try:
				p = int(sig)
			except Exception:
				continue
			if best is None or p > best:
				best = p
		if best is None:
			return None
		dbm = int((best / 1.42) - 110)
		return {"ssid": wifi_name, "signal_percent": best, "signal_dbm": dbm}

	def is_ssid_in_range(self, wifi_name):
		return self.get_best_signal_for_ssid(wifi_name, do_rescan=True) is not None

	def check_connection_quality(self, ssid=None):
		try:
			cmd = ["nmcli", "-t", "-f", "ACTIVE,SIGNAL,SSID", "dev", "wifi"]
			rc, out, _ = sh(cmd, timeout=10)
			if rc != 0:
				return None
			for line in out.splitlines():
				if line.startswith("yes:"):
					parts = line.split(":", 2)
					if len(parts) < 3:
						continue
					_, signal_str, current_ssid = parts
					current_ssid = current_ssid.replace(r"\:", ":")
					if ssid and current_ssid != ssid:
						return None
					try:
						signal_percent = int(signal_str)
						signal_dbm = int((signal_percent / 1.42) - 110)
					except ValueError:
						return None
					return {"ssid": current_ssid, "signal": signal_dbm, "signal_percent": signal_percent, "is_stable": signal_percent > 30}
			return None
		except Exception as e:
			logger.error(f"Error checking WiFi quality via nmcli: {e}")
			return None


def set_regulatory_domain(config):
	country = config.get('country', 'DE')
	if not country or len(country) != 2:
		country = 'DE'

	try:
		subprocess.run(['sudo', 'iw', 'reg', 'set', country], check=True)
		return True
	except Exception as e:
		logger.error(f"Failed to set regulatory domain: {e}")
		return False


def ensure_nm_ready():
	sm = ServiceManager()
	if not sm.check_running("NetworkManager"):
		sm.start_service("NetworkManager")
		time.sleep(2)
	ok = False
	for _ in range(20):
		rc, out, _ = nmcli(["-t", "-f", "RUNNING", "general"], timeout=5)
		if rc == 0 and out.strip().lower() == "running":
			ok = True
			break
		time.sleep(0.5)
	if not ok:
		rc, out, err = nmcli(["general", "status"], timeout=10)
		logger.warning(f"NetworkManager not confirmed running (rc={rc}) out={out} err={err}")
	rc, out, _ = nmcli(["-g", "GENERAL.STATE", "dev", "show", "wlan0"], timeout=10)
	if "unmanaged" in out.lower():
		nmcli(["dev", "set", "wlan0", "managed", "yes"], timeout=10)
		time.sleep(1)
	nmcli(["radio", "wifi", "on"], timeout=10)


def list_connections():
	rc, out, _ = nmcli(["-t", "-f", "NAME", "con", "show"], timeout=20)
	if rc != 0:
		return set()
	return {x.strip() for x in out.splitlines() if x.strip()}

def active_connection_name(ifname="wlan0"):
	rc, out, _ = nmcli(["-g", "GENERAL.CONNECTION", "dev", "show", ifname], timeout=15)
	if rc != 0:
		return None
	v = out.strip()
	return v if v and v != "--" else None

def con_up(name, timeout=45):
	global last_sta_error, last_sta_error_time
	con_down_all_wifi()
	time.sleep(1)
	rc, out, err = nmcli(["-w", str(timeout), "con", "up", name], timeout=timeout + 10)
	if rc != 0:
		last_sta_error = err or out
		last_sta_error_time = time.time()
		logger.warning(f"nmcli con up {name} failed: {last_sta_error}")
		return False
	time.sleep(2)
	return True

def con_down(name):
	nmcli(["con", "down", name], timeout=20)

def con_down_all_wifi():
	rc, out, _ = nmcli(["-t", "-f", "NAME,TYPE", "con", "show", "--active"], timeout=15)
	if rc == 0:
		for line in out.splitlines():
			parts = line.split(":")
			if len(parts) >= 2 and "wireless" in parts[1]:
				nmcli(["con", "down", parts[0]], timeout=10)

def con_delete(name):
	nmcli(["con", "delete", name], timeout=20)

def dev_has_non_linklocal_ip(ifname="wlan0"):
	rc, out, _ = nmcli(["-g", "IP4.ADDRESS", "dev", "show", ifname], timeout=10)
	if rc != 0:
		return False
	for line in out.splitlines():
		ip = line.split("/")[0].strip()
		if ip and not ip.startswith("169.254."):
			return True
	return False

def setup_access_point():
	logger.info("Setting up Access Point...")
	ensure_nm_ready()
	cfg = config_json_handler()
	ap_ssid = cfg.get("ap_ssid") or devicename or "bcMeter"
	ap_psk = cfg.get("ap_password") or "bcMeterbcMeter"
	ap_ip = cfg.get("ap_ip_cidr") or "192.168.18.8/24"
	ap_channel = str(cfg.get("ap_channel") or "7")
	con_down_all_wifi()
	time.sleep(1)
	cons = list_connections()
	if AP_CON_NAME in cons:
		con_delete(AP_CON_NAME)
		time.sleep(1)
	rc, _, err = nmcli([
		"con", "add",
		"type", "wifi",
		"ifname", "wlan0",
		"con-name", AP_CON_NAME,
		"ssid", ap_ssid,
		"autoconnect", "no",
		"wifi.mode", "ap",
		"wifi.band", "bg",
		"wifi.channel", ap_channel,
		"ipv4.method", "shared",
		"ipv4.addresses", ap_ip,
		"ipv6.method", "disabled",
		"wifi-sec.key-mgmt", "wpa-psk",
		"wifi-sec.psk", ap_psk
	], timeout=30)
	if rc != 0:
		logger.error(f"Failed to create AP profile: {err}")
		return False
	time.sleep(1)
	rc, out, err = nmcli(["-w", "30", "con", "up", AP_CON_NAME], timeout=40)
	if rc != 0:
		logger.error(f"Failed to activate AP: {err}")
		return False
	time.sleep(3)
	active = active_connection_name("wlan0")
	if active == AP_CON_NAME:
		logger.info(f"Hotspot active: SSID={ap_ssid}")
		show_display("Hotspot", True, 0)
		show_display(ap_ssid, False, 1)
		return True
	logger.error("AP activation verification failed")
	return False

def stop_access_point(reason=None):
	if reason:
		logger.debug(f"Stopping hotspot: {reason}")
	con_down(AP_CON_NAME)
	return True

def ensure_sta_profile(wifi_ssid, wifi_pwd):
	cons = list_connections()
	if STA_CON_NAME in cons:
		con_delete(STA_CON_NAME)
		time.sleep(1)
	rc, _, err = nmcli([
		"con", "add",
		"type", "wifi",
		"ifname", "wlan0",
		"con-name", STA_CON_NAME,
		"ssid", wifi_ssid,
		"autoconnect", "no",
		"wifi.mode", "infrastructure",
		"ipv4.method", "auto",
		"ipv6.method", "disabled",
		"wifi-sec.key-mgmt", "wpa-psk",
		"wifi-sec.psk", wifi_pwd
	], timeout=30)
	if rc != 0:
		logger.error(f"Failed to create STA profile: {err}")
		return False
	return True

def get_default_gateway():
	rc, out, _ = sh(["ip", "route", "show", "default"], timeout=5)
	if rc != 0:
		return None
	m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
	return m.group(1) if m else None

def ping_router():
	gw = get_default_gateway()
	if not gw:
		return False
	rc, _, _ = sh(["ping", "-c", "1", "-W", "2", gw], timeout=5)
	return rc == 0

def force_wlan0_reset():
	logger.debug("Resetting wlan0 interface")
	try:
		con_down_all_wifi()
		time.sleep(1)
		run_command("sudo ip link set wlan0 down")
		time.sleep(2)
		run_command("sudo ip link set wlan0 up")
		time.sleep(3)
		nmcli(["dev", "set", "wlan0", "managed", "yes"], timeout=10)
		time.sleep(2)
		return True
	except Exception:
		return False

def reload_wifi_driver():
	logger.debug("Reloading WiFi driver")
	try:
		con_down_all_wifi()
		run_command("sudo modprobe -r brcmfmac")
		time.sleep(3)
		run_command("sudo modprobe brcmfmac")
		time.sleep(5)
		nmcli(["dev", "set", "wlan0", "managed", "yes"], timeout=10)
		return is_wifi_driver_loaded()
	except Exception:
		return False

def is_wifi_driver_loaded():
	try:
		rc, out, _ = sh(["ip", "link", "show", "wlan0"], timeout=5)
		return rc == 0 and "wlan0" in out
	except Exception:
		return False

def get_uptime():
	try:
		with open("/proc/uptime") as f:
			return int(float(f.read().split()[0]))
	except Exception:
		return 0

def check_time_sync():
	try:
		if datetime.now().year > 2024:
			return True
		rc, out, _ = sh(["timedatectl", "status"], timeout=10)
		return rc == 0 and "System clock synchronized: yes" in out
	except Exception:
		return False

def time_sync_check_loop(stop_event):
	global time_synced
	while not stop_event.is_set():
		time_synced = check_time_sync()
		if time_synced:
			logger.debug("Time synchronized")
			stop_event.set()
		else:
			time.sleep(120)

def verify_dhcp_lease():
	return dev_has_non_linklocal_ip("wlan0")

def check_for_psk_errors():
	global last_sta_error, last_sta_error_time
	now = time.time()
	if last_sta_error and now - last_sta_error_time < 120:
		pats = [
			r"secrets were required",
			r"no secrets",
			r"psk.*invalid",
			r"wrong.*key",
			r"auth.*fail"
		]
		for p in pats:
			if re.search(p, last_sta_error, re.IGNORECASE):
				return True
	try:
		rc, out, _ = sh(["journalctl", "-u", "NetworkManager", "--since", "2 min ago", "-n", "50", "--no-pager"], timeout=10)
		if rc != 0:
			return False
		pats2 = [
			r"secrets were required",
			r"no secrets provided",
			r"password.*incorrect",
			r"wrong.*key",
			r"auth.*fail"
		]
		for line in out.splitlines():
			for p in pats2:
				if re.search(p, line, re.IGNORECASE):
					return True
		return False
	except Exception:
		return False

def evaluate_wifi_quality(signal_dbm):
	if signal_dbm is None:
		return 0
	if signal_dbm >= -55:
		quality = 4
	elif signal_dbm >= -65:
		quality = 3
	elif signal_dbm >= -75:
		quality = 2
	elif signal_dbm >= -85:
		quality = 1
	else:
		quality = 0
	return quality

def check_happy_state(wifi_ssid):
	if not wifi_ssid:
		return False
	wm = WifiManager()
	current_network = wm.get_current_network()
	if current_network != wifi_ssid:
		return False
	is_online = check_connection()
	if not is_online:
		if ping_router():
			return True
		return False
	if active_connection_name("wlan0") == AP_CON_NAME:
		return False
	return True

def handle_exit_from_happy_state(wifi_ssid):
	global in_happy_state, internet_wait_start_time
	logger.info("Happy state disturbed - analyzing")
	in_happy_state = False
	if not is_wifi_driver_loaded():
		logger.error("WiFi driver not loaded")
		if not reload_wifi_driver():
			setup_access_point()
		return
	wm = WifiManager()
	current_network = wm.get_current_network()
	is_online = check_connection()
	if current_network == wifi_ssid and not is_online:
		logger.debug("Connected but no internet")
		if ping_router():
			show_display("WiFi OK", False, 0)
			show_display("No Internet", False, 1)
			internet_wait_start_time = time.time()
			return
		logger.warning("Router unreachable")
		current_time = time.time()
		if internet_wait_start_time == 0:
			internet_wait_start_time = current_time
		elif current_time - internet_wait_start_time > internet_wait_timeout:
			internet_wait_start_time = 0
			manage_wifi("connectivity_timeout")
			return
		wifi_quality = wm.check_connection_quality(wifi_ssid)
		if wifi_quality and wifi_quality.get("signal") is not None:
			if evaluate_wifi_quality(wifi_quality["signal"]) <= 1:
				internet_wait_start_time = 0
				manage_wifi("poor_signal")
				return
	elif current_network != wifi_ssid:
		internet_wait_start_time = 0
		manage_wifi("network_change")
	else:
		internet_wait_start_time = 0
		manage_wifi("unknown_issue")

def stop_bcMeter_service(reason=None):
	if reason:
		logger.debug(f"Stopping bcMeter: {reason}")
	run_command("sudo systemctl stop bcMeter")

def run_bcMeter_service(reason=None):
	if reason:
		logger.debug(f"Starting bcMeter: {reason}")
	run_command("sudo systemctl start bcMeter")

def manage_wifi(checkpoint=None):
	global wifi_recovery_attempts, in_happy_state, connection_retries, manage_wifi_guard_until
	now = time.time()
	if now < manage_wifi_guard_until:
		logger.debug(f"manage_wifi: suppressed ({checkpoint})")
		return
	manage_wifi_guard_until = now + 8

	config = config_json_handler()
	is_ebcMeter = config.get("is_ebcMeter", False)
	run_hotspot_flag = config.get("run_hotspot", False)
	min_signal_percent = int(config.get("min_wifi_signal_percent", 20))
	sm = ServiceManager()
	wm = WifiManager()
	wifi_ssid, wifi_pwd = wm.get_credentials()
	bcMeter_running = sm.check_running("bcMeter")
	current_network = wm.get_current_network()
	is_online = check_connection()

	q = wm.check_connection_quality()
	if q and q.get("ssid"):
		logger.debug(f"wifi_status: ssid={q.get('ssid')} signal_percent={q.get('signal_percent')} signal_dbm={q.get('signal')} online={is_online}")
	else:
		logger.debug(f"wifi_status: ssid={current_network} online={is_online}")
	logger.debug(f"manage_wifi: {checkpoint}")

	if (not wifi_ssid or not wifi_pwd) or run_hotspot_flag:
		if active_connection_name("wlan0") != AP_CON_NAME:
			logger.debug("Setting up Hotspot")
			if not setup_access_point():
				force_wlan0_reset()
				time.sleep(5)
				setup_access_point()
		return

	if current_network == wifi_ssid and (is_online or ping_router()):
		connection_retries = 0
		wifi_recovery_attempts = 0
		if active_connection_name("wlan0") == AP_CON_NAME:
			stop_access_point("connected")
		if not bcMeter_running and manage_bcmeter_status(action="get", parameter="bcMeter_status") not in (5, 6):
			if manage_bcmeter_status(action="get", parameter="filter_status") > 3 and not is_ebcMeter:
				run_bcMeter_service("Online")
		in_happy_state = True
		return

	if current_network == wifi_ssid and not is_online and ping_router():
		connection_retries = 0
		wifi_recovery_attempts = 0
		if active_connection_name("wlan0") == AP_CON_NAME:
			stop_access_point("router ok")
		in_happy_state = True
		return

	scan = wm.get_best_signal_for_ssid(wifi_ssid, do_rescan=True)
	if scan:
		logger.debug(f"ssid_scan: ssid={wifi_ssid} signal_percent={scan['signal_percent']} signal_dbm={scan['signal_dbm']}")
		if scan["signal_percent"] < min_signal_percent:
			logger.warning(f"ssid_scan: ssid={wifi_ssid} signal_percent={scan['signal_percent']} below_min={min_signal_percent}")
			if active_connection_name("wlan0") != AP_CON_NAME:
				setup_access_point()
			return
	else:
		if active_connection_name("wlan0") != AP_CON_NAME:
			setup_access_point()
		return

	was_ap_active = active_connection_name("wlan0") == AP_CON_NAME
	if was_ap_active:
		if not stop_access_point("pre-STA"):
			force_wlan0_reset()
			setup_access_point()
			return

	if not ensure_sta_profile(wifi_ssid, wifi_pwd):
		setup_access_point()
		return

	ok = con_up(STA_CON_NAME, timeout=45)
	time.sleep(2)

	connected = False
	for _ in range(10):
		if wm.get_current_network() == wifi_ssid:
			connected = True
			break
		time.sleep(2)

	if not ok or not connected:
		connection_retries += 1
		wifi_recovery_attempts += 1
		if check_for_psk_errors():
			wm.delete_credentials()
			setup_access_point()
			return
		if was_ap_active:
			setup_access_point()
		else:
			if connection_retries >= wm.max_connection_retries:
				connection_retries = 0
				setup_access_point()
		return

	if not verify_dhcp_lease():
		connection_retries += 1
		if was_ap_active:
			setup_access_point()
			return
		if connection_retries >= wm.max_connection_retries:
			connection_retries = 0
			setup_access_point()
		return

	wifi_quality = wm.check_connection_quality(wifi_ssid)
	if wifi_quality:
		logger.debug(f"sta_quality: ssid={wifi_quality.get('ssid')} signal_percent={wifi_quality.get('signal_percent')} signal_dbm={wifi_quality.get('signal')} stable={wifi_quality.get('is_stable')}")
	if wifi_quality and wifi_quality.get("is_stable"):
		connection_retries = 0
		wifi_recovery_attempts = 0
		if not bcMeter_running and manage_bcmeter_status(action="get", parameter="bcMeter_status") not in (5, 6):
			if manage_bcmeter_status(action="get", parameter="filter_status") > 3 and not is_ebcMeter:
				run_bcMeter_service("Stable WiFi")
		in_happy_state = True
		return

	in_happy_state = False
	return


def handle_exit_signal(signum, frame):
	logger.info("Shutdown signal received")
	try:
		stop_access_point("exit")
	except Exception:
		pass
	try:
		con_down(STA_CON_NAME)
	except Exception:
		pass
	raise SystemExit(0)

def ap_control_loop():
	global time_synced, in_happy_state, last_happy_state_check, internet_wait_start_time
	sm = ServiceManager()
	wm = WifiManager()
	if manage_bcmeter_status(action="get", parameter="bcMeter_status") not in (5, 6):
		manage_bcmeter_status(action="set", bcMeter_status=4)
	config = config_json_handler()
	scan_interval = 5
	happy_state_check_interval = 20
	router_check_interval = 40
	last_router_check = 0
	run_hotspot_flag = config.get("run_hotspot", False)
	is_ebcMeter = config.get("is_ebcMeter", False)
	was_offline = True
	router_reachable = False

	config = config_json_handler()
	enable_wifi = config.get('enable_wifi', True)

	if not enable_wifi:
		logger.info("WiFi disabled in config")
		run_command("nmcli radio wifi off")
		import sys
		sys.exit(0)

	run_command("nmcli radio wifi on")
	set_regulatory_domain(config)

	ensure_nm_ready()
	wifi_ssid, _ = wm.get_credentials()
	if not wifi_ssid or not wm.is_ssid_in_range(wifi_ssid):
		logger.debug("Initial: No WiFi, starting hotspot")
		if not setup_access_point():
			force_wlan0_reset()
			time.sleep(5)
			setup_access_point()
	else:
		manage_wifi(1)
	stop_time_sync_thread = Event()
	time_sync_thread = Thread(target=time_sync_check_loop, args=(stop_time_sync_thread,))
	time_sync_thread.daemon = True
	time_sync_thread.start()
	calibration_time = manage_bcmeter_status(action="get", parameter="calibration_time")
	signal.signal(signal.SIGINT, handle_exit_signal)
	signal.signal(signal.SIGTERM, handle_exit_signal)
	signal.signal(signal.SIGHUP, handle_exit_signal)
	try:
		while True:
			try:
				config = config_json_handler()
				run_hotspot_flag = config.get("run_hotspot", False)
				is_online = check_connection()
				bcMeter_running = sm.check_running("bcMeter")
				ap_active = active_connection_name("wlan0") == AP_CON_NAME
				is_ebcMeter = config.get("is_ebcMeter", False)
				current_network = wm.get_current_network()
				wifi_ssid, _ = wm.get_credentials()
				current_time = time.time()
				if current_network and not is_online and not ap_active and internet_wait_start_time > 0:
					if current_time - internet_wait_start_time > internet_wait_timeout:
						logger.warning("Connectivity timeout")
						internet_wait_start_time = 0
						manage_wifi("timeout")
						continue
				if current_network and not is_online and not ap_active:
					if current_time - last_router_check > router_check_interval:
						last_router_check = current_time
						router_reachable = ping_router()
						if router_reachable:
							show_display("WiFi OK", False, 0)
							show_display("No Internet", False, 1)
						else:
							wifi_quality = wm.check_connection_quality(wifi_ssid)
							if wifi_quality and wifi_quality.get("signal") is not None:
								if evaluate_wifi_quality(wifi_quality["signal"]) <= 1:
									manage_wifi("poor_signal")
									continue
							if not in_happy_state and internet_wait_start_time == 0:
								manage_wifi("router_unreachable")
				if in_happy_state:
					if current_time - last_happy_state_check > happy_state_check_interval:
						last_happy_state_check = current_time
						if not check_happy_state(wifi_ssid):
							handle_exit_from_happy_state(wifi_ssid)
					else:
						time.sleep(scan_interval)
						continue
				if not is_wifi_driver_loaded():
					logger.error("WiFi driver not loaded")
					if not reload_wifi_driver():
						setup_access_point()
					continue
				if current_network != wifi_ssid and wifi_ssid and not ap_active:
					manage_wifi(2)
				current_status = manage_bcmeter_status(action="get", parameter="bcMeter_status")
				in_hotspot = run_hotspot_flag or ap_active
				if in_hotspot:
					current_status = 3 if bcMeter_running else 4
				elif is_online:
					if bcMeter_running:
						current_status = 2
					else:
						if current_status in (5, 6):
							pass
						elif (manage_bcmeter_status(action="get", parameter="filter_status") > 3) and calibration_time is not None and not is_ebcMeter:
							run_bcMeter_service(f"Status {current_status}")
							current_status = 2
						else:
							current_status = 0
				else:
					if current_status not in (5, 6):
						current_status = 0
				manage_bcmeter_status(action="set", bcMeter_status=current_status, in_hotspot=in_hotspot)
				if is_online:
					if was_offline:
						try:
							send_email("Onboarding")
						except Exception as e:
							logger.error(f"Onboarding email failed: {e}")
						was_offline = False
				else:
					if was_offline and bool(config.get("iot_enable", False)):
						try:
							send_email("Onboarding")
							was_offline = False
						except Exception as e:
							logger.debug(f"IoT onboarding attempt: {e}")
				if not is_online and not run_hotspot_flag:
					uptime = get_uptime() if time_synced else keep_hotspot_alive_without_successful_connection - 1
					if uptime >= keep_hotspot_alive_without_successful_connection:
						if not (is_ebcMeter or bcMeter_running):
							show_display("No Config", False, 0)
							if not ap_active:
								setup_access_point()
				if ap_active and wifi_ssid:
					if int(time.time()) % 60 < scan_interval:
						if wm.is_ssid_in_range(wifi_ssid):
							logger.debug(f"Network {wifi_ssid} detected")
							manage_wifi("periodic_reconnect")
				time.sleep(scan_interval)
			except Exception as e:
				logger.error(f"Loop error: {e}")
				time.sleep(5)
				continue
	except Exception as e:
		logger.error(f"Control loop exception: {e}")
		handle_exit_signal(signal.SIGTERM, None)

if not is_wifi_driver_loaded():
	logger.error("WiFi driver not loaded at startup")
	if not reload_wifi_driver():
		logger.critical("Cannot load WiFi driver")
		raise SystemExit(1)

ap_control_loop()