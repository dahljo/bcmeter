#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import time
import argparse
import re
import urllib.request
from pathlib import Path

INSTALLER_VERSION = "2.7.2 2026-05-15"
REPO_URL = "https://github.com/dahljo/bcmeter.git"
RAW_VERSION_URL = "https://raw.githubusercontent.com/dahljo/bcmeter/main/bcMeter.py"

APT_PACKAGES = [
	"build-essential", "git", "rsync", "rsyslog", "screen", "rfkill", "openssl",
	"iptables", "zram-tools", "avahi-daemon",
	"network-manager", "wireless-tools", "net-tools",
	"nginx", "php-fpm", "php-cli", "php-common",
	"python3-pip", "python3-dev", "python3-venv",
	"python3-numpy", "python3-pil",
	"python3-flask", "python3-smbus", "python3-rpi.gpio", "python3-spidev",
	"python3-libgpiod", "i2c-tools"
]

VENV_ONLY_PACKAGES = [
	"adafruit-blinka",
	"adafruit-circuitpython-sht4x",
	"oled-text",
	"flask-cors",
	"smbus2",
	"pyserial"
]

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
MAINTENANCE_LOG_DIR = BASE_DIR / "maintenance_logs"
INSTALL_LOG = MAINTENANCE_LOG_DIR / "bcMeter_install.log"
LEGACY_NOTICE_FLAG = MAINTENANCE_LOG_DIR / "legacy_redesign_notice.flag"
UPDATING_FLAG = Path("/tmp/bcmeter_updating")
SYSTEMD_ETC = Path("/etc/systemd/system")


def run_cmd(cmd, shell=False, ignore_error=False, **kwargs):
	try:
		if shell:
			subprocess.run(cmd, shell=True, check=True, executable="/bin/bash", **kwargs)
		else:
			subprocess.run(cmd, check=True, **kwargs)
	except subprocess.CalledProcessError:
		if not ignore_error:
			sys.exit(1)


def write_file(path, content, mode="w"):
	Path(path).parent.mkdir(parents=True, exist_ok=True)
	with open(path, mode) as f:
		f.write(content)


def append_if_missing(path, text):
	path = Path(path)
	if not path.exists():
		write_file(path, text + "\n")
		return
	current_content = path.read_text(errors="ignore")
	if text.strip() not in current_content:
		with open(path, "a") as f:
			f.write("\n" + text + "\n")


def setup_logging():
	MAINTENANCE_LOG_DIR.mkdir(parents=True, exist_ok=True)
	with open(INSTALL_LOG, "a") as f:
		f.write(f"{time.ctime()} installation/update log\n")


def log(message):
	print(message)
	with open(INSTALL_LOG, "a") as f:
		f.write(f"{message}\n")
		f.flush()
		os.fsync(f.fileno())


def mark_legacy_notice_pending():
	MAINTENANCE_LOG_DIR.mkdir(parents=True, exist_ok=True)
	LEGACY_NOTICE_FLAG.write_text(f"{time.ctime()} legacy repository update completed\n")
	log("Legacy repository notice will be shown in the web interface after reboot.")


def is_chroot_mode(mode: str):
	return mode == "chroot"


def systemd_online(mode: str):
	if is_chroot_mode(mode):
		return False
	if os.environ.get("SYSTEMD_OFFLINE") == "1":
		return False
	return Path("/run/systemd/system").exists()


def unit_file_path(unit: str):
	candidates = [
		SYSTEMD_ETC / unit,
		Path("/lib/systemd/system") / unit,
		Path("/usr/lib/systemd/system") / unit,
	]
	for c in candidates:
		if c.exists():
			return c
	return None


def disable_unit_fs(unit: str):
	for p in SYSTEMD_ETC.glob(f"*.wants/{unit}"):
		try:
			if p.exists() or p.is_symlink():
				p.unlink()
		except:
			pass
	for p in SYSTEMD_ETC.glob(f"*.requires/{unit}"):
		try:
			if p.exists() or p.is_symlink():
				p.unlink()
		except:
			pass


