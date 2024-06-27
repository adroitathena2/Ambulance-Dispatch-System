import websockets
import websockets.sync.client
import time
import uuid
import sys

from common_networking import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtCore import Qt
from enum import Enum


#  ======================================== Main Window ========================================

"""These"""
RED_STYLE = "QLabel { color : red; }"
BLACK_STYLE = "QLabel { color : black; }"

class AmbStage(Enum):
    FREE = 1
    TO_PATIENT = 2
    TO_HOSPITAL = 3

class Window(QWidget):

    add_pck = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super(Window, self).__init__(*args, **kwargs)
        self.uuid = str(uuid.uuid4())
        self.connection_window = None
        self.webclient_wrk = None
        self.webclient_thr = None
        self.location_lat = 0.0
        self.location_long = 0.0
        self.pat_lat = 0.0
        self.pat_long = 0.0
        self.hsp_lat = 0.0
        self.hsp_long = 0.0
        self.current_stage: AmbStage = AmbStage.FREE
        self.setWindowTitle("Ambulance Driver")
        self.connected = False

        self.main_layout = QHBoxLayout(self)
        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()
        self.main_layout.addLayout(self.left_layout)
        self.main_layout.addLayout(self.right_layout)

        self.location_label = QLabel("")
        self.target_label = QLabel("Target: None")
        self.connect_btn = QPushButton("Connect to Server")
        self.connect_btn.clicked.connect(self.create_connection_window)
        self.reached_btn = QPushButton("Reached")
        self.reached_btn.setDisabled(True)
        self.reached_btn.clicked.connect(self.reached_btn_clicked)

        self.left_layout.addWidget(self.location_label)
        self.left_layout.addWidget(QLabel("Ambulance ID: " + self.uuid))
        self.left_layout.addWidget(self.target_label)
        self.right_layout.addWidget(self.connect_btn)
        self.right_layout.addWidget(self.reached_btn)

        auto_size = self.main_layout.sizeHint()
        auto_size.setHeight(auto_size.height() + 100)
        self.setFixedSize(auto_size)

        self.location_window = LocationWindow(self)
        self.location_window.show()

    def close_location_window(self, lat, long):
        self.location_window = None
        self.location_lat = lat
        self.location_long = long
        self.location_label.setText(f"Ambulance Location: {self.location_lat}, {self.location_long}")
        self.show()

    def create_connection_window(self):
        self.connection_window = ConnectionWindow(self)
        self.connection_window.show()

    def close_connection_window(self):
        self.connection_window = None
        self.connected = True

    def closeEvent(self, a0):
        self.connection_window = None
        super().closeEvent(a0)

    def run_webclient(self, ip_addr):
        self.webclient_wrk = AmbulanceWebClient(ip_addr, self)
        self.webclient_thr = QThread()
        self.webclient_wrk.moveToThread(self.webclient_thr)
        self.webclient_thr.started.connect(self.webclient_wrk.run)
        self.webclient_wrk.finished.connect(self.webclient_thr.quit)
        self.webclient_wrk.finished.connect(self.webclient_wrk.deleteLater)
        self.webclient_thr.finished.connect(self.webclient_thr.deleteLater)

        self.webclient_wrk.finished.connect(self.client_disconnected)
        self.webclient_wrk.connect_btn_status.connect(self.update_btn)
        self.webclient_wrk.connected.connect(self.close_connection_window)
        self.webclient_wrk.dispatch_requested.connect(self.dispatch_requested)

        self.webclient_thr.start()

    def update_btn(self, text, enabled):
        self.connect_btn.setText(text)
        self.connect_btn.setDisabled(not enabled)

        if self.connection_window is not None:
            self.connection_window.connection_window_btn.setText(text)
            self.connection_window.connection_window_btn.setDisabled(not enabled)

    def update_location(self, busy):
        self.location_label.setText(f"Location: {self.location_lat}, {self.location_long}")
        self.reached_btn.setDisabled(not busy)

        if self.connected:
            self.add_pck.emit(generate_json(C2S_AMBULANCE_STATUS, self.uuid, lat=self.location_lat,
                                        long=self.location_long, busy=busy))

    def dispatch_requested(self, pat_lat, pat_long, hsp_lat, hsp_long):
        self.pat_lat = pat_lat
        self.pat_long = pat_long
        self.hsp_lat = hsp_lat
        self.hsp_long = hsp_long
        self.update_location(True)
        self.target_label.setText(f"Patient Location: {pat_lat}, {pat_long}")
        self.target_label.setStyleSheet(RED_STYLE)
        self.current_stage = AmbStage.TO_PATIENT
        self.reached_btn.setText("Reached Patient")
        self.reached_btn.setDisabled(False)

    def reached_btn_clicked(self):
        if self.current_stage == AmbStage.FREE:
            self.update_location(False)
        elif self.current_stage == AmbStage.TO_PATIENT:
            self.reached_btn.setText("Reached Hospital")
            self.location_lat = self.pat_lat
            self.location_long = self.pat_long
            self.update_location(True)
            self.current_stage = AmbStage.TO_HOSPITAL
            self.target_label.setText(f"Hospital Location: {self.hsp_lat}, {self.hsp_lat}")
            self.target_label.setStyleSheet(RED_STYLE)
        elif self.current_stage == AmbStage.TO_HOSPITAL:
            self.reached_btn.setText("Reached")
            self.location_lat = self.hsp_lat
            self.location_long = self.hsp_long
            self.target_label.setText("Target: None")
            self.target_label.setStyleSheet(BLACK_STYLE)
            self.current_stage = AmbStage.FREE
            self.update_location(False)


    def client_disconnected(self):
        self.connected = False


#  ======================================== Web Client ========================================

class AmbulanceWebClient(QObject):
    finished = pyqtSignal()
    connect_btn_status = pyqtSignal(str, bool)
    dispatch_requested = pyqtSignal(float, float, float, float)
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
        if pck["type"] == S2C_DISPATCH_AMBULANCE:
            self.dispatch_requested.emit(pck["pat_lat"], pck["pat_long"],
                                         pck["hsp_lat"], pck["hsp_long"])
        else:
            print("Unknown packet:", pck)

    def run(self):
        self.connect_btn_status.emit("Connecting...", False)
        try:
            time.sleep(0.5)
            with websockets.sync.client.connect(self.ip_addr) as wssa:
                self.connect_btn_status.emit("Connected", False)
                self.connected.emit()
                wssa.send(generate_json(C2S_NEW_AMBULANCE_CONNECTED, self.uuid,
                                        lat=self.window.location_lat, long=self.window.location_long))

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
        self.setWindowTitle("Enter Ambulance Location")
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowCloseButtonHint)
        self.main_window = main_window
        self.location_window_layout = QVBoxLayout(self)

        self.location_window_label_addr = QLabel("Enter your ambulance address: ")
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
            self.main_window.close_location_window(lat_long[0], lat_long[1])
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


app = QApplication(sys.argv)
w = Window()
sys.exit(app.exec_())
