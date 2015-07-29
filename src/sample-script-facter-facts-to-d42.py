# """
#NOTE:
#This script is obsolete.  
#Please use "nix_bsd_mac_inventory (https://github.com/device42/nix_bsd_mac_inventory)" script instead.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
#EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
#MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
#NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
#LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
#WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#"""

################################################################
# The script goes through the yaml fact files created by facter
# and populates device42 database with following info:
# device name, manufacturer, hardware model, serial #, os info, memory, cpucount and cpucores info
# IP address, interface name and mac address.
# Script tested with python 2.4
################################################################


import types
import os.path
import urllib
import urllib2
import traceback
import base64
import sys
import glob
import math

#Device42 URL and credentials

cred = open('/media/sf_dev/device42.credentials', 'r')

BASE_URL = cred.readline().split('\n')[0]  #Please make sure there is no / in the end
USER = cred.readline().split('\n')[0]
PASSWORD = cred.readline().split('\n')[0]
# puppet config dir
puppetdir = cred.readline().split('\n')[0]  #Change to reflect node directory with yaml fact files.

cred.close()

API_DEVICE_URL = BASE_URL + '/api/device/'
API_IP_URL = BASE_URL + '/api/ip/'

DRY_RUN = False  #if True no upload to device42

print
BASE_URL
print
USER
print
PASSWORD
print
puppetdir