def enable_unit_fs(unit: str):
	target = unit_file_path(unit)
	if target is None:
		return
	wants_dir = SYSTEMD_ETC / "multi-user.target.wants"
	wants_dir.mkdir(parents=True, exist_ok=True)
	link = wants_dir / unit
	try:
		if link.exists() or link.is_symlink():
			link.unlink()
	except:
		pass
	try:
		link.symlink_to(target)
	except:
		pass


def mask_unit_fs(unit: str):
	SYSTEMD_ETC.mkdir(parents=True, exist_ok=True)
	mask_path = SYSTEMD_ETC / unit
	try:
		if mask_path.is_symlink() or mask_path.exists():
			mask_path.unlink()
	except:
		pass
	try:
		mask_path.symlink_to("/dev/null")
	except:
		pass
	disable_unit_fs(unit)


def unmask_unit_fs(unit: str):
	p = SYSTEMD_ETC / unit
	try:
		if p.is_symlink() and os.readlink(p) == "/dev/null":
			p.unlink()
	except:
		pass


def get_local_version():
	local_file = BASE_DIR / "bcMeter.py"
	if local_file.exists():
		try:
			with open(local_file) as f:
				for line in f:
					if "bcMeter_version" in line:
						return line.split('"')[1]
		except:
			pass
	return "0.0.0"


def get_remote_version():
	try:
		with urllib.request.urlopen(RAW_VERSION_URL, timeout=5) as response:
			content = response.read().decode("utf-8")
			for line in content.splitlines():
				if "bcMeter_version" in line:
					return line.split('"')[1]
	except:
		return "0.0.0"


def version_tuple(version):
	m = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)", str(version or ""))
	if not m:
		return (0, 0, 0)
	return tuple(int(part) for part in m.groups())


def cleanup_legacy_install():
	venv_dir = BASE_DIR / "venv"
	if venv_dir.exists():
		log("Venv detected; skipping system-wide pip cleanup.")
		return
	log("Legacy install detected (no venv); removing conflicting system-wide Python packages...")
	pip = shutil.which("pip3")
	if not pip:
		log("pip3 not found; skipping system-wide pip cleanup.")
		return
	pkgs = " ".join(VENV_ONLY_PACKAGES)
	run_cmd(f"{pip} uninstall -y {pkgs} --break-system-packages", shell=True, ignore_error=True)


def ensure_codebase_state(force=False):
	UPDATING_FLAG.touch()
	try:
		local_ver = get_local_version()
		remote_ver = get_remote_version()
		log(f"Version Check: Local={local_ver} | Remote={remote_ver}")

		needs_update = False
		if force:
			log("Force update requested")
			needs_update = True
		elif local_ver == "0.0.0":
			log("No local version found. Installing...")
			needs_update = True
		elif version_tuple(remote_ver) > version_tuple(local_ver):
			log(f"Running update... (New: {remote_ver})")
			needs_update = True
		else:
			log("Most recent version installed")
			needs_update = False

		if needs_update:
			log("Backing up config (not touching logs)...")
			backup_dir = BASE_DIR / ".config_backup"
			backup_dir.mkdir(exist_ok=True)

			for json_file in ["bcMeter_config.json", "bcMeter_wifi.json"]:
				src = BASE_DIR / json_file
				if src.exists():
					shutil.copy2(src, backup_dir / json_file)

			log("Fetching latest bcMeter repository...")
			tmp_repo = BASE_DIR / "bcmeter_tmp"
			if tmp_repo.exists():
				shutil.rmtree(tmp_repo)
			run_cmd(f"git clone --depth 1 {REPO_URL} {tmp_repo}", shell=True)

			for d in ["bcmeter", "interface"]:
				p = BASE_DIR / d
				if p.exists():
					shutil.rmtree(p)

			run_cmd(f"rsync -a --delete --exclude=venv/ --exclude=logs/ --exclude=maintenance_logs/ {tmp_repo}/ {BASE_DIR}/", shell=True)
			shutil.rmtree(tmp_repo, ignore_errors=True)
			shutil.rmtree(BASE_DIR / "gerbers", ignore_errors=True)
			shutil.rmtree(BASE_DIR / "stl", ignore_errors=True)

			log("Restoring config...")
			for json_file in ["bcMeter_config.json", "bcMeter_wifi.json"]:
				bak = backup_dir / json_file
				if bak.exists():
					shutil.move(bak, BASE_DIR / json_file)
			shutil.rmtree(backup_dir, ignore_errors=True)

			app_user = BASE_DIR.name
			run_cmd(f"chown -R {app_user}:{app_user} {BASE_DIR}", shell=True, ignore_error=True)

		return needs_update
	finally:
		if UPDATING_FLAG.exists():
			UPDATING_FLAG.unlink()

