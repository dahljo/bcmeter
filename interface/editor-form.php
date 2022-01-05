
<h1>Content of /home/pi/bcMeter.py</h1><br>
<form action="editor.php" method="post">
<textarea rows="50" cols="80" name="content" style="font-family: monospace;background: #000; color: #ccc">
<?php
$fn = "/home/pi/bcMeter.py";
print implode("",file($fn));
?> 
</textarea><br>
<input type="submit" value="Save"> 
<a href="/interface">Back to Interface</a>
</form>