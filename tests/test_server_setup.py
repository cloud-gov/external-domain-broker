import time
from multiprocessing import Process
import pytest
import requests


def test_server_runs():
    def run_server():
        from broker import setup_app

        setup_app().run()

    server = Process(target=run_server)
    server.start()
    time.sleep(0.5)

    response = requests.get("http://localhost:5000/ping")
    assert response.status_code == 200
    assert response.text == "PONG"

    server.terminate()
    server.join()
