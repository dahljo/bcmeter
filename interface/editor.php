<?php
$fn = "/home/pi/bcMeter.py";
$content = $_POST['content'];
$fp = fopen($fn,"w") or die ("Error opening file in write mode!");
fputs($fp,$content);
fclose($fp) or die ("Error closing file!");
?>
<br>

<h3>File saved</h3>

Go back to <a href="/interface">interface</a> or <a href="editor-form.php">script editor</a>.
<br /><br />
<textarea rows="50" cols="80" name="content" style="font-family: monospace;background: #000; color: #ccc">
<?php
$fn = "/home/pi/bcMeter.py";
print implode("",file($fn));
?> 
</textarea><br>

