import asyncio
import websockets
from websockets.server import serve
from common_networking import *
import copy


class Location:
    def __init__(self, lat, long):
        self.lat = lat
        self.long = long

    def distance_to(self, lat, long):
        return ( ( (self.lat - lat) ** 2 ) + ( (self.long - long) ** 2) ) ** 0.5

    def __eq__(self, other):
        return (self.lat == other.lat) and (self.long == other.long)


class DispatchReq(Location):
    def __init__(self, lat, long, sender):
        super().__init__(lat, long)
        self.lat = lat
        self.long = long
        self.sender = sender

    def __eq__(self, other):
        return (self.lat == other.lat) and (self.long == other.long) and (self.sender == other.sender)


class DispatcherClient(Location):
    def __init__(self, lat, long, uuid, name):
        super().__init__(lat, long)
        self.uuid = uuid
        self.name = name

    def __eq__(self, other):
        return self.uuid == other.uuid


class AmbulanceClient(Location):
    def __init__(self, lat, long, uuid):
        super().__init__(lat, long)
        self.uuid = uuid
        self.busy = False
        self.dsp_req: DispatchReq = None

    def __str__(self):
        return f"UUID: {self.uuid}, Location: {self.lat}, {self.long}, Busy: {self.busy}"

    def __eq__(self, other):
        return self.uuid == other.uuid


DISPATCHER_CLIENTS = {}
AMBULANCE_CLIENTS = {}
AMBULANCE_CLIENTS_LAST = {}
FORCE_UPDATE = False
DISPATCH_REQUESTS = []
DISPATCH_REQUESTS_LAST = []
PACKETS_TO_SEND = []
PATIENTS_SERVED = 0
PATIENTS_SERVED_LAST = 0


def compare_amb_dsp_data_list():
    global AMBULANCE_CLIENTS_LAST, DISPATCH_REQUESTS_LAST, PATIENTS_SERVED_LAST
    ret = False
    for i in AMBULANCE_CLIENTS:
        if i not in AMBULANCE_CLIENTS_LAST:
            ret = True
            break

    if not ret:
        for i in AMBULANCE_CLIENTS:
            if AMBULANCE_CLIENTS_LAST[i] != AMBULANCE_CLIENTS[i]:
                ret = True
                break

    AMBULANCE_CLIENTS_LAST = {}
    for i in AMBULANCE_CLIENTS:
        AMBULANCE_CLIENTS_LAST[i] = copy.deepcopy(AMBULANCE_CLIENTS[i])

    if len(DISPATCH_REQUESTS_LAST) != len(DISPATCH_REQUESTS):
        ret = True
    else:
        for i in range(0, len(DISPATCH_REQUESTS)):
            if DISPATCH_REQUESTS_LAST[i] != DISPATCH_REQUESTS[i]:
                ret = True
                break

    DISPATCH_REQUESTS_LAST = copy.deepcopy(DISPATCH_REQUESTS)

    ret |= (PATIENTS_SERVED_LAST != PATIENTS_SERVED)
    PATIENTS_SERVED_LAST = copy.deepcopy(PATIENTS_SERVED)

    return ret


def new_dispatcher_client(payload, websocket):
    global FORCE_UPDATE
    uuid = payload["uuid"]
    lat = payload["lat"]
    long = payload["long"]
    hsp_name = payload["hsp_name"]
    DISPATCHER_CLIENTS[websocket] = DispatcherClient(lat, long, uuid, hsp_name)
    print(f"New dispatcher client {hsp_name} with uuid {uuid}, location {lat}, {long} connected.")
    FORCE_UPDATE = True


def new_ambulance_client(payload, websocket):
    uuid = payload["uuid"]
    lat = payload["lat"]
    long = payload["long"]
    AMBULANCE_CLIENTS[websocket] = AmbulanceClient(lat, long, uuid)
    print(f"New ambulance client with uuid {uuid}, location {lat}, {long} connected.")


