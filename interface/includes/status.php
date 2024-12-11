
<?php
// Start the PHP session
//$version = "24-10-16"
session_start();
header('X-Accel-Buffering: no');
$baseDir = file_exists('/home/bcMeter') ? '/home/bcMeter' : '/home/pi';

function checkUndervoltage() {
		$styles = [
				'red' => "<span class='text-danger font-weight-bold'>",
				'black' => "<span class='text-dark'>",
				'reset' => "</span>"
		];
		$today = date('M d');
		
		// Get the syslog entries after the newest "Linux version" occurrence
		$output = shell_exec("sudo tac /var/log/syslog | awk '/Linux version/ {exit} {print}' | grep -a 'Undervoltage'");
		$lines = array_filter(explode("\n", trim($output)));
		
		if (empty($lines)) return "";

		$response = "
				<div class='text-center'>
						{$styles['red']}<strong>WARNING</strong>: Undervoltage detected - you might ignore it when it does not happen very often. <br>if it repeats a lot, use a 5.25V, 3A power supply and a short cable.{$styles['reset']}<br><br>
		";
		
		foreach (array_slice($lines, -4) as $line) {
				$style = (strpos($line, $today) !== false) ? 'red' : 'black';
				$response .= "{$styles[$style]}{$line}{$styles['reset']}<br>";
		}

		// Add Bootstrap-styled button centered
		$response .= "<br /><button class='btn btn-danger mt-3' onclick='ignoreWarning()'>Ignore undervoltage warning</button></div><br />";

		return $response;
}



// Check if the request is a POST request
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['status']) && $_POST['status'] === 'undervolt') {
		// Return only the undervoltage status if this is an AJAX request
		echo checkUndervoltage();
		exit();
}


?>
<!DOCTYPE html>
<meta charset="utf-8">
<head>    <link rel="stylesheet" type="text/css" href="css/bootstrap.min.css">
</head>
<style>
	html, body{
		font-family: sans-serif;
		margin: 0px;
		padding: 0px
	}
</style>

<body>
<a href="../index.php"><img src="../bcMeter-logo.png" style="width: 300px; display:block; margin: 0 auto;"/><br/><div style="text-align:center">Back to interface</div></a>
	<script src="../../js/jquery-3.6.0.min.js"></script>
	<script src="../../js/bootstrap.min.js"></script>
	<script src="../../js/bootbox.min.js"></script>
<h3 style="text-align: center">
<?php


if (!isset($_SESSION['valid_session']) ) {
	echo "<script>setTimeout(function(){window.location.replace('/interface/index.php');}, 4000);</script>";
	exit();
}

session_destroy();

shell_exec('sudo systemctl daemon-reload');

$connected = FALSE;

if(!$sock = @fsockopen('www.google.com', 80))
{
		$connected = FALSE;
}
else
{   
		$connected = TRUE;
}

function getPID()
{
    global $baseDir;
		$version = '';
		$localfile = $baseDir . '/bcMeter.py';
		for($i = 1; $i <= 50; $i++) {
			$line = trim(exec("head -$i $localfile| tail -1"));
			if (strpos($line, 'bcMeter_version') === 0) {
				$version = explode('"', $line)[1];
				break;
			}
		}

		echo "The version is $version";

		$version_parts = explode('.', $version);


		$VERSION = $version_parts[0] . "." . $version_parts[1]  . "." .  $version_parts[2];


		$grep = shell_exec('ps -eo pid,lstart,cmd | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3');
		$numbers = preg_replace('/^\s+| python3 \/home\/pi\/bcMeter.py/', "", $grep);
		$numbers = explode(" ", $numbers);
		$PID = $numbers[0];
		 

			$STARTED = implode(" ", array_slice($numbers,1));

			if (!isset($grep))
			{
					echo "<pre style='text-align:center;'>bcMeter stopped.<br/></pre>";
			}
			else {
					 echo "<pre style='text-align:center;'>Running with PID $PID since $STARTED <br /> v$VERSION </pre>";
			}
		return $PID;
}





	if (isset($_GET['status'])) {
		$status = $_GET['status'];

	}
	switch($status) {




	case 'change_hostname':
		if (isset($_GET['new_hostname'])) {
			$new_hostname = $_GET['new_hostname'];
			$setHostname = 'sudo raspi-config nonint do_hostname '. $new_hostname;
			$hostname = shell_exec($setHostname);
			echo "changing hostname to $new_hostname on next reboot.";


		}
	echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 10000);</script>";
	break;



		case 'debug':
		echo "$session_id";

		break;

		case 'timestamp':

		$timestamp = $_GET['timestamp'];

		$DEVICETIME = shell_exec('date');
		echo "<pre style='text-align:center;'>Old time set on device: $DEVICETIME </pre>";
		echo "sudo date -s @'" . $timestamp . "'";
	 shell_exec("sudo date -s @'" . $timestamp . "'");

		$DEVICETIME = shell_exec('date');
		echo "<pre style='text-align:center;'>New time set on device: $DEVICETIME </pre>";
		echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 4000);</script>";

		break;

