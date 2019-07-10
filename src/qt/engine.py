import logging
import json
import zmq
from uuid import uuid4

from PyQt5.QtCore import QObject, pyqtSignal

from .engine_subscriber import EngineSubscriber
from .heartbeat_listener import HeartBeatListener

class Engine(QObject):
    """
    Remote Engine Wrapper for PyQt

    Handles all communication with the engine and defines signals for state changes and events.
    """

    bandFound = pyqtSignal(str, int)
    connectNearestCandidateUpdatedGlobal = pyqtSignal(str, int)

    searchStopped = pyqtSignal()
    searchStarted = pyqtSignal()

    connectionStateChangedGlobal = pyqtSignal(str, str)
    activationStateChangedGlobal = pyqtSignal(str, bool)
    buttonStateChangedGlobal = pyqtSignal(str, bool)
    batteryChangedGlobal = pyqtSignal(str, int)
    streamQualityChangedGlobal = pyqtSignal(str, int)

    gestureGlobal = pyqtSignal(str, str)
    mouseMovedGlobal = pyqtSignal(str, float, float, str)

    bound = pyqtSignal(bool)

    search_and_connect_finished = pyqtSignal(str, bool)

    def __init__(self, config, pubAddress, rpcAddress):
        super(Engine, self).__init__()
        self._logger = logging.getLogger(__name__ + ".Engine")

        self.config = config
        self._band = None

        self.currently_searching = False
        self._bound = False
        self._bands = self.config.favorite_bands[:]
        self._resetStates()

        self._ctx = zmq.Context()
        self._rpcSocket = None
        self._subscriber = None
        self._heartbeatListener = HeartBeatListener()
        self._heartbeatListener.connectionEstablished.connect(self._bound_engine)
        self._heartbeatListener.connectionLost.connect(self._unbound_engine)

        self._setupSubscriber(pubAddress)
        self._setupRpcSocket(rpcAddress)

    def changeAddresses(self, pubAddress, rpcAddress):
        self._unbound_engine()
        self._setupSubscriber(pubAddress)
        self._setupRpcSocket(rpcAddress)

    def stop(self):
        if self._subscriber is not None:
            self._subscriber.message.disconnect()
            self._subscriber.stop()
            self._subscriber = None

        if self._rpcSocket is not None:
            self._rpcSocket.close()
            self._rpcSocket = None

        if self._heartbeatListener is not None:
            self._heartbeatListener.stop()
            self._heartbeatListener = None

    def _resetStates(self):
        self._battery = {}
        self._connectionState = {}
        self._connectionReason = {}
        self._streamQuality = {}
        self._activationState = {}
        self._requiredGesturePrecision = {}
        self.currently_searching = False

        for band in self._bands: 
            self.connectionStateChangedGlobal.emit(band, "DISCONNECTED")

        self._bands = self.config.favorite_bands[:]

    def _resetState(self, band):
        if band in self._bands and band not in self.config.favorite_bands:
            self._bands.remove(band)

        self._connectionState[band] = None
        self._connectionReason[band] = None
        self._battery[band] = None
        self._streamQuality[band] = None
        self._activationState[band] = None
        self._requiredGesturePrecision[band] = None

        self.connectionStateChangedGlobal.emit(band, "DISCONNECTED")
        
    def _initStates(self):
        recent_bands = self._bands
        cur_bands = self._sendRequest("getBands")
        self._bands = self.config.favorite_bands[:]
        if cur_bands is not None:
            for band in cur_bands:
                if band not in self._bands:
                    self._bands += [band]

        if self._bands is None:
            self._unbound_engine()
            return

        for band in recent_bands:
            if band not in self._bands:
                self._resetState(band)

        for band in self._bands:
            self._initState(band)

    def _initState(self, band):
        if band not in self._bands:
            self._bands.append(band)

        self._connectionState[band] = self._sendRequest(
            "getConnectionStateName", band=band)
        self._connectionReason[band] = None
        self._battery[band] = self._sendRequest("getBattery", band=band)
        self._streamQuality[band] = self._sendRequest("getStreamQuality", band=band)
        self._activationState[band] = self._sendRequest("getActivationState", band=band)
        self._requiredGesturePrecision[band] = self._sendRequest("getRequiredGesturePrecisionName", band=band)
        
        if (self._connectionState[band] is None 
            or self._battery[band] is None 
            or self._streamQuality[band] is None 
            or self._activationState[band] is None):
            self._unbound_engine()
            return

        self.connectionStateChangedGlobal.emit(band, self._connectionState[band])
        self.batteryChangedGlobal.emit(band, self._battery[band])
        self.streamQualityChangedGlobal.emit(band, self._streamQuality[band])
        self.activationStateChangedGlobal.emit(band, self._activationState[band])

    def _setupRpcSocket(self, address):
        if self._rpcSocket is not None:
            self._rpcSocket.close()

        self._rpcSocket = self._ctx.socket(zmq.DEALER)
        self._rpcSocket.connect(address)
        
        self._poller = zmq.Poller()
        self._poller.register(self._rpcSocket, zmq.POLLIN)

    def _setupSubscriber(self, address):
        if self._subscriber is None:
            self._subscriber = EngineSubscriber(self._ctx, address)
            self._subscriber.message.connect(self._handleMessage)
        else:
            self._subscriber.change_address(address)

    def buzzBand(self, band, duration_millis):
        return self._sendRequest("buzz", band=band, duration_millis=duration_millis)

    def setLedOfBand(self, band, color=None, red=False, blue=False, green=False, pattern=None):
        if color is not None:
            if color == "RED":
                red = True
                green = False
                blue = False  
            elif color == "GREEN":
                red = False
                green = True
                blue = False
            elif color == "BLUE":
                red = False
                green = False
                blue = True
            elif color == "MAGENTA":
                red = True
                green = False
                blue = True
            elif color == "YELLOW":
                red = True
                green = True
                blue = False
            elif color == "CYAN":
                red = False
                green = True
                blue = True
            elif color == "WHITE":
                red = True
                green = True
                blue = True
            elif color == "OFF" or color == "BLACK":
                red = False
                green = False
                blue = False
        if pattern == "BLINK":
            pattern = {
                "high_intensity": 31,
                "low_intensity": 0,
                "rise_time_ms": 200,
                "high_time_ms": 400,
                "fall_time_ms": 200,
                "pulse_duration_ms": 1800,
                "delay_time_ms": 0,
                "repeat_count": 0xff
            }
        elif pattern == "FAST_BLINK":
            pattern = {
                "high_intensity": 31,
                "low_intensity": 0,
                "rise_time_ms": 0,
                "high_time_ms": 150,
                "fall_time_ms": 0,
                "pulse_duration_ms": 300,
                "delay_time_ms": 0,
                "repeat_count": 0xff
            }

        if pattern is None:
            return self._sendRequest("setLed", band=band, red=red, green=green, blue=blue)
        else:
            return self._sendRequest("setLedPattern", band=band, red=red, green=green, blue=blue, pattern=pattern)

    def getConnectionStateOfBand(self, band):
        return self._connectionState.get(band, "DISCONNECTED") or "DISCONNECTED"

    def getConnectionReasonOfBand(self, band):
        return self._connectionReason.get(band, None) or None

    def getActivationStateOfBand(self, band):
        return self._activationState.get(band, None)

    def setActivationStateOfBand(self, band, active):
        self._sendRequest("setActivationState", band=band, state=active)
        self._activationState[band] = active

    def getStreamQualityOfBand(self, band):
        return self._streamQuality.get(band, None)

    def getBatteryOfBand(self, band):
        return self._battery.get(band, None)

    def getBands(self):
        return self._bands

    def getSDKVersion(self):
        return self._sendRequest("getVersion")

    def getRequiredGesturePrecisionOfBand(self, band):
        return self._requiredGesturePrecision.get(band, None)
        
    def setRequiredGesturePrecisionOfBand(self, band, precision_name):
        self._requiredGesturePrecision[band] = precision_name
        return self._sendRequest("setRequiredGesturePrecisionName", band=band, precision=precision_name)

    def setRequiredGesturePrecisionGlobal(self, precision_name):
        for band in self._requiredGesturePrecision:
            self._requiredGesturePrecision[band] = precision_name
        return self._sendRequest("setRequiredGesturePrecisionName", precision=precision_name)
        
    def changeBLEAdaper(self, interface):
        return self._sendRequest("changeBLEAdapter", interface=interface)

    def search(self, seconds=10):
        return self._sendRequest("searchSensorsFor", seconds=seconds)

    def stopSearch(self):
        return self._sendRequest("stopSensorSearch")

    def search_and_connect(self, band, duration=4):
        band_found = {"found": False}

        def add_found_band(fband, rssi):
            if fband == band:
                band_found["found"] = True
                try:
                    self.bandFound.disconnect(add_found_band)
                except:
                    pass
                self.connect(band)

        def stop_search():
            try:
                self.bandFound.disconnect(add_found_band)
            except:
                pass
            self.searchStopped.disconnect(stop_search)
            self.search_and_connect_finished.emit(band, band_found["found"])

        def restart_search():
            self.searchStopped.disconnect(restart_search)
            self.searchStopped.connect(stop_search)
            self.search(duration)

        self.bandFound.connect(add_found_band)

        if not self.currently_searching:
            self.searchStopped.connect(stop_search)
            self.search(duration)
        else:
            self.searchStopped.connect(restart_search)

    def connect(self, band):
       return self._sendRequest("connect", band=band)

    def connectStrongest(self):
        return self._sendRequest("connectStrongest")

    def disconnectBand(self, band):
        return self._sendRequest("disconnect", band=band)

    def getIsBound(self):
        return self._bound

    def startAirmouseOfBand(self, band):
        return self._sendRequest("startAirmouse", band=band)
        
    def stopAirmouseOfBand(self, band):
        return self._sendRequest("stopAirmouse", band=band)

    def _sendRequest(self, method_name, *paramter_list, **parameters):
        if self._rpcSocket is None: 
            return None

        mid = uuid4().int % 2**16
        to_send = {"jsonrpc": "2.0",
             "method": method_name,
             "id": mid
             }

        if parameters is not None and len(parameters) > 0:
            to_send["params"] = parameters
        elif paramter_list is not None:
            to_send["params"] = paramter_list
        #else:
            #self._logger.info("Sending RPC request \"%s\"", method_name)
        self._logger.debug("Sending the following request msg: %s",
                          json.dumps(to_send))
        self._rpcSocket.send_string(json.dumps(to_send))

        retry = True
        while (retry):
            socks = dict(self._poller.poll(2000))
            if (self._rpcSocket in socks and
                    socks[self._rpcSocket] == zmq.POLLIN):
                msg = self._rpcSocket.recv_string()
                #self._logger.debug("Received message: %s",format(msg))
                unpckd = json.loads(msg)
                if unpckd["id"] != mid:
                    self._logger.warning("Received answer out of order!")
                    continue
                if "result" in unpckd and unpckd["result"] is not None:
                    self._logger.debug("Received following reply: {}".format(
                        unpckd["result"]
                    ))
                return unpckd["result"] if "result" in unpckd else None
            else:
                return None

    def _handleMessage(self, message):
        #self._logger.debug("Received the following Publication: %s", message)

        self._heartbeatListener.reset()

        j = json.loads(message)
        typ = j["type"]

        if typ == "Heartbeat":
            pass

        elif typ == "MouseEvent":
            p = j["parameters"]
            mt = p["type"]
            if mt == "move":
                band = j["parameters"]["band"]
                self.mouseMovedGlobal.emit(band, p["x"], p["y"], p["palm_direction"])

        elif typ == "Gesture":
            band = j["parameters"]["band"]
            self._logger.info("%s Received Gesture: %s", band, j["parameters"]["name"])
            self.gestureGlobal.emit(band, j["parameters"]["name"])

        elif typ == "Activation":
            band = j["parameters"]["band"]
            self._logger.info("%s Band changed activation state: %s", band, j["parameters"]["active"])
            self._activationState[band] = j["parameters"]["active"]
            self.activationStateChangedGlobal.emit(band, self._activationState[band])

        elif typ == "SearchResult":
            self._logger.info("Available Sensor: %s (%ddBm)",  j["parameters"]["address"], j["parameters"]["rssi"])
            self.bandFound.emit(j["parameters"]["address"], j["parameters"]["rssi"])

        elif typ == "SearchStarted":
            self.currently_searching = True
            self.searchStarted.emit()

        elif typ == "SearchStopped":
            self.currently_searching = False
            self.searchStopped.emit()

        elif typ == "ConnectionCandidate":
            self._logger.info("AutoConnect Candidate: %s (%d%%)", j["parameters"]["address"],  j["parameters"]["confidence"])
            self.connectNearestCandidateUpdatedGlobal.emit(j["parameters"]["address"], j["parameters"]["confidence"])

        elif typ == "SensorUpdate":
            band = j["parameters"]["band"]
            if "battery" in j["parameters"]:
                self._logger.info("%s Sensor battery charge: %d%%", band, j["parameters"]["battery"])
                self._battery[band] = int(j["parameters"]["battery"])
                self.batteryChangedGlobal.emit(band, self._battery[band])
            if "stream_quality" in j["parameters"]:
                self._logger.info("%s Stream Quality Update: %d%%", band, j["parameters"]["stream_quality"])
                self._streamQuality[band] = int(j["parameters"]["stream_quality"])
                self.streamQualityChangedGlobal.emit(band, self._streamQuality[band])
            if "connection" in j["parameters"]:
                pass

        elif typ == "ConnectionState":
            band = j["parameters"]["band"]
            self._connectionState[band] = j["parameters"]["state"]
            self._connectionReason[band] = j["parameters"]["reason"]
            self._logger.info("%s Band changed connection state: %s", band, j["parameters"]["state"])

            if self._connectionState[band] == "CONNECTED":
                    self._initState(band)
            elif self._connectionState[band] != "DISCONNECTED":
                self.connectionStateChangedGlobal.emit(band, self._connectionState[band])
            else:
                self.connectionStateChangedGlobal.emit(band, self._connectionState[band])
                self._resetState(band)


        elif typ == "Button":
            band = j["parameters"]["band"]
            self.buttonStateChangedGlobal.emit(band, j["parameters"]["pressed"])
        
    def _bound_engine(self):
        if not self._bound:
            self._initStates()
            self._bound = True
            self.bound.emit(self._bound)

    def _unbound_engine(self):
        if self._bound:
            self._resetStates()
            self._bound = False
            self.bound.emit(self._bound)
            
    isBound = property(getIsBound)
    