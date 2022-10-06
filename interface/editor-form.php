<h1>Content of /home/pi/bcMeterConf.py</h1><br>
<form action="editor.php" method="post">
<textarea rows="50" cols="100" name="content" style="font-family: monospace;background: #000; color: #ccc; font-size:14px">
<?php
$fn = "/home/pi/bcMeterConf.py";
print implode("",file($fn));
?> 
</textarea><br>
<input type="submit" value="Save"> 
<a href="/interface">Back to Interface</a>
</form>