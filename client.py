
from click._compat import raw_input

import rdt

if __name__ == '__main__':
    socket = rdt.RDTSocket()
    # Creates an IPv4 socket with UDP to listen from r1
    socket.connect(('127.0.0.1',2223))
    while True:
        inputData = input()
        if (inputData == "exit"):
            break
        else:
            socket.send(inputData.encode())
            data = socket.recv(2048)
            print("回显是："+data.decode())
    socket.close()