
import zmq
import logging

from PyQt5.QtCore import QObject, QThread, pyqtSignal

class EngineSubscriber(QObject):
    """
    PyQt wrapper around zmq subscriber to listen for messages from the engine (or really any zmq publisher)
    """
    message = pyqtSignal(str)

    def __init__(self, ctx, address):
        super(EngineSubscriber, self).__init__()

        # ZeroMQ endpoint
        self._context = ctx
        self._logger = logging.getLogger(__name__ + "EngineSubscriber")
        self._address = address
        self._socket = None
        self._poller = None
        self._reset_socket = True
        self.running = True
        
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._loop)
        self._thread.start()

    def stop(self):
        self.running = False
        self._thread.quit()
        self._thread.wait()

    def change_address(self, address):
        self._address = address
        self._reset_socket = True

    def _loop(self):
        while self.running:
            if (self._reset_socket):
                if (self._poller is not None):
                    self._socket.close()
                self._socket = self._context.socket(zmq.SUB)
                self._socket.connect(self._address)
                self._socket.setsockopt_string(zmq.SUBSCRIBE, u"")
                self._poller = zmq.Poller()
                self._poller.register(self._socket, zmq.POLLIN)
                self._reset_socket = False
            socks = dict(self._poller.poll(200))
            if self._socket in socks and socks[self._socket] == zmq.POLLIN:
                message = self._socket.recv_string()
                self.message.emit(message)