def repair_dpkg_state():
	updates_dir = Path("/var/lib/dpkg/updates")
	backup_dir = Path("/root/bcmeter_dpkg_updates_backup")

	if updates_dir.exists():
		backup_dir.mkdir(parents=True, exist_ok=True)
		for f in sorted(updates_dir.glob("[0-9][0-9][0-9][0-9]")):
			try:
				shutil.copy2(f, backup_dir / f.name)
			except Exception:
				pass
			try:
				f.unlink()
			except Exception:
				pass

	for _ in range(5):
		p = subprocess.run(
			["dpkg", "--configure", "-a"],
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			errors="replace",
		)
		if p.returncode == 0:
			return True

		m = re.search(r"parsing file '(/var/lib/dpkg/updates/\d+)'", p.stderr)
		if not m:
			return False

		bad = Path(m.group(1))
		if bad.exists():
			backup_dir.mkdir(parents=True, exist_ok=True)
			try:
				shutil.copy2(bad, backup_dir / bad.name)
			except Exception:
				pass
			try:
				bad.unlink()
			except Exception:
				pass

	return False



def system_setup(mode: str, noupgrade=False):
	run_cmd("rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*", shell=True, ignore_error=True)

	#log("Repairing dpkg/apt state...")
	#repair_dpkg_state()
	run_cmd("dpkg --configure -a", shell=True, ignore_error=True)
	run_cmd("apt -f install -y", shell=True, ignore_error=True)

	log("Updating package lists...")
	run_cmd("rm -rf /var/lib/apt/lists/*", shell=True, ignore_error=True)
	run_cmd(["apt", "update", "-y"])

	log("Fixing broken deps (pre)...")
	run_cmd(["apt", "--fix-broken", "install", "-y"], ignore_error=True)

	if not noupgrade:
		log("Upgrading base system...")
		run_cmd(["apt", "upgrade", "-y"])

	log("Installing system dependencies...")
	run_cmd(["apt", "install", "-y"] + APT_PACKAGES)

	log("Fixing broken deps (post)...")
	run_cmd(["apt", "--fix-broken", "install", "-y"], ignore_error=True)

	log("Removing known-unwanted packages...")
	run_cmd("apt purge -y cloud-init", shell=True, ignore_error=True)
	shutil.rmtree("/etc/cloud", ignore_errors=True)
	shutil.rmtree("/var/lib/cloud", ignore_errors=True)

	log("Autoremoving unused packages...")
	run_cmd(["apt", "autoremove", "-y"], ignore_error=True)

	log("Cleaning apt cache...")
	run_cmd(["apt", "clean"], ignore_error=True)




def install_pigpiod(mode: str):
	run_cmd("apt install -y pigpio python3-pigpio", shell=True, ignore_error=True)

	log("Checking for pigpiod...")
	pigpiod_bin = shutil.which("pigpiod") or ("/usr/local/bin/pigpiod" if Path("/usr/local/bin/pigpiod").exists() else None)

	if not pigpiod_bin:
		log("Building pigpiod from source...")
		tmp_dir = Path("/tmp/pigpio")
		if tmp_dir.exists():
			shutil.rmtree(tmp_dir)
		try:
			run_cmd("git clone https://github.com/joan2937/pigpio.git /tmp/pigpio", shell=True)
			run_cmd("sed -i '/setup.py/d' Makefile", shell=True, cwd=str(tmp_dir))
			run_cmd("make", shell=True, cwd=str(tmp_dir))
			run_cmd("make install", shell=True, cwd=str(tmp_dir))
			run_cmd("ldconfig", shell=True)
			pigpiod_bin = "/usr/local/bin/pigpiod"
		except Exception as e:
			log(f"Build failed: {e}")
		finally:
			shutil.rmtree(tmp_dir, ignore_errors=True)

	pigpiod_bin = shutil.which("pigpiod") or pigpiod_bin
	if not pigpiod_bin:
		log("CRITICAL: pigpiod installation failed.")
		return

	service_content = f"""[Unit]
Description=Pigpio daemon
After=network.target

[Service]
ExecStart={pigpiod_bin} -l
Type=forking

[Install]
WantedBy=multi-user.target
"""
	write_file(SYSTEMD_ETC / "pigpiod.service", service_content)
	enable_unit_fs("pigpiod.service")

	if systemd_online(mode):
		run_cmd("systemctl daemon-reload", shell=True, ignore_error=True)
		run_cmd("killall pigpiod", shell=True, ignore_error=True)
		run_cmd("systemctl enable pigpiod", shell=True, ignore_error=True)
		run_cmd("systemctl restart pigpiod", shell=True, ignore_error=True)

	append_if_missing("/etc/environment", "PIGPIO_ADDR=soft")
	append_if_missing("/etc/environment", "PIGPIO_PORT=8888")