case 'deleteOld':

		$files = glob('../../logs/*.csv'); 
		// Sort files by date, newest first
		array_multisort(
				array_map('filemtime', $files),
				SORT_NUMERIC,
				SORT_DESC,
				$files
		);

		$files = array_slice($files, 0, 2);

		// Delete all other files
		foreach (array_diff(glob('../../logs/*.csv'), $files) as $file) {
				unlink($file);
		}

		// New log deletion in '../maintenance_logs/' folder
		$maint_files = glob('../../maintenance_logs/*.csv'); 

		// Sort files by date, newest first
		array_multisort(
				array_map('filemtime', $maint_files),
				SORT_NUMERIC,
				SORT_DESC,
				$maint_files
		);

		// Keep the three most recent files
		$recent_maint_files = array_slice($maint_files, 0, 3);

		// Find any file containing "install" in the filename
		$install_files = array_filter($maint_files, function($file) {
				return strpos($file, 'install') !== false;
		});

		// Merge recent files and install files, ensuring uniqueness
		$files_to_keep = array_unique(array_merge($recent_maint_files, $install_files));

		// Delete all other files
		foreach (array_diff($maint_files, $files_to_keep) as $file) {
				unlink($file);
		}

		echo "<pre style='text-align:center'><h2>Successfully deleted old logs</h2>Returning to Interface in a few seconds or click <a href='/interface/index.php'>here</a></pre>";
		echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 4000);</script>";
		break;


	 case 'reboot':
			$wifiFile=$baseDir . '/bcMeter_wifi.json';
			$data=json_decode(file_get_contents($wifiFile),TRUE);                     //no pwd given, resubmit of old wifi network
			$wifi_pwd = $data["wifi_pwd"];
			$wifi_ssid = $data["wifi_ssid"];
		 $bcMeter_hotspot_address = "http://192.168.18.8";
			$bcMeter_hostname = gethostname();
			$bcMeter_wifi_address ="http://$bcMeter_hostname.local";

			if(empty($wifi_pwd)){   
				exec("sudo bash -c \"echo 'ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n' > /etc/wpa_supplicant/wpa_supplicant.conf\"");
				
				echo "<pre style='text-align:center'><h2>Rebooting to hotspot mode</h2>";
				echo "Connect to WiFi called bcMeter when it shows up in a minute before you connect to <a href='$bcMeter_hotspot_address'>$bcMeter_hotspot_address</a>.";  

			}
			else {
				echo "<pre style='text-align:center'><h2>Rebooting and logging into WiFi $wifi_ssid</h2>";  
				echo "You can access your bcMeter then at <br /> <a href='$bcMeter_wifi_address'>$bcMeter_wifi_address</a> <br /> I will try to automatically redirect in about in about a minute.";  
				 
				echo "</pre><script>setTimeout(function(){window.location.replace('$bcMeter_wifi_address');}, 70000);</script>";
			}
			exec('sudo reboot now');

				


			break;
		case 'shutdown':
			echo "bcMeter will now shutdown<br />You may disconnect the power source in 20 seconds or when you hear the pump is stopped.<br /><br /><pre>";
			$cmd = 'sudo shutdown now';
					echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 10000);</script>";

				exec($cmd);
			 

			break;
		case 'debug':
			echo "debug log<br /><br /><pre>";
			$cmd = 'sudo python3 ' . $baseDir . '/bcMeter.py debug';
				while (@ ob_end_flush()); // end all output buffers if any
				$proc = popen($cmd, 'r');
				echo '<pre>';

				echo '</pre><br /> <h3>copy and paste this to <a href="mailto:jd@bcmeter.org">jd@bcmeter.org</a><br /> <br /><a href="index.php">Go back to interface</a>';
			break;

 case 'update':