def new_dispatch_request(payload, websocket):
    uuid = payload["uuid"]
    lat = payload["lat"]
    long = payload["long"]
    print(f"Received new dispatch request from uuid {uuid}, location {lat}, {long}.")
    DISPATCH_REQUESTS.append(DispatchReq(lat, long, uuid))


def try_dispatch_ambs():
    done_reqs = []
    for req in DISPATCH_REQUESTS:
        closest_amb = [-1, 9999999999999999.0]
        for i in AMBULANCE_CLIENTS:
            amb: AmbulanceClient = AMBULANCE_CLIENTS[i]
            if not amb.busy:
                dist = amb.distance_to(req.lat, req.long)
                if closest_amb[1] > dist:
                    closest_amb[0] = i
                    closest_amb[1] = dist

        if closest_amb[0] != -1:
            amb: AmbulanceClient = AMBULANCE_CLIENTS[closest_amb[0]]
            closest_amb_found: AmbulanceClient = AMBULANCE_CLIENTS[closest_amb[0]]
            closest_dispatcher = [0, 9999999999999999.0]
            for i in DISPATCHER_CLIENTS:
                dsp: DispatcherClient = DISPATCHER_CLIENTS[i]
                dist = req.distance_to(dsp.lat, dsp.long)
                if dist < closest_dispatcher[1]:
                    closest_dispatcher[0] = i
                    closest_dispatcher[1] = dist

            closest_dsp_found: DispatcherClient = DISPATCHER_CLIENTS[closest_dispatcher[0]]
            pck_data = generate_json(S2C_DISPATCH_AMBULANCE, "", pat_lat=req.lat, pat_long=req.long,
                                     hsp_lat=closest_dsp_found.lat, hsp_long=closest_dsp_found.long)
            PACKETS_TO_SEND.append(([closest_amb[0]], pck_data))
            print(f"Dispatching ambulance {str(amb)} to {req.lat}, {req.long}.")
            closest_amb_found.busy = True
            closest_amb_found.dsp_req = copy.deepcopy(req)

            done_reqs.append(req)

    update_ambulance_dispatch_data()
    for i in done_reqs:
        DISPATCH_REQUESTS.remove(i)


def ambulance_update(payload, websocket):
    global PATIENTS_SERVED
    uuid = payload["uuid"]

    for i in AMBULANCE_CLIENTS:
        if AMBULANCE_CLIENTS[i].uuid == uuid:
            amb: AmbulanceClient = AMBULANCE_CLIENTS[i]
            amb.lat = payload["lat"]
            amb.long = payload["long"]

            if amb.busy and (not payload["busy"]):
                PATIENTS_SERVED += 1
                hsp_name = f"{amb.lat}, {amb.long}"
                for j in DISPATCHER_CLIENTS.items():
                    if (j[1].lat == amb.lat) and (j[1].long == amb.long):
                        hsp_name = j[1].name
                        break

                amb_wss = list(AMBULANCE_CLIENTS.keys())
                PACKETS_TO_SEND.append(([x[0] for x in DISPATCHER_CLIENTS.items()
                                         if x[1].uuid == amb.dsp_req.sender],
                                        generate_json(S2C_AMBULANCE_REACHED, "",
                                        amb_no=amb_wss.index(i),
                                                      hsp_name=hsp_name))
                                       )

            amb.busy = payload["busy"]
            print(f"Recieved update from ambulance {amb.uuid}: Location: {amb.lat}, {amb.long}, Busy: {amb.busy}.")


