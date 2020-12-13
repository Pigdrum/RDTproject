import struct

from USocket import UnreliableSocket
import threading
import time


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
        self.recv_base = 0
        self.recvBuf = {}
        self.header = Header()
        self.send_base = 0
        self.sender_queue = {}
        # 序列号长度
        self.SEQLEN = 4294967295
        #记录本次发送完成data的seq，方便接收ack时使用
        self.seq_after_send=0
        #############################################################################
        #                             END OF YOUR CODE                              #
        #############################################################################

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
            # 接受syn报文
            recv_header, data, addr = self._recv_from(1024)
            print("syn接受成功")
            if (recv_header.checkChecksum() and recv_header.syn == 1):
                conn.recv_base = recv_header.seq + 1
                ################### 使用新的conn发送syn_ack报文############

                conn._sendSYNACK(addr, recv_header.seq)
                break
        conn.settimeout(10)
        # 接受ack报文
        while (1):
            # 接受ack报文
            try:
                recv_header, data, addr = conn._recv_from(1024)
            except TimeoutError as e:
                return self.accept()
            if (recv_header.checkChecksum() and recv_header.ack == 1 and recv_header.seqack == self.send_base + 1):
                break
        print("syn接受成功-----")
        conn.sourceAddr = addr
        conn.send_base += 1

        self.printState()
        print("success accept")
        return conn, addr

    def connect(self, address: (str, int)):
        """
        Connect to a remote socket at address.
        Corresponds to the process of establishing a connection on the client side.
        """
        #### 1.发送syn报文
        self._sendSYN(address)
        print("syn发送成功-----" + str(address))
        print("发送的seq是:" + str(self.header.seq))
        #### 2.等待syn_ack报文
        while (1):
            recv_header, data, addr = self._recv_from(1024)
            if (not recv_header.checkChecksum()):
                continue
            if (recv_header.syn == 1 and recv_header.ack == 1 and recv_header.seqack == self.send_base + 1):
                self.recv_base = recv_header.seq + 1
                ### 3.发送ack，建立连接
                self._sendThree(recv_header.seq)
                break
        print("syn ack 接受成功-----")

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
        self.printState()
        self.settimeout(None)
        assert self._recv_from, "Connection not established yet. Use recvfrom instead."
        #############################################################################
        # TODO: YOUR CODE HERE                                                      #
        #############################################################################
        while (1):
            recv_header, payload, addr = self._recv_from(bufsize)
            if (addr != self.sourceAddr):
                continue
            else:
                print("接收到的报文头")
                recv_header.printState()
                if (not recv_header.checkChecksum()):
                    continue
                # 序号小于rev_base
                if (recv_header.seq < self.recv_base):
                        self._sendACK()
                elif (recv_header.seq < self.recv_base + self.header.window_size and recv_header.seq >= self.recv_base):
                    self.header.ack = 1
                    # 如果缓存里没有，存进去
                    if not self.recvBuf.get(recv_header.seq):
                        self.recvBuf[recv_header.seq] = payload
                    #超前接收了
                    if (recv_header.seq != self.recv_base):
                        self._sendACK()
                    #if seq==recv_base
                    else:
                        i = self.recv_base
                        returnData = b''
                        while (self.recvBuf.get(i)):
                            returnData += self.recvBuf[i]
                            self.recvBuf.pop(i)
                            i = i + len(returnData)
                        self.recv_base = i
                        self._sendACK()
                        return returnData

                    self._sendACK()

            #############################################################################
            #                             END OF YOUR CODE                              #
            #############################################################################

    def send(self, bytes: bytes):
        """
        Send data to the socket. 
        The socket must be connected to a remote socket, i.e. self._send_to must not be none.
        """
        self.seq_after_send = self.send_base+len(bytes)
        self._partition_data(bytes)
        for _, value in self.sender_queue.items():
            self._send_to(value, self.sourceAddr)
            print("send seccuss:")
            print(value)
        self.wait_ack()
        print("收到ack")


    def _partition_data(self, payload: bytes):
        print("开始发送:")
        self.printState()
        seg_seq_num = self.send_base
        total_len = len(payload)
        remain_len = total_len
        start_index = 0
        MSS = self.header.mss
        while remain_len > MSS:
            partitioned_payload = payload[start_index: start_index + MSS]
            print("partition data: " + partitioned_payload.decode() + ", seq_num: " + str(seg_seq_num))
            self.header.seq = seg_seq_num
            self.header.len = MSS
            partitioned_data_seg = self.header.pack() + partitioned_payload
            seg_seq_num += MSS
            start_index += MSS
            remain_len -= MSS
            # add the segment into the sender queue
            self.sender_queue[start_index] = (partitioned_data_seg)
        # add the last segment
        last_data = payload[start_index: total_len]
        self.header.seq = seg_seq_num
        self.header.len = total_len - start_index
        last_data_seg = self.header.pack() + last_data
        self.sender_queue[start_index] = last_data_seg

    def wait_ack(self):
        print("等待接收ack:")
        self.printState()
        while True:
            recv_header, data, addr = self._recv_from(2048)
            self.settimeout(3)
            try:
                if (addr == self.sourceAddr):
                    print("收到的ack包")
                    recv_header.printState()
                    if (not recv_header.checkChecksum()):
                        continue
                    if recv_header.seqack > self.send_base:
                        self.send_base = recv_header.seqack
                        if(self.send_base == self.seq_after_send):
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

    def printState(self):
        print("syn=" + str(self.header.syn))
        print("seq=" + str(self.header.seq))
        print('seqack=' + str(self.header.seqack))
        print('len=' + str(self.header.len))
        print('sendbase=' + str(self.send_base))
        print("recvbase=" + str(self.recv_base))

    def _recvData(self, bufferSize):
        data, addr = self.recvfrom(bufferSize)
        self.sourceAddr = addr
        recv_header = Header()
        headerLen = recv_header.headerLen()
        recv_header.unpack(data[:headerLen])
        return recv_header, data[headerLen:], addr

    def _sendSYN(self, address):
        self.header.syn = 1
        self.header.seq = self.send_base
        self._send_to(self.header.pack(), address)

    def _sendSYNACK(self, addr, recv_seq):
        self.header.syn = 1
        self.header.ack = 1
        self.header.seqack = recv_seq + 1
        self.header.seq = self.send_base
        self._send_to(self.header.pack(), addr)

    def _sendThree(self,recv_seq):
        self.send_base += 1
        self.header.syn = 0
        self.header.seqack = recv_seq + 1
        self.header.seq = self.send_base
        self.header.ack = 1
        self._send_to(self.header.pack(), self.sourceAddr)

    def _sendACK(self):
        self.header.seqack = self.recv_base
        self.header.ack = 1
        self._send_to(self.header.pack(), self.sourceAddr)


"""
You can define additional functions and classes to do thing such as packing/unpacking packets, or threading.

"""


class Header():
    def __init__(self):
        self.syn = 0
        self.fin = 0
        self.ack = 0
        self.seq = 0
        self.seqack = 0
        self.len = 0
        self.checksum = 0
        self.rwn = 0
        self.cwn = 0
        self.mss = 100
        self.window_size = 100

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

    def printState(self):
        print("seq=" + str(self.seq))
        print('seqack=' + str(self.seqack))
