
<?php
if (isset($_POST['datetime'])) {
    $datetime = $_POST['datetime'];
    if ($datetime =='now'){
          $exec_code = shell_exec('date');
          echo ($exec_code);
       }
 }
?>