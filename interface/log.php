<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bcMeter system log</title>
    <link rel="stylesheet" href="css/bootstrap.min.css">
    <style>
        #logContent {
            background-color: #333;
            color: white;
            font-family: monospace;
            padding: 10px;
            overflow: auto;
            height: 40em; /* Adjust the height as needed */
            width: 80%; /* Adjust the width as needed */
            font-size: 10px;
            white-space: pre-wrap;
        }
    </style>
</head>
<body>

<div class="container mt-5">
    <h2>System Log Viewer</h2>

    <?php
    if ($_SERVER["REQUEST_METHOD"] == "POST") {
        if (isset($_POST["viewLog"])) {
            $output = shell_exec("sudo cat /var/log/syslog | grep python3 2>&1");

            if ($output === null) {
                echo "Error executing the command.";
            } else {
                echo '<div id="logContent">' . htmlspecialchars($output) . '</div>';
                
                // Save the content to a file
                $filename = 'output.log';
                file_put_contents($filename, $output);
                
                // Display a download link for the file
                echo '<a href="' . $filename . '" class="btn btn-success" download>Download Log</a>';
            }
        }
    }
    ?>

    <form method="post" action="<?php echo htmlspecialchars($_SERVER["PHP_SELF"]); ?>">
        <button type="submit" class="btn btn-primary" name="viewLog">View Log</button>
    </form>
</div>

</body>
</html>
