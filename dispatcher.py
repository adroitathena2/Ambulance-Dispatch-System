import websockets
import websockets.sync.client
import time
import uuid
import sys

from common_networking import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtCore import Qt


#  ======================================== Main Window ========================================

class Window(QWidget):
    add_pck = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super(Window, self).__init__(*args, **kwargs)
        self.uuid = str(uuid.uuid4())
        self.connection_window = None
        self.dispatch_window = None
        self.reached_window = None
        self.webclient_wrk = None
        self.webclient_thr = None
        self.location_lat = 0.0
        self.location_long = 0.0
        self.hsp_name = ""
        self.setWindowTitle("Ambulance Dispatcher")

        self.main_layout = QHBoxLayout(self)
        self.left_layout = QVBoxLayout()
        self.middle_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()
        self.main_layout.addLayout(self.left_layout)
        self.main_layout.addLayout(self.middle_layout)
        self.main_layout.addLayout(self.right_layout)

        self.avail_amb = QTableWidget(self)
        self.avail_amb.setAlternatingRowColors(True)
        self.avail_amb.setSelectionMode(QAbstractItemView.NoSelection)
        self.avail_amb.setColumnCount(3)
        self.avail_amb.setHorizontalHeaderLabels(["No.", "Latitude", "Longitude"])
        self.avail_amb.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.avail_amb.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.avail_amb.verticalHeader().hide()

        self.dispatch_reqs = QTableWidget(self)
        self.dispatch_reqs.setAlternatingRowColors(True)
        self.dispatch_reqs.setColumnCount(2)
        self.dispatch_reqs.setHorizontalHeaderLabels(["Latitude", "Longitude"])
        self.dispatch_reqs.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.dispatch_reqs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        self.location_label = QLabel("")
        self.hsp_name_label = QLabel("")
        self.avail_amb_count_label = QLabel("Available Ambulances: 0")
        self.busy_amb_count_label = QLabel("Busy Ambulances: 0")
        self.dsptch_req_count_label = QLabel("Dispatch Requests: 0")
        self.patients_served_label = QLabel("Patients Served: 0")
        self.connect_btn = QPushButton("Connect to Server")
        self.connect_btn.clicked.connect(self.create_connection_window)
        self.dispatch_btn = QPushButton("Add Dispatch Request")
        self.dispatch_btn.clicked.connect(self.create_dispatch_window)
        self.dispatch_btn.setDisabled(True)

        self.left_layout.addWidget(QLabel("Available Ambulances:", self))
        self.left_layout.addWidget(self.avail_amb)

        self.middle_layout.addWidget(QLabel("Pending Dispatch Requests:", self))
        self.middle_layout.addWidget(self.dispatch_reqs)

        self.right_layout.addWidget(self.avail_amb_count_label)
        self.right_layout.addWidget(self.dsptch_req_count_label)
        self.right_layout.addWidget(self.busy_amb_count_label)
        self.right_layout.addWidget(self.patients_served_label)
        self.right_layout.addWidget(self.hsp_name_label)
        self.right_layout.addWidget(self.location_label)
        self.right_layout.addWidget(QLabel("Dispatcher ID: " + self.uuid))
        self.right_layout.addWidget(self.dispatch_btn)
        self.right_layout.addWidget(self.connect_btn)

        auto_size = self.main_layout.sizeHint()
        auto_size.setHeight(auto_size.height() + 100)
        self.setFixedSize(auto_size)

        self.location_window = LocationWindow(self)
        self.location_window.show()

    def close_location_window(self, lat, long, hsp_name):
        self.location_window = None
        self.location_lat = lat
        self.location_long = long
        self.hsp_name = hsp_name
        self.location_label.setText(f"Hospital Location: {self.location_lat}, {self.location_long}")
        self.hsp_name_label.setText(f"Hospital Name: {self.hsp_name}")
        self.show()

    def create_dispatch_window(self):
        self.dispatch_window = DispatchWindow(self)
        self.dispatch_window.show()

    def close_dispatch_window(self, lat, long):
        self.dispatch_window = None
        self.add_pck.emit(generate_json(C2S_DISPATCH_REQUEST, self.uuid, lat=lat, long=long))

    def create_connection_window(self):
        self.connection_window = ConnectionWindow(self)
        self.connection_window.show()

    def close_connection_window(self):
        self.dispatch_btn.setDisabled(False)
        self.connection_window = None

    def closeEvent(self, a0):
        self.connection_window = None
        self.dispatch_window = None
        self.location_window = None
        self.reached_window = None
        super().closeEvent(a0)

    def run_webclient(self, ip_addr):
        self.webclient_wrk = DispatcherWebClient(ip_addr, self)
        self.webclient_thr = QThread()
        self.webclient_wrk.moveToThread(self.webclient_thr)
        self.webclient_thr.started.connect(self.webclient_wrk.run)
        self.webclient_wrk.finished.connect(self.webclient_thr.quit)
        self.webclient_wrk.finished.connect(self.webclient_wrk.deleteLater)
        self.webclient_thr.finished.connect(self.webclient_thr.deleteLater)

        self.webclient_thr.finished.connect(self.client_disconnected)
        self.webclient_wrk.connect_btn_status.connect(self.update_btn)
        self.webclient_wrk.connected.connect(self.close_connection_window)
        self.webclient_wrk.update_info.connect(self.update_info)
        self.webclient_wrk.amb_reached.connect(self.amb_reached)

        self.webclient_thr.start()

    def update_info(self, amb_list, dsptch_list, free_amb_count, busy_amb_count, dsptch_count, patients_served):
        self.avail_amb_count_label.setText("Available Ambulances: " + str(free_amb_count))
        self.busy_amb_count_label.setText("Busy Ambulances: " + str(busy_amb_count))
        self.dsptch_req_count_label.setText("Dispatch Requests: " + str(dsptch_count))
        self.patients_served_label.setText("Patients Served: " + str(patients_served))

        self.avail_amb.setRowCount(len(amb_list))
        self.dispatch_reqs.setRowCount(len(dsptch_list))

        for i in range(0, len(amb_list)):
            amb_dat = amb_list[i]
            for j in range(0, 3):
                ins_item = QTableWidgetItem(str(amb_dat[j]))
                ins_item.setFlags(ins_item.flags() ^ (Qt.ItemIsEditable | Qt.ItemIsSelectable))
                self.avail_amb.setItem(i, j, ins_item)

        for i in range(0, len(dsptch_list)):
            dsp_dat = dsptch_list[i]
            for j in range(0, 2):
                ins_item = QTableWidgetItem(str(dsp_dat[j]))
                ins_item.setFlags(ins_item.flags() ^ (Qt.ItemIsEditable | Qt.ItemIsSelectable))
                self.dispatch_reqs.setItem(i, j, ins_item)

    def update_btn(self, text, enabled):
        self.connect_btn.setText(text)
        self.connect_btn.setDisabled(not enabled)

        if self.connection_window is not None:
            self.connection_window.connection_window_btn.setText(text)
            self.connection_window.connection_window_btn.setDisabled(not enabled)

    def amb_reached(self, amb_no, amb_name):
        self.reached_window = ReachedWindow(self, amb_no, amb_name)
        self.reached_window.show()

    def client_disconnected(self):
        self.dispatch_window = None
        self.dispatch_btn.setDisabled(True)
        self.avail_amb.setRowCount(0)
        self.dispatch_reqs.setRowCount(0)


