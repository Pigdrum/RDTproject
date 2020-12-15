
import rdt

if __name__ == '__main__':
    # while (1):
    socket = rdt.RDTSocket()

    socket.bind(('127.0.0.1', 2223))
    conn,info = socket.accept()
    while True:
        data = conn.recv(2048)
        print("收到是：" + data.decode())
        if data and data !=b'exit':
            conn.send(data)
        else:
            conn.close()
            break
