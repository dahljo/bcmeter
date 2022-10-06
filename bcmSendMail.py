import smtplib, ssl
from email.mime.multipart import MIMEMultipart 
from email.mime.text import MIMEText 
from email.mime.application import MIMEApplication
import os
from time import sleep

smtp_server = 'smtp.gmail.com'
smtp_port = 587
#Replace with your own gmail account
gmail = 'bcmeter.dev@gmail.com'
password = 'kgf125P*"bcm'

while True:

	message = MIMEMultipart('mixed')
	message['From'] = os.uname()[1] + ' <{sender}>'.format(sender = gmail)
	message['To'] = 'jonasdahl@gmx.de'
	#message['CC'] = 'axel.friedrich.berlin@gmail.com'
	message['Subject'] = os.uname()[1] + " log"

	to= message['To']
	cc= message['CC']

	msg_content = 'Find current log attached'
	body = MIMEText(msg_content, 'html')
	message.attach(body)


	attachmentPath = "/home/pi/logs/log_current.csv"
	try:
		with open(attachmentPath, "rb") as attachment:
			p = MIMEApplication(attachment.read(),_subtype="csv")	
			p.add_header('Content-Disposition', "attachment; filename= %s" % attachmentPath.split("/")[-1]) 
			message.attach(p)
	except Exception as e:
		print(str(e))

	msg_full = message.as_string()

	context = ssl.create_default_context()

	with smtplib.SMTP(smtp_server, smtp_port) as server:
		server.ehlo()  
		server.starttls(context=context)
		server.ehlo()
		server.login(gmail, password)
		server.sendmail(gmail, to.split(";") + (cc.split(";") if cc else []), msg_full)
		server.quit()

	print("email sent out successfully")
	sleep(1800)


