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
        self.window_size = 10000000000000

        #-------------超时间隔------------
        self.timer = None
        self.estimatedRTT = 0
        self.devRTT = 0
        self.sampleRTT = 0
        self.timeoutInterval = 1
        self.alph = 0.125
        #--------------------------------
        self.send_base = 0
        self.send_message = {}
        self.send_queue = PriorityQueue()
        # 序列号长度
        self.SEQLEN = 4294967295
        # 记录本次发送完成data的seq，方便接收ack时使用
        self.nextSeqNum = 0

        # 全局结束标志
        self._isEnd = False

        # 完成结束的发送fin状态
        self._isSendFIN = False
        # 为了拥塞控制的参数
        self.duplicateACK = 0
        self.cwnd = self.mss
        self.state = 0  # 0代表慢启动，1代表快速恢复，2代表拥塞避免
        self.ssthresh = 64 * 1024
        #############################################################################
        #                             END OF YOUR CODE                              #
        #############################################################################

    def _beginTimer(self):
        self.timer = threading.Timer(self.timeoutInterval, self.__timeoutEvent__)
        self.timer.start()

    def __timeoutEvent__(self):
        # ---------------拥塞控制--------超时事件
        self.timeoutInterval*=2
        self.ssthresh = self.cwnd / 2
        self.cwnd = self.mss
        self.duplicateACK = 0
        self.state = 0
        # ------------------------------------------------#
        seg = self.send_queue.queue[0]
        print("超时重发")
        self._send_to(seg.pack(), self.sourceAddr)
        self._beginTimer()

    def __begin_loop__(self):
        t3 = threading.Thread(target=self._beginReceve)
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
                conn.sourceAddr = addr
                conn.recv_base = recv_header.seq + 1
                conn.lastByteRead = conn.recv_base
                # 3.使用新的conn发送syn_ack报文############

                conn._sendSYNACK(addr, recv_header.seq)
                break
        # 5.接受ack报文
        while (1):
            # 接受ack报文
            try:
                recv_header, data, addr = conn._recv_from(1024)
            except TimeoutError as e:
                return self.accept()
            if (recv_header.checkChecksum() and recv_header.ack == 1 and recv_header.seqack == self.send_base + 1):
                conn.recv_base = recv_header.seq + 1
                conn.lastByteRead = conn.recv_base
                try:
                    self.send_queue.get_nowait()
                except Exception as e:
                    pass
                conn.timer.cancel()
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
        self.sourceAddr = address
        self._sendSYN(address)
        print("syn发送成功-----" + str(address))

        #### 4.等待syn_ack报文
        while (1):
            recv_header, data, addr = self._recv_from(1024)
            if (not recv_header.checkChecksum()):
                continue
            if (recv_header.syn == 1 and recv_header.ack == 1 and recv_header.seqack == self.send_base + 1):
                self.sourceAddr = addr
                self.recv_base = recv_header.seq + 1
                self.lastByteRead = self.recv_base
                self.send_base += 1
                ### 3.发送ack，建立连接
                try:
                    self.send_queue.get_nowait()
                except Exception as e:
                    pass
                self.timer.cancel()
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
        # 进行动作：从接收队列里取消息，如果无消息，则继续等待消息队列填充消息
        print("开始接收")
        returnData = b''
        while (not self._isEnd):
            # 从缓存中读取数据
            i = self.lastByteRead
            while (self.recvBuf.get(self.lastByteRead)):
                if (len(returnData) + len(self.recvBuf) > bufsize):
                    # 结束了就不能收数据了
                    return returnData
                returnData += self.recvBuf[i]
                self.recvBuf.pop(self.lastByteRead)
                i = i + len(returnData)
            self.lastByteRead = i
            if returnData != b'':
                return returnData
        return b'exit'

    def send(self, bytes: bytes):
        """
        Send data to the socket.
        The socket must be connected to a remote socket, i.e. self._send_to must not be none.
        """
        # 进行动作：把消息放入发送队列，发送包
        self._partition_data(bytes)

        for key, value in self.send_message.items():
            # 阻塞等待
            while (self.nextSeqNum - self.send_base > self.cwnd):
                pass
            if (self.timer != None and not self.timer.is_alive()):
                self._beginTimer()
            self.send_queue.put(value)
            self._send_to(value.pack(), self.sourceAddr)
            self.nextSeqNum += value.len
        self.send_message = {}

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
            header.payload = partitioned_payload
            seg_seq_num += MSS
            start_index += MSS
            remain_len -= MSS
            # add the segment into the sender queue
            self.send_message[start_index] = header
        # add the last segment
        last_data = payload[start_index: total_len]
        if (len(last_data) != 0):
            header = Header(self)
            header.seq = seg_seq_num
            header.len = total_len - start_index
            header.payload = last_data
            self.send_message[start_index] = header

    def _beginReceve(self):
        # 执行动作：一直接受，可能是ack消息，可能是fin，可能是message
        while ((not self._isEnd)):
            recv_header, data, addr = self._recv_from(2048)
            print('接收到报文:')
            print(recv_header)
            if (addr == self.sourceAddr):
                if (not recv_header.checkChecksum()):
                    continue
                if (recv_header.ack == 1):
                    self._recvACK(recv_header)
                elif (recv_header.fin == 1):
                    self._recvFIN(recv_header)
                else:
                    self._recvMessage(recv_header, data)

    def _recvACK(self, recv_header):
        # 执行动作：更新send_base，消息队列出队，如果全部接受完了，则暂停时间，否则重新开始时间
        print("收到ack--")
        print(recv_header)
        print(self)

        if recv_header.seqack > self.send_base:
            # ---------------拥塞控制--------收到new ack
            if self.state == 0:
                # ------慢启动------
                self.cwnd += self.mss
                self.duplicateACK = 0
                if (self.cwnd >= self.ssthresh):
                    self.state = 2
            elif self.state == 1:
                # ------快速恢复------
                self.cwnd = self.ssthresh
                self.duplicateACK = 0
                self.state = 2
            elif self.state == 2:
                # ------拥塞避免------
                self.cwnd += self.mss * self.mss / self.cwnd
                self.duplicateACK = 0
            # ------------------------------------------------#
            self.send_base = recv_header.seqack
            while ((not self.send_queue.empty()) and self.send_queue.queue[0].seq < self.send_base):
                try:
                    self.send_queue.get_nowait()
                except Exception as e:
                    pass
            if (self.send_base == self.nextSeqNum):
                # 全部接收完成
                if (self.timer != None):
                    self.timer.cancel()
            else:
                if (self.timer != None and self.timer.is_alive):
                    self.timer.cancel()
                self._beginTimer()
        else:
            # ---------------拥塞控制--------#收到冗余ack
            if self.state == 0:
                self.duplicateACK += 1
                # ------慢启动------
                if self.duplicateACK == 3:
                    self.ssthresh = self.cwnd / 2
                    self.cwnd = self.ssthresh + 3 * self.mss
                    self.state = 1
            elif self.state == 1:
                self.cwnd += self.mss
                # ------快速恢复------
            elif self.state == 2:
                self.duplicateACK += 1
                if self.duplicateACK == 3:
                    self.ssthresh = self.cwnd / 2
                    self.cwnd = self.ssthresh + 3 * self.mss
                    self.state = 1
                # ------拥塞避免------
            # ------------------------------------------------#
            if self.duplicateACK == 3:
                # 快速重传###
                seg = self.send_queue.queue[0]
                print("快速重传")
                self._send_to(seg.pack(), self.sourceAddr)

    def _recvMessage(self, recv_header, payload):
        # 接受消息:如果是以前的消息，sendack，否则放进接收队列，如果是recvbase，更新recvbase，如果是大于recvbase,不更新
        print("接收到的报文头")
        print(recv_header)
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

    def _recvFIN(self, recv_header):
        print("收到fin")
        self.recv_base += recv_header.len
        self._sendACK()
        if (self._isSendFIN):
            self._isEnd = True
            start = time.time()
            while (1):
                try:
                    self.settimeout(10)
                    if (time.time() - start > 20):
                        break
                    header, data, addr = self._recv_from(1024)
                    if (self.sourceAddr == addr and header.checkChecksum() and header.fin == 1):
                        self.timer.cancel()
                        self.recv_base += 1
                        self._sendACK()
                except socket.timeout:
                    pass
        else:
            self._sendFINandReceveACK()
        self._isEnd = True
        super().close()
        print('socket closed')

    def _sendFINandReceveACK(self):
        print('发送fin')
        self._sendFIN()
        start = time.time()
        while (1):
            try:
                self.settimeout(10)
                if (time.time() - start > 20):
                    break
                header, payload, addr = self._recv_from(1024)
                if (addr == self.sourceAddr and header.checkChecksum() and header.ack == 1):
                    print("收到最后的ack")
                    print(header)
                    self.timer.cancel()
                    break
            except socket.timeout:
                pass

    def close(self):
        """
        Finish the connection and release resources. For simplicity, assume that
        after a socket is closed, neither futher sends nor receives are allowed.
        """
        if (self._isEnd):
            return
        self._isSendFIN = True
        self._sendFIN()
        while (not self._isEnd):
            pass

    def set_send_to(self, send_to):
        self._send_to = send_to

    def set_recv_from(self, recv_from):
        self._recv_from = recv_from

    def _recvData(self, bufferSize):
        data, addr = self.recvfrom(bufferSize)
        recv_header = Header(self)
        headerLen = recv_header.headerLen()
        recv_header.unpack(data[:headerLen])
        return recv_header, data[headerLen:], addr

    def _sendSYN(self, address):
        header = Header(self)
        header.syn = 1
        header.seq = self.send_base
        self.nextSeqNum += 1
        self.send_queue.put(header)
        self._send_to(header.pack(), address)
        self._beginTimer()

    def _sendSYNACK(self, addr, recv_seq):
        header = Header(self)
        header.syn = 1
        header.ack = 1
        header.seqack = recv_seq + 1
        header.seq = self.send_base
        self.nextSeqNum += 1
        self.send_queue.put(header)
        self._send_to(header.pack(), addr)
        self._beginTimer()

    def _sendThree(self, recv_seq):
        header = Header(self)
        self.nextSeqNum += 1
        header.syn = 0
        header.seqack = recv_seq + 1
        header.seq = self.send_base
        header.ack = 1
        self._send_to(header.pack(), self.sourceAddr)
        # 假设对方已经收到了
        self.send_base += 1

    def _sendACK(self):
        header = Header(self)
        header.seqack = self.recv_base
        header.ack = 1
        self._send_to(header.pack(), self.sourceAddr)

    def _sendFIN(self):
        header = Header(self)
        header.fin = 1
        header.seq = self.send_base
        header.payload = b'\0'
        header.len = 1
        self.nextSeqNum += 1
        self.send_queue.put(header)
        self._send_to(header.pack(), self.sourceAddr)
        self._beginTimer()

    def __str__(self):
        to_string = "("
        items = self.__dict__
        n = 0
        for k in items:
            if k.startswith("_"):
                continue
            if (str(k) == 'sendto'):
                continue
            if (str(k) == 'send_queue'):
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
        self.payload = b''

    def pack(self):
        flag = self.syn << 3
        flag += self.fin << 2
        flag += self.ack << 1
        self.calculateChecksum()
        return struct.pack('!BIIIH', flag, self.seq, self.seqack, self.len, self.checksum) + self.payload

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

    def __lt__(self, rhs):
        return self.seq < rhs.seq

    def __eq__(self, other):
        return (self.seq == other.seq and self.ack == other.ack and self.fin == other.fin and
                self.syn == other.syn and self.checksum == other.checksum and self.seqack == other.seqack
                and self.payload == other.payload)
