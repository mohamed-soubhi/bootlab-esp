#!/usr/bin/env python3
"""
Simple TCP forwarder for Windows host to forward incoming connections to WSL2.
Usage: python tcp_forwarder.py <listen_port> <target_port>
"""
import socket
import sys
import threading

def forward(src, dst):
    """Copy src -> dst until src's EOF, then half-close dst (FIN, not RST).

    Closing both sockets on the first EOF can send a RST that discards data
    still in flight -- it truncated a 1 MB OTA download. Sockets are closed
    only once BOTH directions are done (see pipe()).
    """
    try:
        while True:
            data = src.recv(8192)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    try:
        dst.shutdown(socket.SHUT_WR)
    except Exception:
        pass


def pipe(client, target):
    """Relay both directions; close both sockets after both have finished."""
    back = threading.Thread(target=forward, args=(target, client), daemon=True)
    back.start()
    forward(client, target)
    back.join()
    for s in (client, target):
        try:
            s.close()
        except Exception:
            pass

def main():
    listen_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8443
    target_port = int(sys.argv[2]) if len(sys.argv) > 2 else listen_port
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', listen_port))
    server.listen(10)
    print(f"[TCP_FWD] Listening on 0.0.0.0:{listen_port}, forwarding to 127.0.0.1:{target_port}", flush=True)

    while True:
        try:
            client, addr = server.accept()
            target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target.connect(('127.0.0.1', target_port))
            threading.Thread(target=pipe, args=(client, target), daemon=True).start()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[TCP_FWD] Error: {e}", file=sys.stderr, flush=True)

if __name__ == '__main__':
    main()