def configure_hardware(mode: str):
	log("Configuring hardware...")
	zram_conf = Path("/etc/default/zramswap")
	if zram_conf.exists():
		content = zram_conf.read_text()
		content = re.sub(r"^PERCENT=.*", "#PERCENT=50", content, flags=re.MULTILINE)
		if "SIZE=" in content:
			content = re.sub(r"^#*SIZE=.*", "SIZE=64", content, flags=re.MULTILINE)
		else:
			content += "\nSIZE=64\n"
		content = re.sub(r"^#*ALGO=.*", "ALGO=lz4", content, flags=re.MULTILINE)
		zram_conf.write_text(content)
		if systemd_online(mode):
			run_cmd("systemctl restart zramswap.service > /dev/null 2>&1", shell=True, ignore_error=True)

	config_txt = Path("/boot/firmware/config.txt") if Path("/boot/firmware/config.txt").exists() else Path("/boot/config.txt")
	append_if_missing(config_txt, "dtoverlay=disable-bt")

	cmdline = Path("/boot/firmware/cmdline.txt") if Path("/boot/firmware/cmdline.txt").exists() else Path("/boot/cmdline.txt")
	if cmdline.exists():
		if "ipv6.disable=1" not in cmdline.read_text(errors="ignore"):
			cmdline.write_text(cmdline.read_text(errors="ignore").strip() + " ipv6.disable=1")
	append_if_missing("/etc/sysctl.conf", "net.ipv6.conf.all.disable_ipv6=1")

	if not is_chroot_mode(mode):
		w1_devices = Path("/sys/bus/w1/devices/")
		has_sensor = any("28" in x.name for x in w1_devices.iterdir()) if w1_devices.exists() else False
		run_cmd(f"raspi-config nonint do_onewire {0 if has_sensor else 1}", shell=True, ignore_error=True)

	append_if_missing(BASE_DIR / ".bashrc", "\nif [ -x /usr/bin/raspi-config ]; then sudo raspi-config nonint do_expand_rootfs >/dev/null 2>&1 || true; fi\n")



def configure_sudoers(app_user):
	sudoers_content = ["www-data ALL=(ALL) NOPASSWD: ALL"]
	if app_user and app_user != "www-data":
		sudoers_content.append(f"{app_user} ALL=(ALL) NOPASSWD: ALL")
	write_file("/etc/sudoers.d/010_bcmeter", "\n".join(sudoers_content) + "\n")
	run_cmd("chmod 0440 /etc/sudoers.d/010_bcmeter", shell=True)


def setup_python_env():
	log("Setting up Python environment...")
	venv_dir = BASE_DIR / "venv"
	if not venv_dir.exists():
		run_cmd([sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)])
	pip_bin = venv_dir / "bin" / "pip"
	run_cmd([str(pip_bin), "install", "--no-cache-dir"] + VENV_ONLY_PACKAGES)
	run_cmd([str(pip_bin), "install", "--no-cache-dir", "pigpio"], ignore_error=True)
	return venv_dir


