## Thank you for your interest! In this git you find everything you need to build your own bcMeter:


## Recommended setup:
download bcMeter.img from https://bcmeter.org and clone that to a microSD card - change WiFi credentials and you're ready

## manual installation:

see https://bcmeter.org/wiki/index.php?title=Installation#Alternative:_Manual_Set_Up_the_microSD_Card for instructions, the basic procedure is:

1. write raspberry LITE(!) image to micro sd card  
2. create empty ssh file on /boot to be able to log in via ssh later
3. create wpa_supplicant.conf with your WiFi credentials on /boot (see https://bcmeter.org/wiki/index.php?title=Installation#Enable_WiFi_access if you dont know what this means)
4. bootup raspberry pi and log into it via ssh, download and run install.sh script (wget -N https://raw.githubusercontent.com/bcmeter/bcmeter/main/install.sh && sudo bash install.sh)
5. run bcMeter script 


### Script / Interface

install.sh is a just a batch to configure the raspberry for the use as bcMeter
bcMeter.py is the python script which saves the data as csv
/interface contains a simple d3.js interface for reading out the csv file



### Gerber for PCB Manufactoring

in /gerbers there are two versions of the pcb available. there is a general purpose pcb for use with 12v and one smaller which is powered by the raspberry pi directly.

### STL files for 3D Printing

in /stl you find the files for 3d printing. as of july 2021 there is one case for the general purpose circuit board (PCB) but the smaller PCB fits as well. We will create a smaller case as well to reduce the costs to print, if the big case is not necessary. 


5V option

![bcMeter-smallCase](https://user-images.githubusercontent.com/87074315/152612250-c9c2e578-1b18-46d1-ad44-5a189bbf04da.png)
![bcMeter-5V](https://user-images.githubusercontent.com/87074315/152612590-75ef60a8-828f-4d69-82bb-b6b03c55a555.png)

12V option
![bcmeter-tht](https://user-images.githubusercontent.com/87074315/124761537-337b2780-df32-11eb-83bd-753e4972f371.jpg)
![bcmeter-general-purpose-case](https://user-images.githubusercontent.com/87074315/124761546-3413be00-df32-11eb-8138-fc08c174cbb7.jpg)
