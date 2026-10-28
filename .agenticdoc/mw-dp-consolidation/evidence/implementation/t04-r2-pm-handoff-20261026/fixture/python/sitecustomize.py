import socket
def denied(*args, **kwargs):
    raise AssertionError('PM verification forbids network')
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