#  ======================================== Web Client ========================================

class DispatcherWebClient(QObject):
    finished = pyqtSignal()
    connect_btn_status = pyqtSignal(str, bool)
    update_info = pyqtSignal(list, list, int, int, int, int)
    amb_reached = pyqtSignal(int, str)
    connected = pyqtSignal()

    def __init__(self, ip_addr, window: Window):
        super().__init__()
        self.ip_addr = ip_addr
        self.uuid = window.uuid
        self.pck_list = []
        self.window = window
        window.add_pck.connect(self.add_packet)

    def add_packet(self, packet):
        self.pck_list.append(packet)

    def handle_packet(self, pck):
        if pck["type"] == S2C_UPDATE_AMBULANCE_DISPATCH_INFO:
            self.update_info.emit(pck["amb_list"], pck["dsptch_list"], pck["free_amb_count"],
                                  pck["busy_amb_count"], pck["dsptch_count"], pck["patients_served"])
        elif pck["type"] == S2C_AMBULANCE_REACHED:
            self.amb_reached.emit(pck["amb_no"], pck["hsp_name"])
        else:
            print("Unknown packet:", pck)

    def run(self):
        self.connect_btn_status.emit("Connecting...", False)
        try:
            time.sleep(0.5)
            with websockets.sync.client.connect(self.ip_addr) as wssa:
                self.connect_btn_status.emit("Connected", False)
                self.connected.emit()
                wssa.send(generate_json(C2S_NEW_DISPATCHER_CONNECTED, self.uuid,
                                        lat=self.window.location_lat, long=self.window.location_long,
                                        hsp_name=self.window.hsp_name))

                while True:
                    while True:
                        for i in self.pck_list:
                            wssa.send(i)
                        self.pck_list = []
                        try:
                            while True:
                                pck = wssa.recv(0.5)
                                self.handle_packet(json.loads(pck))
                        except TimeoutError:
                            pass

        except (websockets.ConnectionClosedOK, websockets.ConnectionClosedError):
            print("Connection closed.")
        except websockets.InvalidURI:
            print("Invalid URL.")
        except ConnectionRefusedError:
            print("Connection refused.")
        except ConnectionResetError:
            print("Connection reset.")
        except TimeoutError:
            print("Connection Timed out.")
        finally:
            self.connect_btn_status.emit("Connect", True)

        self.finished.emit()


#  ======================================== Sub Windows ========================================

