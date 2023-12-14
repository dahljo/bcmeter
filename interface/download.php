<?php
header('Content-Type: application/octet-stream');
header('Content-Disposition: attachment; filename="syslog_python3_log.txt"');

readfile('/var/log/syslog');
?>
