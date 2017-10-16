# Copyright Kinemic GmbH
#
# Minimal example to receive gesture events from Gesture Publisher
# You will need python-zmq

import json
import zmq
import argparse

def setup_subscriber(publisher_address):
    """
    Setup the subscriber socket and return it.
    :param publisher_address: zmq conform uri of publisher
    :return: subscriber socket
    """
    print("Subscribing to server on {}".format(publisher_address))
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(publisher_address)
    filter = ""
    # the following two lines are for Python2 compatability
    if isinstance(filter, bytes):
        filter = filter.decode("ascii")
    socket.setsockopt_string(zmq.SUBSCRIBE, filter)
    return socket


if __name__ == "__main__":
    PARSER = argparse.ArgumentParser("Minimal example for Gesture Subscriber")
    PARSER.add_argument("--publisher", help="zmq conform uri of publisher ",
                        default="tcp://192.168.100.100:9999")
    ARGS = PARSER.parse_args()
    SOCKET = setup_subscriber(ARGS.publisher)

    print("Start receiving messages, exit by pressing CTRL+C")
    try:
        while True:
            message = SOCKET.recv_string()
            event = json.loads(message)
            if event["type"] == "Gesture":
                # print out name of gesture (e.g. "Swipe L")
                print("Received gesture: {}".format(event["parameters"]["name"]))
    except KeyboardInterrupt:
        print("received CTRL+C, exit loop")
