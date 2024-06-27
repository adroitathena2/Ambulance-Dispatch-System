import json
import socket
import requests

C2S_NEW_DISPATCHER_CONNECTED = 1  # pckid, uuid, lat, long, hsp_name
C2S_NEW_AMBULANCE_CONNECTED = 2  # pckid, uuid, lat, long
C2S_DISPATCH_REQUEST = 3  # pckid, uuid, lat, long
S2C_UPDATE_AMBULANCE_DISPATCH_INFO = 4  # pckid, "", amb_list=list[list[no., lat, long]],
# dsptch_list=list[list[lat, long]], free_amb_count, busy_amb_count, dsptch_count, patients_served
S2C_DISPATCH_AMBULANCE = 5  # pckid, "", pat_lat, pat_long, hsp_lat, hsp_long
C2S_AMBULANCE_STATUS = 6  # pckid, uuid, lat, long, busy
S2C_AMBULANCE_REACHED = 7  # pckid, "", no., hsp_name


def generate_json(payload_type, client_uuid, **kwargs):
    d = {"type": payload_type, "uuid": client_uuid}

    for i in kwargs:
        d[i] = kwargs[i]
    return json.dumps(d)


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def get_lat_long_from_addr(address):
    req_link = ("https://dev.virtualearth.net/REST/v1/Locations"
                "?query=" + address + "&maxResults=1"
                "&key=AnPmjr3zZA4MHAyvsd-dCEcwpd-A1n6sasRCathmB53DXcb7pb6CO6MnnWKj1fre")

    req = requests.get(req_link)
    map_json = req.json()
    if len(map_json["resourceSets"]) > 0:
        if len(map_json["resourceSets"][0]["resources"]) > 0:
            return map_json["resourceSets"][0]["resources"][0]["point"]["coordinates"]

    return None