// Function to flush and send output to the browser
function sendOutput($output) {
		echo $output;
		ob_flush();
		flush();
}


if (!isset($_SESSION['update_in_progress'])) {
		$_SESSION['update_in_progress'] = true;

		if ($connected == TRUE) {
				echo "bcMeter will now update, this may take a few minutes. <br /><br /><pre>";
				$cmd = "screen -dmS bcMeterUpdate bash -c 'cd $baseDir && sudo wget -N https://raw.githubusercontent.com/bcmeter/bcmeter/main/install.sh -P $baseDir && sudo bash $baseDir/install.sh update'";
				$proc = popen($cmd, 'r');
				sendOutput('<pre>');

				while (!feof($proc)) {
						$output = fread($proc, 4096);
						sendOutput($output);
				}

				pclose($proc);

				// Display the content of the log file
				$logContent = file_get_contents($baseDir . '/maintenance_logs/bcMeter_install.log');
				sendOutput($logContent);

				echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 30000);</script>";
		} else {
				echo "<pre style='text-align:center'>bcMeter seems not to be online! Change WiFi and try again</pre>";
		}

		echo "Wait for automatic redirect... <script>setTimeout(function(){window.location.replace('/interface/index.php');}, 10000);</script>";

		// Mark the update as complete
		unset($_SESSION['update_in_progress']);
}
break;
		
case 'syslog':

$timestamp = date('Ymd_His');
$hostname = gethostname();
$zipFilePath = '/tmp/syslog_and_maintenance_logs_' . $hostname . '_' . $timestamp . '.zip';
$additionalSyslog = '';
if (file_exists('/var/log/syslog.1')) {
		$additionalSyslog = '/var/log/syslog.1';
}
$zipCommand = "sudo zip -j $zipFilePath /var/log/syslog $baseDir/maintenance_logs/* $additionalSyslog";

// Execute the command
shell_exec($zipCommand);

// Check if ZIP file was created successfully
if (file_exists($zipFilePath)) {
		// Set appropriate headers for downloading the ZIP file
		header('Content-Description: File Transfer');
		header('Content-Type: application/zip');
		header('Content-Disposition: attachment; filename=' . basename($zipFilePath));
		header('Content-Transfer-Encoding: binary');
		header('Expires: 0');
		header('Cache-Control: must-revalidate');
		header('Pragma: public');
		header('Content-Length: ' . filesize($zipFilePath));

		// Clean any previously output data
		ob_clean();
		flush();

		// Read the ZIP file and output its contents
		readfile($zipFilePath);

		// Delete the ZIP file after download
		unlink($zipFilePath);
} else {
		echo 'Failed to create ZIP file.';
}
break;



 case 'calibration':
		session_write_close(); // Important to not block the session
echo 'Starting calibration... Takes a minute';
		function executeCommand($cmd) {
				while (@ob_end_flush()); // End all output buffers if any
				$proc = popen($cmd, 'r');
				echo '<pre>';
				while (!feof($proc)) {
						echo fread($proc, 4096);
						@flush();
				}
				echo '</pre>';

		}

		$cmd1 = 'sudo systemctl stop bcMeter';
		executeCommand($cmd1);
				sleep(2); 
		$cmd2 = "sudo python3 $baseDir/bcMeter.py cal";
		executeCommand($cmd2);
		echo "Wait for automatic redirect... <script>setTimeout(function(){window.location.replace('/interface/index.php');}, 10000);</script>";

		break;




			default:

				getPID();
		

	}

	
?>
	
	</h3>
<script>
</script>
</body>
</html>

