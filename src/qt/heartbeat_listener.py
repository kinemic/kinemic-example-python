import time

from PyQt5.QtCore import QThread, QObject, pyqtSignal, QTimer

class HeartBeatListener(QObject):
    """
    Watchdog which needs to be called reset to indicate connection to the engine was established
    """

    connectionLost = pyqtSignal()
    connectionEstablished = pyqtSignal()

    class Looper(QObject):

        connectionLost = pyqtSignal()
        connectionEstablished = pyqtSignal()

        def __init__(self, timeout):
            self._running = True
            self._listening = True
            self._timeout_s = timeout
            self._timer = None
            self._last_pet = None
            super().__init__()

        def start(self):
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._loop)
            self._last_pet = time.time()
            self._timer.start(0)

        def _loop(self):
            if self._running:
                now = time.time()
                if ((now - self._last_pet) > self._timeout_s and
                        self._listening):
                    self.connectionLost.emit()
                self._timer.start(500.0 * self._timeout_s)

        def stop(self):
            self._running = False
            self._timer.disconnect()

        def reset(self):
            self._last_pet = time.time()
            # if not self.established:
            self.connectionEstablished.emit()

        def pause_listening(self):
            self._listening = False

        def resume_listening(self):
            self._listening = True


    def __init__(self, timeoutSeconds=3):
        super(HeartBeatListener, self).__init__()
        self._thread = QThread()
        self._looper = HeartBeatListener.Looper(timeoutSeconds)
        self._looper.moveToThread(self._thread)
        self._thread.started.connect(self._looper.start)
        self._looper.connectionEstablished.connect(self.connectionEstablished.emit)
        self._looper.connectionLost.connect(self.connectionLost.emit)
        self._thread.start()

    def stop(self):
        self._looper.stop()
        self._thread.quit()
        self._thread.wait()

    def pause_listening(self):
        self._looper.pause_listening()

    def resume_listening(self):
        self._looper.resume_listening()

    def reset(self):
        self._looper.reset()
