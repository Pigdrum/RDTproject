import threading
import time
import USocket
from struct import pack, unpack
from queue import PriorityQueue

def fun_timer():
    # while(1):
    print(11111111111)

class tester:
    def __init__(self):
        self.counter = 0

    def threader(self):
        for i in range(100):
            self.counter+=1
            print(self.counter)

    def other(self):
        print("开始运行other")

    def getCounter(self):
        print("我来说counter="+str(self.counter))

    def runThreader(self):
        t1 = threading.Thread(target=self.threader)
        t1.start()

    def __eq__(self, other):
        return self.counter == other.counter

if __name__ == "__main__":
    while True:
        t = threading.Timer(1,fun_timer)
        t.start()

        t = threading.Timer(1,fun_timer)
        t.start()
        t.cancel()
    print(tester() == tester())
    syn = 1
    fin = 0
    ack = 1
    flag = syn << 3
    flag += fin << 2
    flag += ack << 1

    print(pack("!bI", flag, 23))
    c = unpack("!bI", pack("!bI", flag, 23))
    print(c)
    socket = USocket.socket()

    start = time.time()
    print("ss:")
    time.sleep(1)
    print(time.time() - start)

    # queu = PriorityQueue()
    # try:
    #     queu.get_nowait()
    # except Exception as e:
    #     pass
    # queu.put((1,'sadf'))
    # queu.put((2,'sdaf'))
    # print(queu.queue[0])
    # print(queu.queue)

    # test = tester()
    #
    # test.runThreader()
    # test.getCounter()
    # test.other()
    # timer=None
    # h = {}
    # h[1] = 'awef'
    # h[2] = 'aaaa'
    # h[3] = 'dvvd'
    # for e,h in h.items():
    #     print(e)
    # print([1,2][0:1])
    timer = threading.Timer(5, fun_timer)
    timer.start()
    #
    # timer.sleep(15) # 15秒后停止定时器
    timer.cancel()


    # t1 = threading.Thread(target=fun_timer)
    # t2 = threading.Thread(target=fun_timer)
    # t1.start()
    # t2.start()
    #
    print('主线程结束')