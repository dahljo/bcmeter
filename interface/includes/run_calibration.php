<?php
$baseDir = file_exists('/home/bcmeter') ? '/home/bcmeter' : (file_exists('/home/bcMeter') ? '/home/bcMeter' : '/home/pi');
$bcmeter_path = $baseDir . '/bcMeter.py';
$venv_python = $baseDir . '/venv/bin/python3';

exec('sudo systemctl stop bcMeter', $output1, $return_var1);

if ($return_var1 === 0 || $return_var1 === 3) {
    $cmd = "sudo $venv_python -u $bcmeter_path cal";
    exec($cmd);
}
?>