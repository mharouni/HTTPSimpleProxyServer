# Don't forget to change this file's name before submission.
import sys
import os
import socket
import enum
import struct
import asyncio
import re
import logging
#logging.basicConfig(level=logging.DEBUG)

class HttpRequestInfo(object):

    def __init__(self, client_info, method: str, requested_host: str,
                 requested_port: int,
                 requested_path: str,
                 headers: list):
        self.method = method
        self.client_address_info = client_info
        self.requested_host = requested_host
        self.requested_port = requested_port
        self.requested_path = requested_path
        # Headers will be represented as a list of tuples
        # for example ("Host", "www.google.com")
        # if you get a header as:
        # "Host: www.google.com:80"
        # convert it to ("Host", "www.google.com") note that the
        # port is removed (because it goes into the request_port variable)
        self.headers = headers

    def to_http_string(self):



        request = self.method + " " + self.requested_path + " " + "HTTP/1.0\r\n"
        hostHeader = ""
        for head in self.headers:
            if self.requested_port != 80 and "Host" in head[0]:
                hostHeader = hostHeader + head[0] + ": " + head[1]+":"+str(self.requested_port) + "\r\n"
            else:
                hostHeader = hostHeader + head[0] + ": " + head[1] + "\r\n"
        endRequest = "\r\n"
        request = request + hostHeader + endRequest
        return request

    def to_byte_array(self, http_string):

        return bytes(http_string, "UTF-8")

    def display(self):
        print(f"Client:", self.client_address_info)
        print(f"Method:", self.method)
        print(f"Path:", self.requested_path)
        print(f"Host:", self.requested_host)
        print(f"Port:", self.requested_port)
        stringified = [": ".join([k, v]) for (k, v) in self.headers]
        print("Headers:\n", "\n".join(stringified))


class HttpErrorResponse(object):


    def __init__(self, code, message):
        self.code = code
        self.message = message

    def to_http_string(self):
        """ Same as above """
        httpVersion = "HTTP/1.0"
        code = str(self.code)
        message = self.message
        return httpVersion + " " + code + " " + message + "\r\n\r\n"
        pass

    def to_byte_array(self, http_string):

        return bytes(http_string, "UTF-8")

    def display(self):
        print(self.to_http_string())



class HttpCache():
    cacheMem = dict()
    pastCacheFlag = -1
    gettingTocache = dict()
    @classmethod
    def add(cls, host: str, path: str, val: bytes):
        keyMaker = [host, path]
        key = tuple(keyMaker)
        cls.cacheMem[key] = val
        cls.pastCacheFlag = 0
        cls.gettingTocache.update({key: False})
    @classmethod
    def sendFromCache(cls, host: str, path: str):
        keyMaker = [host, path]
        key = tuple(keyMaker)
        if key in cls.cacheMem:
            return cls.cacheMem.get(key, b'Cache Error')

    @classmethod
    def checkInCache(cls, host: str, path: str):
        keyMaker = [host, path]
        key = tuple(keyMaker)
        if key in cls.cacheMem:
            cls.pastCacheFlag = 0
        else:
            if cls.gettingTocache.get(key) == True:
                return True
            else:
                cls.gettingTocache[key] = True
                cls.pastCacheFlag = -1
    @classmethod
    async def pollCache(cls, host: str, path: str):
        keyMaker = [host, path]
        key = tuple(keyMaker)
        while 1:
            flag = cls.gettingTocache.get(key)
            if not flag:
                return
            await asyncio.sleep(0.001)


class HttpRequestState(enum.Enum):

    INVALID_INPUT = 0
    NOT_SUPPORTED = 1
    GOOD = 2
    PLACEHOLDER = -1


def entry_point(proxy_port_number):

    if len(sys.argv) > 2:
        ip_adress = sys.argv[2]
    else:
        ip_adress = ''
    proxyAddress = (ip_adress, int(proxy_port_number))
    print("Starting HTTP proxy on port:", proxy_port_number)
    proxySocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxySocket.bind(proxyAddress)
    proxySocket.listen(40)
    proxySocket.setblocking(0)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(runServer(proxySocket))




async def runServer(proxySocket):
    loop = asyncio.get_running_loop()
    counter = 0
    while True:
        clientSocket, clientAddress = await loop.sock_accept(proxySocket)
        data = await getClientRequest(clientSocket)
        asyncio.create_task(handleAll(clientSocket, clientAddress, data))
        counter = counter + 1



async def getClientRequest(clientSocket):
    loop = asyncio.get_running_loop()
    data = bytes("", "utf8")
    while 1:
        dataChunk = await loop.sock_recv(clientSocket, 4)
        data = data + dataChunk
        if data[len(data) - 4:] == b'\r\n\r\n':
            break
    return data