def configure_services(mode: str, venv_dir: Path):
	log("Configuring services...")
	php_ver = subprocess.getoutput("php -r 'echo PHP_MAJOR_VERSION.\".\".PHP_MINOR_VERSION;'").strip()
	if not php_ver:
		php_ver = "8.2"

	nginx_conf = f"""server {{
	listen 80 default_server;
	server_name $host;
	root {BASE_DIR};
	expires -1;
	proxy_no_cache 1;
	proxy_cache_bypass 1;
	index index.html index.htm index.php;
	location = / {{ rewrite ^/$ /interface/index.php redirect; }}
	location / {{ try_files $uri $uri/ =404; }}
	location ~ \\.php$ {{
		include snippets/fastcgi-php.conf;
		fastcgi_pass unix:/run/php/php{php_ver}-fpm.sock;
	}}
	location ~ /\\. {{ deny all; }}
	location /logs/ {{ autoindex on; add_header Access-Control-Allow-Origin \"*\"; }}
}}"""
	write_file("/etc/nginx/sites-available/default", nginx_conf)

	py_bin = venv_dir / "bin" / "python"
	common_env = f'Environment="PATH={venv_dir}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"\n'
	common_unit = "After=multi-user.target NetworkManager.service\nWants=NetworkManager.service\n"

	ap_loop_unit = f"""[Unit]
Description=bcMeter_ap_control_loop
{common_unit}
[Service]
Type=idle
ExecStart={py_bin} {BASE_DIR}/bcMeter_ap_control_loop.py
ExecStartPre=/bin/sleep 5
KillSignal=SIGINT
SyslogIdentifier=bcMeter_ap_control_loop
Restart=always
RestartSec=3
OOMScoreAdjust=-500
User=root
{common_env}
[Install]
WantedBy=multi-user.target
"""

	flask_unit = f"""[Unit]
Description=bcMeter_flask
{common_unit}
[Service]
Type=idle
ExecStart={py_bin} {BASE_DIR}/app.py
ExecStartPre=/bin/sleep 5
KillSignal=SIGINT
SyslogIdentifier=bcMeter_flask
Restart=always
RestartSec=3
OOMScoreAdjust=-500
User=root
{common_env}
[Install]
WantedBy=multi-user.target
"""

	bcmeter_unit = f"""[Unit]
Description=bcMeter
{common_unit}
[Service]
Type=idle
ExecStart={py_bin} {BASE_DIR}/bcMeter.py
ExecStartPre=/bin/sleep 5
KillSignal=SIGINT
SyslogIdentifier=bcMeter
Restart=no
RestartSec=3
OOMScoreAdjust=-500
User=root
{common_env}
"""

	write_file(SYSTEMD_ETC / "bcMeter_ap_control_loop.service", ap_loop_unit)
	write_file(SYSTEMD_ETC / "bcMeter_flask.service", flask_unit)
	write_file(SYSTEMD_ETC / "bcMeter.service", bcmeter_unit)

	disable_unit_fs("bcMeter.service")
	enable_unit_fs("bcMeter_ap_control_loop.service")
	enable_unit_fs("bcMeter_flask.service")

	if systemd_online(mode):
		run_cmd("systemctl daemon-reload", shell=True, ignore_error=True)
		run_cmd("systemctl stop bcMeter", shell=True, ignore_error=True)
		run_cmd("systemctl disable bcMeter", shell=True, ignore_error=True)
		run_cmd("systemctl reset-failed bcMeter", shell=True, ignore_error=True)
		run_cmd("systemctl enable bcMeter_ap_control_loop", shell=True, ignore_error=True)
		run_cmd("systemctl enable bcMeter_flask", shell=True, ignore_error=True)
		run_cmd("systemctl restart nginx", shell=True, ignore_error=True)

	if not is_chroot_mode(mode):
		for cmd in ["do_boot_behaviour B2", "do_i2c 0", "do_spi 0", "do_serial_hw 0", "do_serial_cons 1", "do_net_names 0", "do_expand_rootfs"]:
			run_cmd(f"raspi-config nonint {cmd}", shell=True, ignore_error=True)

	app_user = BASE_DIR.name
	run_cmd(f"chown -R {app_user}:{app_user} {BASE_DIR}", shell=True, ignore_error=True)


	bashrc = BASE_DIR / ".bashrc"
	service_check = "\nif ! systemctl is-active --quiet bcMeter_ap_control_loop; then\n    sudo systemctl enable bcMeter_ap_control_loop\n    sudo systemctl start bcMeter_ap_control_loop\nfi\n"
	append_if_missing(bashrc, service_check)

	bashrc_content = bashrc.read_text(errors="ignore") if bashrc.exists() else ""
	bashrc_content = re.sub(r"^alias bcd=.*$", "", bashrc_content, flags=re.MULTILINE)
	bashrc_content = re.sub(r"^alias bcc=.*$", "", bashrc_content, flags=re.MULTILINE)
	bashrc_content = bashrc_content.strip() + "\n"
	bashrc_content += f"alias bcd='sudo {py_bin} {BASE_DIR}/bcMeter.py debug'\n"
	bashrc_content += f"alias bcc='sudo {py_bin} {BASE_DIR}/bcMeter.py cal'\n"
	bashrc.write_text(bashrc_content)


