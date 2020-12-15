import socket
import struct

from USocket import UnreliableSocket
import threading
import time
from queue import PriorityQueue


# 还剩close，checksum
class RDTSocket(UnreliableSocket):
    """
    The functions with which you are to build your RDT.
    -   recvfrom(bufsize)->bytes, addr
    -   sendto(bytes, address)
    -   bind(address)

    You can set the mode of the socket.
    -   settimeout(timeout)
    -   setblocking(flag)
    By default, a socket is created in the blocking mode.
    https://docs.python.org/3/library/socket.html#socket-timeouts

    """

    def __init__(self, rate=None, debug=True):
        super().__init__(rate=rate)
        self._rate = rate
        self._send_to = self.sendto
        self._recv_from = self._recvData
        self.debug = debug
        #############################################################################
        # TODO: ADD YOUR NECESSARY ATTRIBUTES HERE
        #############################################################################
        # 都是对方的地址
        self.sourceAddr = 0
        self.mss = 1024

        self.lastByteRead = 0
        self.recv_base = 0
        self.recvBuf = {}

        self.estimatedRTT = 0
        self.devRTT = 0

        self.window_size = 100
        self.send_base = 0
        self.send_message = {}
        self.send_queue = PriorityQueue()
        # 序列号长度
        self.SEQLEN = 4294967295
        # 记录本次发送完成data的seq，方便接收ack时使用
        self.nextSeqNum = 0

        self._beginSend = False

        self._isEnd = False
        self.timer = None
        #############################################################################
        #                             END OF YOUR CODE                              #
        #############################################################################

    def _beginTimer(self):
        self.timer = threading.Timer(3, self.__timeoutEvent__)
        self.timer.start()

    def __timeoutEvent__(self):
        seg = self.send_queue.queue[self.send_base]
        self._send_to(seg[0]+seg[1], self.sourceAddr)
        self._beginTimer()

    def __recvACKEvent__(self):
        while (not self._isEnd):
            self.wait_ack()

    def __begin_loop__(self):
        t3 = threading.Thread(target=self.__recvACKEvent__)
        t3.start()

    def accept(self):  # ->(RDTSocket, (str, int)):
        """
        Accept a connection. The socket must be bound to an address and listening for
        connections. The return value is a pair (conn, address) where conn is a new
        socket object usable to send and receive data on the connection, and address
        is the address bound to the socket on the other end of the connection.

        This function should be blocking.
        """
        conn, addr = RDTSocket(self._rate), None
        while (1):
            # 2.接受syn报文
            recv_header, data, addr = self._recv_from(1024)
            print("syn接受成功")
            if (recv_header.checkChecksum() and recv_header.syn == 1):
                conn.recv_base = recv_header.seq + 1
                conn.lastByteRead = conn.recv_base
                ################### 使用新的conn发送syn_ack报文############

                conn._sendSYNACK(addr, recv_header.seq)
                break
        # 4.接受ack报文
        while (1):
            # 接受ack报文
            try:
                recv_header, data, addr = conn._recv_from(1024)
            except TimeoutError as e:
                return self.accept()
            if (recv_header.checkChecksum() and recv_header.ack == 1 and recv_header.seqack == self.send_base + 1):
                conn.recv_base = recv_header.seq + 1
                conn.lastByteRead = conn.recv_base
                break
        print("syn接受成功-----")
        conn.sourceAddr = addr
        conn.send_base += 1
        conn.__begin_loop__()
        print("success accept")
        print(conn)
        return conn, addr

    def connect(self, address: (str, int)):
        """
        Connect to a remote socket at address.
        Corresponds to the process of establishing a connection on the client side.
        """
        #### 1.发送syn报文
        self._sendSYN(address)
        print("syn发送成功-----" + str(address))

        #### 3.等待syn_ack报文
        while (1):
            recv_header, data, addr = self._recv_from(1024)
            if (not recv_header.checkChecksum()):
                continue
            if (recv_header.syn == 1 and recv_header.ack == 1 and recv_header.seqack == self.send_base + 1):
                self.recv_base = recv_header.seq + 1
                self.lastByteRead = self.recv_base
                self.send_base += 1
                ### 3.发送ack，建立连接
                self._sendThree(recv_header.seq)
                break
        print("syn ack 接受成功-----")
        self.__begin_loop__()

    def recv(self, bufsize: int) -> bytes:
        """
        Receive data from the socket.
        The return value is a bytes object representing the data received.
        The maximum amount of data to be received at once is specified by bufsize.

        Note that ONLY data send by the peer should be accepted.
        In other words, if someone else sends data to you from another address,
        it MUST NOT affect the data returned by this function.
        """
        print("开始接收")
        assert self._recv_from, "Connection not established yet. Use recvfrom instead."
        #############################################################################
        # TODO: YOUR CODE HERE                                                      #
        #############################################################################
        returnData = b''
        while (1):
            #先从缓存中读取数据
            i = self.lastByteRead
            while (self.recvBuf.get(self.lastByteRead)):
                if (len(returnData) + len(self.recvBuf) > bufsize):
                    return returnData
                returnData += self.recvBuf[i]
                self.recvBuf.pop(self.lastByteRead)
                i = i + len(returnData)
            self.lastByteRead = i
            if returnData != b'':
                return returnData
            #如果缓存中没有数据，则接受数据
            if(self.send_base!=self.nextSeqNum):
                self.settimeout(0.5)
            else:
                self.settimeout(None)
            try:
                recv_header, payload, addr = self._recv_from(bufsize)
                print("接受到了")
                if (addr != self.sourceAddr):
                    continue
                else:
                    if (not recv_header.checkChecksum()):
                        continue
                    if(recv_header.ack==1):
                        self.recvACK(recv_header)
                    else:
                        self.recvMessage(recv_header, payload)
            except socket.timeout:
                pass

            #############################################################################
            #                             END OF YOUR CODE                              #
            #############################################################################
    def recvMessage(self,recv_header,payload):
        print("接收到的报文头")
        print(recv_header)
        print(self)
        # 序号小于rev_base
        if (recv_header.seq < self.recv_base):
            self._sendACK()
        elif (recv_header.seq < self.recv_base + self.window_size and recv_header.seq >= self.recv_base):
            # 如果缓存里没有，存进去
            if not self.recvBuf.get(recv_header.seq):
                self.recvBuf[recv_header.seq] = payload
            if (recv_header.seq != self.recv_base):
                self._sendACK()
            # if seq==recv_base
            else:
                i = self.recv_base
                returnData = b''
                while (self.recvBuf.get(i)):
                    returnData += self.recvBuf[i]
                    i = i + len(returnData)
                self.recv_base = i
                self._sendACK()
        print(self)

    def send(self, bytes: bytes):
        """
        Send data to the socket.
        The socket must be connected to a remote socket, i.e. self._send_to must not be none.
        """
        self._partition_data(bytes)
        for key, value in self.send_message.items():
            if (self.timer != None and not self.timer.is_alive()):
                self._beginTimer()
            self._send_to(value[0] + value[1], self.sourceAddr)
            self.nextSeqNum += len(value[1])
            self.send_queue.put((key, value))
        self.wait_ack()

    def _partition_data(self, payload: bytes):
        print("开始发送:")
        seg_seq_num = self.send_base
        total_len = len(payload)
        remain_len = total_len
        start_index = 0
        MSS = self.mss
        while remain_len > MSS:
            partitioned_payload = payload[start_index: start_index + MSS]
            print("partition data: " + partitioned_payload.decode() + ", seq_num: " + str(seg_seq_num))
            header = Header(self)
            header.seq = seg_seq_num
            header.len = MSS
            partitioned_data_seg = (header.pack(), partitioned_payload)
            seg_seq_num += MSS
            start_index += MSS
            remain_len -= MSS
            # add the segment into the sender queue
            self.send_message[start_index] = (partitioned_data_seg)
        # add the last segment
        last_data = payload[start_index: total_len]
        header = Header(self)
        header.seq = seg_seq_num
        header.len = total_len - start_index
        last_data_seg = (header.pack(), last_data)
        self.send_message[start_index] = last_data_seg

    def wait_ack(self):
        print("等待接收ack:")
        while True:
            recv_header, data, addr = self._recv_from(2048)
            self.settimeout(3)
            try:
                if (addr == self.sourceAddr):
                    print("收到的ack包")
                    if (not recv_header.checkChecksum()):
                        continue
                    if recv_header.seqack > self.send_base:
                        self.send_base = recv_header.seqack
                        if (self.send_base == self.nextSeqNum):
                            self.sender_queue = {}
                            # 全部接收完成
                            break
            except Exception as e:
                # 超时重传
                self._send_to(self.sender_queue[self.send_base], self.sourceAddr)




    def close(self):
        """
        Finish the connection and release resources. For simplicity, assume that
        after a socket is closed, neither futher sends nor receives are allowed.
        """
        #############################################################################
        # TODO: YOUR CODE HERE                                                      #
        #############################################################################

        #############################################################################
        #                             END OF YOUR CODE                              #
        #############################################################################
        super().close()

    def set_send_to(self, send_to):
        self._send_to = send_to

    def set_recv_from(self, recv_from):
        self._recv_from = recv_from

    def _recvData(self, bufferSize):
        data, addr = self.recvfrom(bufferSize)
        self.sourceAddr = addr
        recv_header = Header(self)
        headerLen = recv_header.headerLen()
        recv_header.unpack(data[:headerLen])
        return recv_header, data[headerLen:], addr

    def _sendSYN(self, address):
        header = Header(self)
        header.syn = 1
        header.seq = self.send_base
        self.nextSeqNum += 1
        self._send_to(header.pack(), address)

    def _sendSYNACK(self, addr, recv_seq):
        header = Header(self)
        header.syn = 1
        header.ack = 1
        header.seqack = recv_seq + 1
        header.seq = self.send_base
        self.nextSeqNum += 1
        self._send_to(header.pack(), addr)

    def _sendThree(self, recv_seq):
        header = Header(self)
        self.nextSeqNum += 1
        header.syn = 0
        header.seqack = recv_seq + 1
        header.seq = self.send_base
        header.ack = 1
        self._send_to(header.pack(), self.sourceAddr)
        #假设对方已经收到了
        self.send_base+=1

    def _sendACK(self):
        header = Header(self)
        header.seqack = self.recv_base
        header.ack = 1
        self._send_to(header.pack(), self.sourceAddr)

    def __str__(self):
        to_string = "("
        items = self.__dict__
        n = 0
        for k in items:
            if k.startswith("_"):
                continue
            if (str(k) == 'sendto'):
                continue
            if(str(k) == 'send_queue'):
                to_string = to_string + str(k) + "=" + str(self.send_queue.queue) + ","
            else:
                to_string = to_string + str(k) + "=" + str(items[k]) + ","
            n += 1
        if n == 0:
            return ""
        return to_string.rstrip(",") + ")"


