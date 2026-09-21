#!/usr/bin/env python3
"""
Simple TCP forwarder for Windows host to forward incoming connections to WSL2.
Usage: python tcp_forwarder.py <listen_port> <target_port>
"""
import socket
import sys
import threading

def forward(src, dst):
    try:
        while True:
            data = src.recv(8192)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
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
            t1 = threading.Thread(target=forward, args=(client, target), daemon=True)
            t2 = threading.Thread(target=forward, args=(target, client), daemon=True)
            t1.start()
            t2.start()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[TCP_FWD] Error: {e}", file=sys.stderr, flush=True)

if __name__ == '__main__':
    main()
