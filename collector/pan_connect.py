import requests
import urllib3
import xml.etree.ElementTree as ET

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_api_key(pano_ip, username, password):
    url = f"https://{pano_ip}/api/?type=keygen&user={username}&password={password}"
    response = requests.get(url, verify=False, timeout=10)

    if response.status_code != 200:
        raise Exception(f"HTTP error {response.status_code} from {pano_ip}")

    tree = ET.fromstring(response.text)
    key_node = tree.find('.//key')

    if key_node is None:
        msg_node = tree.find('.//msg')
        error = msg_node.text if msg_node is not None else "Unknown error"
        raise Exception(f"Failed to get API key from {pano_ip}: {error}")

    return key_node.text