def update_ambulance_dispatch_data():
    global FORCE_UPDATE
    cmped = compare_amb_dsp_data_list()
    if (not cmped) and (not FORCE_UPDATE):
        return
    if not cmped:
        FORCE_UPDATE = False

    amb_list = []
    dsptch_list = []

    idx = 0
    free_count = 0
    for i in AMBULANCE_CLIENTS:
        idx += 1
        cl: AmbulanceClient = AMBULANCE_CLIENTS[i]
        if not cl.busy:
            amb_list.append([idx, cl.lat, cl.long])
            free_count += 1

    for i in DISPATCH_REQUESTS:
        dsptch_list.append([i.lat, i.long])

    dat = generate_json(S2C_UPDATE_AMBULANCE_DISPATCH_INFO, "", amb_list=amb_list,
                        dsptch_list=dsptch_list, free_amb_count=free_count,
                        busy_amb_count=len(AMBULANCE_CLIENTS) - free_count,
                        dsptch_count=len(DISPATCH_REQUESTS), patients_served=PATIENTS_SERVED)

    all_disp = [x for x in DISPATCHER_CLIENTS.keys()]

    PACKETS_TO_SEND.append((all_disp, dat))


def handle_payload(payload, websocket):
    print(f"{payload['uuid']} -> srv:", payload)
    payload_type = payload["type"]
    if payload_type == C2S_NEW_DISPATCHER_CONNECTED:
        new_dispatcher_client(payload, websocket)
    elif payload_type == C2S_NEW_AMBULANCE_CONNECTED:
        new_ambulance_client(payload, websocket)
    elif payload_type == C2S_DISPATCH_REQUEST:
        new_dispatch_request(payload, websocket)
    elif payload_type == C2S_AMBULANCE_STATUS:
        ambulance_update(payload, websocket)
        pass
    else:
        print(f"Unknown packet:", payload)


async def receive_incoming(websocket):
    try:
        async for message in websocket:
            try:
                payload = json.loads(message)
                if ("uuid" in payload) and ("type" in payload):
                    handle_payload(payload, websocket)
                else:
                    raise json.JSONDecodeError("Missing params: id or uuid.", "", 0)
            except json.JSONDecodeError:
                print("Failed to parse payload.")
                print(message)
    except websockets.ConnectionClosedError:
        await client_disconnect(websocket)


async def client_disconnect(websocket):
    global FORCE_UPDATE
    if websocket in DISPATCHER_CLIENTS:
        dsptch: DispatcherClient = DISPATCHER_CLIENTS[websocket]
        print(f"Dispatcher client disconnected: {dsptch.uuid}.")
        del DISPATCHER_CLIENTS[websocket]
    elif websocket in AMBULANCE_CLIENTS:
        amb: AmbulanceClient = AMBULANCE_CLIENTS[websocket]
        print(f"Ambulance client disconnected: {amb.uuid}.")
        FORCE_UPDATE = True
        del AMBULANCE_CLIENTS[websocket]


async def send_outgoing(websocket):
    while True:
        update_ambulance_dispatch_data()
        try_dispatch_ambs()

        pcks_done = []
        for pckIdx in range(0, len(PACKETS_TO_SEND)):
            pckData = PACKETS_TO_SEND[pckIdx]
            if len(pckData[0]) == 0:
                print("srv -> cl", pckData[1])
                pcks_done.append(pckData)
            try:
                try:
                    idxInList = pckData[0].index(websocket)
                    await websocket.send(pckData[1])
                    del pckData[0][idxInList]
                except ValueError:
                    pass
            except websockets.ConnectionClosedError:
                await client_disconnect(websocket)

        for i in pcks_done:
            PACKETS_TO_SEND.remove(i)

        await asyncio.sleep(1)


async def handle(websocket):
    consumer_task = asyncio.create_task(receive_incoming(websocket))
    producer_task = asyncio.create_task(send_outgoing(websocket))
    done, pending = await asyncio.wait(
        [consumer_task, producer_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()


async def main():
    server_started = False
    for i in range(0, 100):
        try:
            while True:
                server_addr = get_local_ip()
                async with serve(handle, server_addr, 12100 + i):
                    server_started = True
                    print(f"Hosted server on: {server_addr}:{12100 + i}")
                    await asyncio.Future()
        except OSError as err:
            if err.errno != 10048:
                raise err

    if not server_started:
        print("Could not find any free port in range 12100-12200!")


asyncio.run(main())
