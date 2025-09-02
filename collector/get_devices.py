import yaml
import requests
import xml.etree.ElementTree as ET
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_managed_devices(pano_ip, api_key):
    url = f"https://{pano_ip}/api/?type=op&cmd=<show><devices><connected></connected></devices></show>&key={api_key}"
    response = requests.get(url, verify=False, timeout=10)
    tree = ET.fromstring(response.text)
    devices = []

    for entry in tree.findall('.//entry'):
        hostname = entry.findtext('hostname')
        serial = entry.findtext('serial')
        ip = entry.findtext('ip-address')

        # Skip empty or placeholder entries
        if not (hostname or serial or ip):
            continue

        device = {
            'hostname': hostname or '',
            'serial': serial or '',
            'model': entry.findtext('model', ''),
            'ip': ip or '',
            'connected': entry.findtext('connected', ''),
            'ha_state': entry.findtext('ha/state', '')
        }
        devices.append(device)

    return devices
