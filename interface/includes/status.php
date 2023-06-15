
<?php
// Start the PHP session
session_start();
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

    $version = '';
    $localfile = '/home/pi/bcMeter.py';
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
    //sort files by date, newest first
    array_multisort(
        array_map( 'filemtime', $files ),
        SORT_NUMERIC,
        SORT_DESC,
        $files
    );

    $files = array_slice($files, 0, 2);

    //delete all other files
    foreach (array_diff(glob('../../logs/*.csv'), $files) as $file) {
        unlink($file);
    }

    echo "<pre style='text-align:center'><h2>Successfully deleted old logs</h2>Returning to Interface in a few seconds or click <a href='/interface/index.php'>here</a></pre>";
          echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 4000);</script>";
    break;

	 case 'reboot':
      $wifiFile='/home/pi/bcMeter_wifi.json';
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
      $cmd = 'sudo python3 /home/pi/bcMeter.py debug';
        while (@ ob_end_flush()); // end all output buffers if any
        $proc = popen($cmd, 'r');
        echo '<pre>';

        echo '</pre><br /> <h3>copy and paste this to <a href="mailto:jd@bcmeter.org">jd@bcmeter.org</a><br /> <br /><a href="index.php">Go back to interface</a>';
      break;

 case 'update':
 if ($connected == TRUE){
      echo "bcMeter will now update, this may take a few minutes. <br /><br /><pre>";
      while (@ ob_end_flush()); // end all output buffers if any
      $cmd = 'cd /home/pi && sudo wget -N https://raw.githubusercontent.com/bcmeter/bcmeter/main/install.sh -P /home/pi/ && sudo bash /home/pi/install.sh update' ;
      $proc = popen($cmd, 'r');
      echo '<pre>';
      echo "</pre><script>setTimeout(function(){window.location.replace('/interface/index.php');}, 10000);</script>";
    }
   else {
    echo "<pre style='text-align:center'>bcMeter seems not to be online! Change WiFi and try again</pre>";
   }
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

