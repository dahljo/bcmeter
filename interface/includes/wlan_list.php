<?php
    $ssidArr = array();

    $cmd = 'nmcli -t -f SSID dev wifi list --rescan yes 2>/dev/null';
    exec($cmd, $output, $ret);

    if ($ret === 0) {
        foreach($output as $line){
            $ssid = trim($line);
            if (!empty($ssid)) {
                $ssidArr[$ssid] = true;
            }
        }
    } else {
        $cmd = 'sudo /usr/sbin/iwlist wlan0 scan 2>/dev/null';
        exec($cmd, $output2, $ret2);

        if ($ret2 !== 0) {
            $cmd = 'sudo /sbin/iwlist wlan0 scan 2>/dev/null';
            exec($cmd, $output2, $ret2);
        }

        foreach($output2 as $line){
            if (preg_match('/ESSID:"(.+)"/', $line, $matches)) {
                $ssidArr[$matches[1]] = true;
            }
        }
    }

    uksort($ssidArr, 'strcasecmp');

    $hosted = trim(shell_exec("grep '^ssid=' /etc/hostapd/hostapd.conf | cut -d= -f2"));
    if ($hosted) unset($ssidArr[$hosted]);

    echo json_encode(array_keys($ssidArr));
?>