async def handleAll(clientSocket: socket, clientAddress, data):
    loop = asyncio.get_running_loop()
    processedRequest, proceed, gettingToCache = await loop.run_in_executor(None, handleCPU, clientAddress, data)
    if not proceed:
        await loop.sock_sendall(clientSocket, processedRequest)
    else:
        goodHttpRequest = processedRequest
        if gettingToCache == True:
            await HttpCache.pollCache(goodHttpRequest.requested_host, goodHttpRequest.requested_path)
        if HttpCache.pastCacheFlag == 0:
            fullResponse = await loop.run_in_executor(None, HttpCache.sendFromCache,goodHttpRequest.requested_host, goodHttpRequest.requested_path)
        else:
            fullResponse = await handleCasheMiss(goodHttpRequest)
        await loop.sock_sendall(clientSocket, fullResponse)
    clientSocket.close()



async def handleCasheMiss(goodHttpRequest: HttpRequestInfo):
    loop = asyncio.get_running_loop()
    fullResponse = await handleServerCom(goodHttpRequest)
    await loop.run_in_executor(None, HttpCache.add, goodHttpRequest.requested_host, goodHttpRequest.requested_path, fullResponse)
    return fullResponse



def handleCPU(clientAddress, data):
    processedRequest, proceed = http_request_pipeline(clientAddress, data)
    if proceed:
        goodHttpRequest = processedRequest
        gettingToCache = HttpCache.checkInCache(goodHttpRequest.requested_host, goodHttpRequest.requested_path)
    else:
        goodHttpRequest = processedRequest
        gettingToCache = None
    return goodHttpRequest, proceed, gettingToCache



async def handleServerCom(goodHttpRequest: HttpRequestInfo):
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, goodHttpRequest.to_http_string)
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket.setblocking(0)
    try:
        await loop.sock_connect(serverSocket, (goodHttpRequest.requested_host, goodHttpRequest.requested_port))
    except:
        print("Wrong Port")
        return b''
    data = await loop.run_in_executor(None, goodHttpRequest.to_http_string)
    byteData = await loop.run_in_executor(None, goodHttpRequest.to_byte_array, data)
    await loop.sock_sendall(serverSocket, byteData)
    fullResponse = bytes("", "utf8")
    while 1:
        dataChunck = await loop.sock_recv(serverSocket, 264)
        if len(dataChunck) == 0:
            break
        fullResponse = fullResponse + dataChunck
    serverSocket.close()
    return fullResponse


def http_request_pipeline(source_addr, http_raw_data):

    # Parse HTTP request
    requestState = check_http_request_validity(http_raw_data)
    if requestState.name == "GOOD":
        parsed = parse_http_request(source_addr, http_raw_data)
        sanitize_http_request(parsed)
        return parsed, True
    elif requestState.name == "NOT_SUPPORTED":
        errorResponse = HttpErrorResponse(501, "Unsupported Method")
        return errorResponse.to_byte_array(errorResponse.to_http_string()), False
    else:
        errorResponse = HttpErrorResponse(400, "Bad Request")
        return errorResponse.to_byte_array(errorResponse.to_http_string()), False
    # Validate, sanitize, return Http object.


def parse_http_request(source_addr, http_raw_data) -> HttpRequestInfo:

    exCounter = 0
    headers = []
    hostIndex = -1
    port = 80
    method, counter = getMethod(http_raw_data, exCounter)
    exCounter = counter + 1
    path, counter = getPath(http_raw_data, exCounter)
    exCounter = counter + 1
    version, counter = getVersion(http_raw_data, exCounter)
    exCounter = counter + 2
    while 1:
        header, counter = getHeaders(http_raw_data, exCounter)
        if header is not None:
            headers.append(header)
            exCounter = counter + 2
        else:
            break
    for i in range(0, len(headers)):
        head = headers.pop(0)
        spHead = head.split(":")
        if ("Host" in spHead[0]):
            hostIndex = i
            if ( len(spHead) > 2):
                port = int(spHead.pop())
        if (spHead[1][0] == " "):
            spHead[1] = spHead[1][1:]
        headers.append(spHead)
    if hostIndex < 0: #absolute path
        host = ""
    else:
        host = headers[hostIndex][1]
    host, path, portFromURL = sanitizePath(path, host)
    if port != 80:
        ret = HttpRequestInfo(source_addr, method, host, port, path, headers)
    else:
        ret = HttpRequestInfo(source_addr, method, host, portFromURL, path, headers)
    return ret

def getHeaders(rawHttp, counter):
    try:
        headerLen = getStringLenght(rawHttp, counter, ord("\r"))
        if (counter + 5 >= len(rawHttp)):
            return None, counter
        else:
            if isinstance(rawHttp, bytes):
                header = struct.unpack(str(headerLen) + 's', rawHttp[counter: counter+headerLen])
                header = str(header[0], 'utf-8')
            else:
                header = rawHttp[counter: counter+headerLen]
            counter = counter + headerLen
            return header, counter
    except:
        raise Exception("Header Error")

def getVersion(rawData, counter):
    try:
        versionLen = getStringLenght(rawData, counter, ord('\r'))
        if isinstance(rawData, bytes):
            version = struct.unpack(str(versionLen) + 's', rawData[counter: counter + versionLen])
            version = str(version[0], 'utf-8')
        else:
            version = rawData[counter: counter + versionLen]
        counter = counter + versionLen
        return version, counter
    except:
        raise Exception("Version Error")

