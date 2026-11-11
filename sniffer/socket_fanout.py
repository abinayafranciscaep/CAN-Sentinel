#!/usr/bin/env python3
import os, selectors, signal, socket, stat, time

SOURCE = "/tmp/can_sentinel.sock"
OUTPUT = "/tmp/can_sentinel_fanout.sock"
MAX_PENDING = 1024 * 1024
running = True

def stop(*_):
    global running
    running = False

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

if os.path.exists(OUTPUT):
    if not stat.S_ISSOCK(os.stat(OUTPUT).st_mode):
        raise RuntimeError("Refusing to remove non-socket: " + OUTPUT)
    os.unlink(OUTPUT)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(OUTPUT)
os.chmod(OUTPUT, 0o660)
server.listen(8)
server.setblocking(False)

upstream = None
while running:
    try:
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        upstream.connect(SOURCE)
        upstream.setblocking(False)
        print("Connected to sniffer", flush=True)
        break
    except OSError as exc:
        upstream.close()
        upstream = None
        print("Waiting for sniffer:", exc, flush=True)
        time.sleep(2)

selector = selectors.DefaultSelector()
selector.register(server, selectors.EVENT_READ, "server")
if upstream:
    selector.register(upstream, selectors.EVENT_READ, "upstream")
clients = {}

def drop(client):
    try:
        selector.unregister(client)
    except Exception:
        pass
    clients.pop(client, None)
    try:
        client.close()
    except OSError:
        pass

try:
    while running and upstream:
        for key, _ in selector.select(timeout=1):
            sock, kind = key.fileobj, key.data
            if kind == "server":
                try:
                    client, _ = server.accept()
                    client.setblocking(False)
                    clients[client] = bytearray()
                    selector.register(client, selectors.EVENT_READ, "client")
                    print("Downstream connected:", len(clients), flush=True)
                except OSError:
                    pass
            elif kind == "upstream":
                try:
                    chunk = upstream.recv(65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    print("Sniffer disconnected", flush=True)
                    running = False
                    break
                for client, pending in list(clients.items()):
                    pending.extend(chunk)
                    if len(pending) > MAX_PENDING:
                        print("Dropping slow client", flush=True)
                        drop(client)
                    else:
                        selector.modify(client, selectors.EVENT_READ | selectors.EVENT_WRITE, "client")
            elif kind == "client":
                if key.events & selectors.EVENT_READ:
                    try:
                        probe = sock.recv(1, socket.MSG_PEEK)
                    except BlockingIOError:
                        probe = None
                    except OSError:
                        probe = b""
                    if probe == b"":
                        drop(sock)
                        continue
                if key.events & selectors.EVENT_WRITE and sock in clients:
                    pending = clients[sock]
                    if pending:
                        try:
                            sent = sock.send(pending)
                            del pending[:sent]
                        except BlockingIOError:
                            pass
                        except OSError:
                            drop(sock)
                            continue
                    if sock in clients and not clients[sock]:
                        selector.modify(sock, selectors.EVENT_READ, "client")
finally:
    for client in list(clients):
        drop(client)
    if upstream:
        upstream.close()
    selector.close()
    server.close()
    try:
        os.unlink(OUTPUT)
    except FileNotFoundError:
        pass
