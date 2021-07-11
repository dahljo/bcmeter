## Thank you for your interest! In this git you find everything you need to build your own bcMeter:

### Gerber for PCB Manufactoring

in /gerbers there are two versions of the pcb available. there is a general purpose pcb for use with 12v and one smaller which is powered by the raspberry pi directly.

### STL files for 3D Printing

in /stl you find the files for 3d printing. as of july 2021 there is one case for the general purpose circuit board (PCB) but the smaller PCB fits as well. We will create a smaller case as well to reduce the costs to print, if the big case is not necessary. 

### Script / Interface

install.sh is a just a batch to configure the raspberry for the use as bcMeter
bcMeter.py is the python script which saves the data as csv
/interface contains a simple d3.js interface for reading out the csv file

**recommended:** 
download bcMeter.img from bcmeter.org and clone that to a microSD card - change WiFi credentials and you're ready

**manual installation:**

see https://bcmeter.org/wiki/index.php?title=Software for instructions, the basic procedure is:

1. write raspberry lite image to micro sd card (do not use the raspberry os desktop imagefile!). 
2. create empty ssh file on /boot to be able to log in via ssh later
3. create wpa_supplicant.conf with your WiFi credentials on /boot (see bcmeter.org/wiki if you dont know what this means)
4. download and run install.sh script
5. run bcMeter script


renderings of the pcb and case

![bcmeter-tht](https://user-images.githubusercontent.com/87074315/124761537-337b2780-df32-11eb-83bd-753e4972f371.jpg)
![bcmeter-smd](https://user-images.githubusercontent.com/87074315/124761541-3413be00-df32-11eb-88a7-5631a5a1f0b4.jpg)
![bcmeter-general-purpose-case](https://user-images.githubusercontent.com/87074315/124761546-3413be00-df32-11eb-8138-fc08c174cbb7.jpg)