def getPath(rawData, counter):
    try:
        hostLen = getStringLenght(rawData, counter)
        if isinstance(rawData, bytes):
            host = struct.unpack(str(hostLen) + 's', rawData[counter: counter + hostLen])
            host = str(host[0], 'utf-8')
        else:
            host = rawData[counter: counter + hostLen]
        counter = counter + hostLen
        return host, counter
    except:
        raise Exception("Path Error")

def getMethod(rawData, counter):
    try:
        methodLen = getStringLenght(rawData, counter)
        counter = counter + methodLen
        if isinstance(rawData, bytes):
            method = struct.unpack(str(methodLen) + 's', rawData[:counter])
            method = str(method[0], 'utf-8')
        else:
            method = rawData[:counter]
        return method, counter
    except:
        print("method")
        raise Exception("Method Error")


def check_http_request_validity(http_raw_data) -> HttpRequestState:

    try:
        exCounter = 0
        headers = []
        hostIndex = -1
        port = 80
        method, counter = getMethod(http_raw_data, exCounter)
        exCounter = counter + 1
        path, counter = getPath(http_raw_data, exCounter)
        exCounter = counter + 1
        version, counter = getVersion(http_raw_data, exCounter)
        correctVersion = re.search("HTTP/\d[.]\d", version)
        if not correctVersion:
            raise Exception
        exCounter = counter + 2
        while 1:
            header, counter = getHeaders(http_raw_data, exCounter)
            if header is not None:
                headers.append(header)
                exCounter = counter + 2
            else:
                break
        for i in range(0, len(headers)):
            head = headers.pop(0)
            spHead = head.split(":")
            if ("Host" in spHead[0]):
                hostIndex = i
                if ( len(spHead) > 2):
                    port = int(spHead.pop())
            if (spHead[1][0] == " "):
                spHead[1] = spHead[1][1:]
            headers.append(spHead)
        if hostIndex < 0: #absolute path
            host = ""
        else:
            host = headers[hostIndex][1]
        if host == "" and ("http://" not in path):
            raise Exception

    except:
        return HttpRequestState.INVALID_INPUT

    if method == "POST" or method == "HEAD" or method == "PUT" or method == "TRACE" or method == "DELETE" or method == "PATCH" or method == "CONNECT" or method == "OPTIONS":
        return HttpRequestState.NOT_SUPPORTED
    elif "GET" not in method:
        return HttpRequestState.INVALID_INPUT

    # return HttpRequestState.GOOD (for example)
    return HttpRequestState.GOOD


def sanitize_http_request(httpRequest: HttpRequestInfo) -> HttpRequestInfo:

    flag = False
    host, path, port = sanitizePath(httpRequest.requested_path, httpRequest.requested_host)
    headers = httpRequest.headers
    length = len(headers)
    for i in range(0, length):
        header = headers[i]
        head = header[0]
        if "Host" in head or "host" in head:
            flag = True
    if flag == False:
        hostHeader = ["Host", host]
        headers.insert(0, hostHeader)



def sanitizePath(absolutePath, httpHost):
    port = 80
    if httpHost is "":
        startHostIndex = absolutePath.index(":") + 3
        lastHostIndex = absolutePath.index("/", startHostIndex)
        host = absolutePath[startHostIndex:lastHostIndex]
        if (len(absolutePath) - 1) == lastHostIndex:
            relativePath = "/"
        else:
            relativePath = absolutePath[lastHostIndex:]
    elif absolutePath[0] == "/":

        relativePath = absolutePath
        host = httpHost
    else:
        host = httpHost
        startHostIndex = absolutePath.index(":") + 3
        lastHostIndex = absolutePath.index("/", startHostIndex)
        if (len(absolutePath) - 1) == lastHostIndex:
            relativePath = "/"
        else:
            relativePath = absolutePath[lastHostIndex:]
        portExists = relativePath.find(":")
        if portExists > -1:
            port = int(relativePath[portExists + 1:])
            print(port)
            print(relativePath)
            relativePath = relativePath[:portExists]
    return host, relativePath, port


def getStringLenght(rawHttp, start, delim = 32):
        counter = 0
        if isinstance(rawHttp,bytes):
            for i in range(start, len(rawHttp)):
                if rawHttp[i] != delim:
                    counter = counter + 1
                else:
                    break
        else:
            delim = chr(delim)
            for i in range(start, len(rawHttp)):
                if rawHttp[i] != delim:
                    counter = counter + 1
                else:
                    break
        if counter == len(rawHttp) -1:
            raise Exception("counter Error")
        return counter

#######################################
# Leave the code below as is.
#######################################


def get_arg(param_index, default=None):

    try:
        return sys.argv[param_index]
    except IndexError as e:
        if default:
            return default
        else:
            print(e)
            print(
                f"[FATAL] The comand-line argument #[{param_index}] is missing")
            exit(-1)    # Program execution failed.




def main():

    print("\n\n")
    print("*" * 50)
    print(f"[LOG] Printing command line arguments [{', '.join(sys.argv)}]")
    print("*" * 50)

    # This argument is optional, defaults to 18888
    proxy_port_number = get_arg(1, 18888)
    entry_point(proxy_port_number)


if __name__ == "__main__":
    main()