class LocationWindow(QWidget):
    def __init__(self, main_window: Window, *args, **kwargs):
        super(LocationWindow, self).__init__(*args, **kwargs)
        self.setWindowTitle("Enter Hospital Location")
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowCloseButtonHint)
        self.main_window = main_window
        self.location_window_layout = QVBoxLayout(self)

        self.location_window_label_addr = QLabel("Enter your hospital address: ")
        self.location_window_text_box_addr = QLineEdit("")
        self.location_window_text_box_addr.textEdited.connect(self.text_boxes_changed)

        self.location_window_label_name = QLabel("Enter your hospital name: ")
        self.location_window_text_box_name = QLineEdit("")
        self.location_window_text_box_name.textEdited.connect(self.text_boxes_changed)

        self.location_window_btn = QPushButton("Set Location")
        self.location_window_btn.clicked.connect(self.location_button_clicked)
        self.location_window_btn.setDisabled(True)

        self.location_window_layout.addWidget(self.location_window_label_addr)
        self.location_window_layout.addWidget(self.location_window_text_box_addr)
        self.location_window_layout.addWidget(self.location_window_label_name)
        self.location_window_layout.addWidget(self.location_window_text_box_name)
        self.location_window_layout.addWidget(self.location_window_btn)

        self.setFixedSize(QSize(400, 150))

    def text_boxes_changed(self):
        addr_text = self.location_window_text_box_addr.text().strip()
        name_text = self.location_window_text_box_name.text().strip()
        self.location_window_btn.setDisabled((addr_text == "") or (name_text == ""))

    def location_button_clicked(self):
        addr_text = self.location_window_text_box_addr.text().strip()
        name_text = self.location_window_text_box_name.text().strip()
        self.location_window_btn.setDisabled(True)
        self.location_window_btn.setText("Fetching Location...")
        lat_long = get_lat_long_from_addr(addr_text)

        if lat_long is not None:
            self.main_window.close_location_window(lat_long[0], lat_long[1], name_text)
        else:
            self.location_window_text_box_addr.setText("Address could not be found!")
            self.location_window_btn.setText("Set Location")
            self.location_window_btn.setDisabled(False)


class DispatchWindow(QWidget):
    def __init__(self, main_window: Window, *args, **kwargs):
        super(DispatchWindow, self).__init__(*args, **kwargs)
        self.setWindowTitle("Enter Patient Location")
        self.main_window = main_window
        self.location_window_layout = QVBoxLayout(self)

        self.location_window_label_addr = QLabel("Enter your patient address: ")
        self.location_window_text_box_addr = QLineEdit("")
        self.location_window_text_box_addr.textEdited.connect(self.addr_changed)

        self.location_window_btn = QPushButton("Set Location")
        self.location_window_btn.clicked.connect(self.location_button_clicked)
        self.location_window_btn.setDisabled(True)

        self.location_window_layout.addWidget(self.location_window_label_addr)
        self.location_window_layout.addWidget(self.location_window_text_box_addr)
        self.location_window_layout.addWidget(self.location_window_btn)

        self.setFixedSize(QSize(400, 100))

    def addr_changed(self):
        addr_text = self.location_window_text_box_addr.text().strip()
        self.location_window_btn.setDisabled(addr_text == "")

    def location_button_clicked(self):
        addr_text = self.location_window_text_box_addr.text().strip()
        self.location_window_btn.setDisabled(True)
        self.location_window_btn.setText("Fetching Location...")
        lat_long = get_lat_long_from_addr(addr_text)

        if lat_long is not None:
            self.main_window.close_dispatch_window(lat_long[0], lat_long[1])
        else:
            self.location_window_text_box_addr.setText("Address could not be found!")
            self.location_window_btn.setText("Set Location")
            self.location_window_btn.setDisabled(False)


class ConnectionWindow(QWidget):
    def __init__(self, main_window: Window, *args, **kwargs):
        super(ConnectionWindow, self).__init__(*args, **kwargs)
        self.setWindowTitle("Connect to Server")
        self.main_window = main_window
        self.connection_window_layout = QVBoxLayout(self)
        self.connection_window_label = QLabel("Enter the server IP: ")
        self.connection_window_text_box = QLineEdit("ws://" + get_local_ip() + ":12100")
        self.connection_window_btn = QPushButton("Connect")
        self.connection_window_btn.clicked.connect(self.connect_button_clicked)

        self.connection_window_layout.addWidget(self.connection_window_label)
        self.connection_window_layout.addWidget(self.connection_window_text_box)
        self.connection_window_layout.addWidget(self.connection_window_btn)

        self.setFixedSize(QSize(400, 100))

    def connect_button_clicked(self):
        url = self.connection_window_text_box.text()
        self.main_window.run_webclient(url)


class ReachedWindow(QWidget):
    def __init__(self, main_window: Window, amb_no, hsp_name, *args, **kwargs):
        super(ReachedWindow, self).__init__(*args, **kwargs)
        self.setWindowTitle("Ambulance Reached")
        self.main_window = main_window
        self.window_layout = QVBoxLayout(self)
        self.label = QLabel(f"Ambulance {amb_no + 1} has brought the patient to the hospital {hsp_name}!")
        self.label.setAlignment(Qt.AlignHCenter)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        self.window_layout.addWidget(self.label)
        self.window_layout.addWidget(self.close_btn)

        self.setFixedSize(QSize(600, 100))


app = QApplication(sys.argv)
w = Window()
sys.exit(app.exec_())