"""
You can define additional functions and classes to do thing such as packing/unpacking packets, or threading.

"""


class Header:
    def __init__(self, rdtSocket: RDTSocket):
        self.syn = 0
        self.fin = 0
        self.ack = 0
        self.seq = 0
        self.seqack = 0
        self.len = 0
        self.checksum = 0
        self.rwn = 0
        self.cwn = 0
        self.mss = rdtSocket.mss
        self.window_size = rdtSocket.window_size

    def pack(self):
        flag = self.syn << 3
        flag += self.fin << 2
        flag += self.ack << 1
        self.calculateChecksum()
        return struct.pack('!BIIIH', flag, self.seq, self.seqack, self.len, self.checksum)

    def unpack(self, b):
        unpacked = struct.unpack('!BIIIH', b)
        flag = unpacked[0]
        self.syn = (flag >> 3) & 0b0001
        self.fin = (flag >> 2) & 0b0001
        self.ack = (flag >> 1) & 0b0001
        self.seq = int(unpacked[1])
        self.seqack = int(unpacked[2])
        self.len = int(unpacked[3])
        self.checksum = int(unpacked[4])

    def headerLen(self):
        return len(self.pack())

    def calculateChecksum(self):
        pass

    def checkChecksum(self):
        return True

    def __str__(self):
        to_string = "("
        items = self.__dict__
        n = 0
        for k in items:
            if k.startswith("_"):
                continue
            if (str(k) == 'sendto'):
                continue
            to_string = to_string + str(k) + "=" + str(items[k]) + ","
            n += 1
        if n == 0:
            return ""
        return to_string.rstrip(",") + ")"
