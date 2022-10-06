

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
  <a href="" id="download" style="display: none;"></a>





<a hreg="../"><img src="bcMeter-logo.png" style="width: 300px; display:block; margin: 0 auto;"/></a>
  <script src="js/d3.min.js"></script>
  <script src="js/jquery-3.6.0.min.js"></script>
  <script src="js/bootstrap.min.js"></script>
  <script src="js/bootbox.min.js"></script>



<h3 style="text-align: center">

<?php

$PID = getPID(); 

function getPID()
{

    $grep = shell_exec('ps -eo pid,lstart,cmd | grep bcMeter.py | grep -Fv grep | grep -Fv www-data | grep -Fv sudo | grep -Fiv screen | grep python3');
    $numbers = preg_replace('/^\s+| python3 \/home\/pi\/bcMeter.py/', "", $grep);
    $numbers = explode(" ", $numbers);
    $PID = $numbers[0];
      $VERSION =  "0.9.8 2022-10-04";
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
	 case 'reboot':
      echo "bcMeter will now reboot and is back online in a minute. <br />You may keep this page open for automatic reload.<br /><br /><pre>";
      echo "</pre><script>setTimeout(function(){window.location.replace('index.php');}, 60000);</script>";
      $cmd = 'sudo reboot now';
        while (@ ob_end_flush()); // end all output buffers if any
        $proc = popen($cmd, 'r');
        echo '<pre>';
        while (!feof($proc))
        {
            echo fread($proc, 4096);
            @ flush();
        }
        echo '</pre>';
      break;
    case 'shutdown':
      echo "bcMeter will now shutdown<br />You may disconnect the power source in 20 seconds.<br /><br /><pre>";
      $cmd = 'sudo shutdown now';
        while (@ ob_end_flush()); // end all output buffers if any
        $proc = popen($cmd, 'r');
        echo '<pre>';
        while (!feof($proc))
        {
            echo fread($proc, 4096);
            @ flush();
        }
        echo '</pre>';
      break;
    case 'debug':
      echo "debug log<br /><br /><pre>";
      $cmd = 'sudo python3 /home/pi/bcMeter.py debug';
        while (@ ob_end_flush()); // end all output buffers if any
        $proc = popen($cmd, 'r');
        echo '<pre>';
        while (!feof($proc))
        {
            echo fread($proc, 4096);
            @ flush();
        }
        echo '</pre><br /> <h3>copy and paste this to <a href="mailto:jd@bcmeter.org">jd@bcmeter.org</a><br /> <br /><a href="index.php">Go back to interface</a>';
      break;

 case 'update':
      echo "bcMeter will now update<br /><br /><pre>";

       shell_exec("sudo kill -9 $PID");

        while (@ ob_end_flush()); // end all output buffers if any
      $cmd = 'cd /home/pi && sudo wget -N https://raw.githubusercontent.com/bcmeter/bcmeter/main/install.sh -P /home/pi/ && sudo bash /home/pi/install.sh update' ;
      $proc = popen($cmd, 'r');
      echo '<pre>';
      while (!feof($proc))
      {
          echo fread($proc, 4096);
          @ flush();
      }

      echo '</pre>';


  	
    	default:
	   		echo "no valid status submitted";
		

	}
?>
	
	</h3>
<script>
</script>
</body>
</html>

