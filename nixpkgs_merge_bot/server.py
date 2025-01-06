import contextlib
import os
import socket

from .git import clone
from .settings import Settings
from .webhook.handler import GithubWebHook


def start_server(settings: Settings) -> None:
    clone(settings.repo, settings.repo_path)
    nfds = os.environ.get("LISTEN_FDS", None)
    if nfds is not None:
        fds = range(3, 3 + int(nfds))
        for fd in fds:
            sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)

            while True:
                with contextlib.suppress(OSError):
                    GithubWebHook(*sock.accept(), settings)
    else:
        serversocket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            serversocket.bind((settings.host, settings.port))
            print(f"listen on {settings.host}:{settings.port}")
            serversocket.listen()
            while True:
                with contextlib.suppress(OSError):
                    conn, addr = serversocket.accept()
                    GithubWebHook(conn, addr, settings)
        finally:
            serversocket.shutdown(socket.SHUT_RDWR)
            serversocket.close()