def configure_network_manager(mode: str):
	log("Configuring NetworkManager...")

	nm_conf = "[main]\nplugins=keyfile\n\n[device]\nwifi.scan-rand-mac-address=no\n\n[connection]\nwifi.cloned-mac-address=preserve\n"
	write_file("/etc/NetworkManager/conf.d/10-bcmeter.conf", nm_conf)

	for f in ["/etc/NetworkManager/conf.d/10-globally-managed-devices.conf", "/usr/lib/NetworkManager/conf.d/10-globally-managed-devices.conf"]:
		Path(f).unlink(missing_ok=True)

	for f in ["/etc/network/interfaces.d/wlan0_wifi", "/etc/wpa_supplicant/wpa_supplicant.conf"]:
		Path(f).unlink(missing_ok=True)

	ifaces = Path("/etc/network/interfaces")
	if ifaces.exists():
		content = ifaces.read_text(errors="ignore")
		ifaces.write_text("\n".join(l for l in content.splitlines() if "wlan0" not in l) + "\n")

	run_cmd("apt purge -y dhcpcd5 hostapd ifupdown", shell=True, ignore_error=True)

	for unit in ["systemd-networkd.service", "dhcpcd.service", "hostapd.service", "dnsmasq.service"]:
		disable_unit_fs(unit)
		mask_unit_fs(unit)

	unmask_unit_fs("NetworkManager.service")
	enable_unit_fs("NetworkManager.service")

	if systemd_online(mode):
		for s in ["systemd-networkd", "dhcpcd", "hostapd", "dnsmasq"]:
			run_cmd(f"systemctl stop {s}", shell=True, ignore_error=True)
			run_cmd(f"systemctl disable {s}", shell=True, ignore_error=True)
			run_cmd(f"systemctl mask {s}", shell=True, ignore_error=True)
		run_cmd("systemctl unmask NetworkManager && systemctl enable NetworkManager && systemctl restart NetworkManager", shell=True, ignore_error=True)
		time.sleep(3)
		run_cmd("nmcli dev set wlan0 managed yes", shell=True, ignore_error=True)
		run_cmd("nmcli radio wifi on", shell=True, ignore_error=True)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("mode", nargs="?", default="install")
	parser.add_argument("--clone", action="store_true")
	args = parser.parse_args()

	mode = args.mode

	setup_logging()
	if os.geteuid() != 0:
		sys.exit("Run with sudo")

	app_user = BASE_DIR.name
	force_update = (mode == "force")

	cleanup_legacy_install()
	system_setup(mode, noupgrade=(mode == "noupgrade"))
	install_pigpiod(mode)

	ensure_codebase_state(force=force_update or args.clone)
	if mode == "update":
		mark_legacy_notice_pending()

	venv_dir = setup_python_env()
	configure_hardware(mode)
	configure_services(mode, venv_dir)
	configure_sudoers(app_user)

	LOG_DIR.mkdir(parents=True, exist_ok=True)
	(LOG_DIR / "log_current.csv").touch(exist_ok=True)

	log("=" * 50)
	log("FINAL STEP: Network reconfiguration")
	log("SSH connection will drop. Device will reboot.")
	log("=" * 50)
	configure_network_manager(mode)
	run_cmd(f"chmod -R 777 {BASE_DIR}", shell=True, ignore_error=True)
	if is_chroot_mode(mode):
		return


	time.sleep(3)

	run_cmd("reboot now", shell=True)


if __name__ == "__main__":
	main()
