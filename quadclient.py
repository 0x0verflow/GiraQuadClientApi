import socket
import _thread
from time import sleep
import hashlib
import requests
import xml.etree.ElementTree as ET

TYPE_USUAL_DEVICE = 1
TYPE_GARAGE = 20

class QuadClient:
    """Inofficial Gira QuadClient API for Python - by 0x0verflow (https://github.com/0x0verflow/)"""

    class Device:
        device_id = None
        room_id = None
        friendly_device_name = None
        friendly_room_name = None
        val = None
        switch_on_id = None
        switch_off_id = None

        def __init__(self, device_id, room_id, friendly_device_name, friendly_room_name, val, switch_on_id, switch_off_id):
            self.device_id = device_id
            self.room_id = room_id
            self.friendly_device_name = friendly_device_name
            self.friendly_room_name
            self.val = val
            self.switch_on_id = switch_on_id
            self.switch_off_id = switch_off_id
            pass

    __so = None
    __listener_thread = None

    __timeout = 10.0

    __ip = None
    __port = None
    __username = None
    __password = None

    __debug_mode = False

    __connected = False
    __logged_in = False

    devices = list()

    def __init__(self, ip, username, password, port=80, timeout=10.0, debug_mode=False):
        self.__ip = ip
        self.__port = port
        self.__username = username
        self.__password = password
        self.__debug_mode = debug_mode
        self.__timeout = timeout
        pass

    def __log(self, msg):
        if self.__debug_mode:
            print("[QuadClient] " + msg)
        pass

    def connect(self):
        self.__log("Trying to connect to HomeServer...")

        # Building connection
        try:
            self.__so = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__so.settimeout(self.__timeout)
            self.__so.connect((self.__ip, self.__port))
            
            self.__connected = True
            
            # Start listener -> Authentification
            self.__listener_thread = _thread.start_new_thread(self.__listener, ())
            return True
        except socket.timeout:
            self.__log("Connection timed out. (Timeout: " + str(self.__timeout) + ")")
            return False
        except ConnectionRefusedError:
            self.__log("Connection refused by HomeServer at " + str(self.__ip))
            return False
        pass

    def disconnect(self):
        if not self.__connected:
            self.__log("You need to connect to a server before disconnecting")
            return False
        else:
            self.__so.close()
            return True

    def __listener(self):
        # Announce login
        self.__so.sendall(("GET /QUAD/LOGIN \r\n\r\n").encode())

        # Handle events
        try:
            while True:
                try:
                    raw_data = self.__so.recv(2048)

                    if raw_data:
                        data = str(raw_data.decode())
                        args = data.split("|")
                        event = int(args[0])

                        self.__log("< " + str(data))

                        self.__handle_event(event, args)
                except socket.error:
                    sleep(0.01)
        except KeyboardInterrupt:
            exit()
        pass

    def __handle_event(self, event, args):
        # Handle events

        if event == 100: # (Re)send username
            self.__send_telegram("90|" + self.__username + "|")
        elif event == 91: # (Re)send hashed password
            self.__send_telegram("92|" + self.__generate_hash(self.__username, self.__password, args[1]) + "|")
        elif event == 93: # Login successful
            self.__log("Login successful")
            self.__logged_in = True
            self.__log("Trying to download device list...")
            self.__index_devices(args[1])
        elif event == 0 or event == 1 or event == 2: # Device update
            self.__log("Received new device update")

            dev_found = False

            for d in self.devices:
                if d.device_id == args[1]:
                    d.val = float(args[2])
                    self.__log("(Direct) Updated value of " + str(d.device_id) + " to " + str(d.val))
                    dev_found = True
            
            if not dev_found:
                for d in self.devices:
                    if d.switch_on_id == args[1]:
                        d.val = float(args[2])
                        self.__log("(SwitchOn) Updated value of " + str(d.device_id) + " to " + str(d.val))
                        dev_found = True

            if not dev_found:
                for d in self.devices:
                    if d.switch_off_id == args[1]:
                        d.val = float(args[2])
                        self.__log("(SwitchOff) Updated value of " + str(d.device_id) + " to " + str(d.val))
                        dev_found = True

            if not dev_found:
                self.update_all_device_values()
        pass
    
    def __index_devices(self, query):
        # Download project info
        with requests.get("http://" + self.__ip + ":" + str(self.__port) + "/quad/client/client_project.xml?" + str(query), stream=True) as r:
                r.raise_for_status()
                with open(".proj_cache.xml", 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): 
                        if chunk:
                            f.write(chunk)

        # Process project info
        root = ET.parse(".proj_cache.xml").getroot()

        for room in root[0]:
            friendly_room_name = room.get("txt1")
            room_id = room[0].get("room")
            for dg in root[4]:
                if dg.get("id") == room_id:
                    for dev in dg:
                        friendly_device_name = dev.get("text")
                        device_id = dev.get("id")
                        switch_on_id = None
                        switch_off_id = None

                        for x in root[5]:
                            if x.get("id") == device_id:
                                switch_on_id = x[0].get("tag")
                                switch_off_id = x[1].get("tag")
                        
                        self.devices.append(self.Device(int(device_id), int(room_id), str(friendly_device_name), str(friendly_room_name), float(0), int(switch_on_id), int(switch_off_id)))
                        self.update_device_value(device_id)
                        self.__log("Found device: " + friendly_room_name + " -> " + friendly_device_name + "   (Room: " + str(room_id) + "; Device: " + str(device_id) + ")")
        pass

    def __send_telegram(self, msg):
        self.__log("> " + msg)
        self.__so.sendall((str(msg) + "\x00").encode())
        pass

    def __generate_hash(self, username, password, salt):
        salt = [ord(c) for c in salt]
        arr1 = [salt[i] ^ 92 if len(salt) > i else 92 for i in range(64)]
        arr2 = [salt[i] ^ 54 if len(salt) > i else 54 for i in range(64)]
        arr1 = "".join([chr(b) for b in arr1])
        arr2 = "".join([chr(b) for b in arr2])
        hash = hashlib.md5((arr2 + username + password).encode()).hexdigest().upper()
        hash = hashlib.md5((arr1 + hash).encode()).hexdigest().upper()
        return hash

    def update_device_value(self, device_id):
        if self.__logged_in:
            self.__log("Requesting new device update...")
            self.__send_telegram("2|" + str(device_id) + "|0")
            return True
        else:
            self.__log("You need to log in/connect before updating")
            return False
        pass

    def update_all_device_values(self):
        if self.__logged_in:
            for device in self.devices:
                self.update_device_value(device.device_id)
                sleep(0.5)
            self.__log("Updated all device values")
            return True
        else:
            self.__log("You need to log in/connect before updating")
            return False
        pass
        pass

    def set_device_value(self, device_type, device_id, val): 
        if self.__logged_in:
            self.__send_telegram(str(device_type) + "|" + str(device_id) + "|" + str(val))
            self.update_device_value(device_id)
            return True
        else:
            self.__log("You need to log in/connect before setting a value")
            return False
        pass

    def _send_telegram(self, msg):
        self.__send_telegram(msg)
        pass