def post(url, params):
    """http post with basic-auth params is dict like object"""
    try:
        data = urllib.urlencode(params)  # convert to ascii chars
        headers = {
            'Authorization': 'Basic ' + base64.b64encode(USER + ':' + PASSWORD),
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        if DRY_RUN:
            print
            url, headers, data
        else:
            req = urllib2.Request(url, data, headers)
            print
            '---REQUEST---', req.get_full_url()
            print
            req.headers
            print
            req.data

            response = urllib2.urlopen(req)
            print
            '---RESPONSE---'
            print
            response.read()

    except Exception, Err:
        print
        '-----EXCEPTION OCCURED-----'
        print
        str(Err)

def to_ascii(s):
    """remove non-ascii characters"""
    if type(s) == types.StringType:
        return s.encode('ascii', 'ignore')
    else:
        return str(s)


def closest_memory_assumption(v):
    if v < 512:
        v = 128 * math.ceil(v / 128.0)
    elif v < 1024:
        v = 256 * math.ceil(v / 256.0)
    elif v < 4096:
        v = 512 * math.ceil(v / 512.0)
    elif v < 8192:
        v = 1024 * math.ceil(v / 1024.0)
    else:
        v = 2048 * math.ceil(v / 2048.0)
    return int(v)


for infile in glob.glob(os.path.join(puppetdir, '*yaml')):
    d = {}

    f = open(infile)
    print
    "---Going through fact file: %s" % infile
    for line in f:
        if "--" not in line:

            line = line.strip().replace('"', '')
            try:
                key, val = line.split(':', 1)
                d[key] = val.strip()
            except:
                pass

    f.close()
    device_name = to_ascii(
        d.get('clientcert', None))  #using clientcert as the nodename here, you can change it to your liking.
    if device_name == 'None':
        device_name = to_ascii(d.get('name', None))
    if len(device_name) > 64:
        device_name = device_name[:64]
    os = to_ascii(d.get('operatingsystem', None))
    osver = to_ascii(d.get('operatingsystemrelease', None))
    device = {
        'name': device_name, }

    if os is not None: device.update({'os': os, })
    if osver is not None: device.update({'osverno': osver, })
    manufacturer = to_ascii(d.get('manufacturer', None)).strip()
    if manufacturer is not None:
        for mftr in ['VMware, Inc.', 'Bochs', 'KVM', 'QEMU', 'Microsoft Corporation', 'Xen']:
            if mftr == manufacturer:
                manufacturer = 'virtual'
                device.update({'manufacturer': 'vmware', })
                break
        if manufacturer != 'virtual':
            hw = to_ascii(d.get('productname', None))
            sn = to_ascii(d.get('serialnumber', None))

            if hw is not None: device.update({
                'manufacturer': manufacturer,
                'hardware': hw,
            })
            if sn != "None":
                device.update({'serial_no': sn, })

                #RAM
    if d.get('memorysize_mb', None) != None:
        memory = closest_memory_assumption(int(float(d['memorysize_mb'])))
        device.update({'memory': memory, })
    elif d.get('memorysize', None) != None:
        if d.get('memorysize', None).split(' ')[1] == 'MB':
            memory = closest_memory_assumption(int(float(d['memorysize'].split(' ')[0])))
        else:
            memory = closest_memory_assumption(int(float(d['memorysize'].split(' ')[0]) * 1024))
        device.update({'memory': memory, })


    #mem_c = d.get('memorysize_mb',None)
    #if mem_c is None:
    #    mem_b = d.get('memorysize',None).split(' ')[1]
    #    if mem_b is not None:
    #        if mem_b == 'MB':
    #            memory = closest_memory_assumption(int(float(d['memorysize'].split(' ')[0])))
    #        else: memory = closest_memory_assumption(int(float(d['memorysize'].split(' ')[0])*1024))
    #        device.update({'memory': memory,})
    #else:
    #    memory = closest_memory_assumption(int(float(d['memorysize_mb'])))
    #    device.update({'memory': memory,})

    #cpucount=Total CPUs, cpucore=Cores/CPU
    cpucount = d.get('physicalprocessorcount', None)
    if cpucount is not None:
        cpucount = int(cpucount)
        if cpucount == 0: cpucount = 1
        cpucore = int(d.get('processorcount', None))
        device.update({
            'cpucount': cpucount,
            'cpucore': cpucore,
        })
    cpuspeed = d.get('processor0', None)
    if cpuspeed is not None:
        #split to get the part after @ and before GHz
        if len(cpuspeed.split('@')) > 1:
            cpuspeed = int(1000 * float(cpuspeed.split('@')[1].split('GHz')[0]))
            device.update({'cpupower': cpuspeed, })

    #HDD, HDDSize is the sum of the drives 
    HDDSize = 0
    HDDCount = 0
    for i in range(1, 3):
        for j in range(1, 21):
            currentPhysicalDrive = "physicaldrive_" + str(i) + "i_1_" + str(j) + "_size"
            HDD = d.get(currentPhysicalDrive, None)
            if HDD is not None:
                HDDSize += float(HDD.split('_')[0])
                HDDCount += 1
    if HDDCount > 0:
        device.update({'hddcount': HDDCount, 'hddsize': HDDSize, })

    #Type, virtual or physical
    virtual = d.get('is_virtual', None)
    if virtual == 'true':
        device.update({'type': 'virtual', })
        device.pop('hardware', None)
    elif virtual == 'false':
        device.update({'type': 'physical', })
        #device.pop('hardware', None)

    #Interface 
    post(API_DEVICE_URL, device)
    if d.get('interfaces', None) != None:
        interfaces = d.get('interfaces', None).split(',')
        for interface in interfaces:
            if not 'loopback' in interface.lower():
                ipkey = 'ipaddress' + '_' + interface.replace(' ', '').lower()
                mackey = 'macaddress' + '_' + interface.replace(' ', '').lower()
                try:
                    macaddress = d[mackey]
                except:
                    macaddress = d.get('macaddress', None)
                ip = {
                    'ipaddress': d.get(ipkey, None),

                    'device': device_name,
                    'tag': interface.replace('_', ' ')
                }
                if macaddress is not None: ip.update({'macaddress': macaddress, })
                if ip.get('ipaddress') is not None and ip.get('ipaddress') != '127.0.0.1': post(API_IP_URL, ip)
    else:
        print
        "KEINE INTERFACES VORHANDEN!!!111"

