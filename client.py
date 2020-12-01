import requests
import datetime
import json
import sys

url = "http://XXXX/tasks"

for arg in sys.argv:
    print(arg)


def get_task():
    response = requests.get(url + '/get')
    print(f"Request answer: {response.text}")


def add_task():
    response = requests.post(url + '/post')
    print(f"Request answer: {response.text}")


def del_task():
    response = requests.post(url + '/delete')
    print(f"Request answer: {response.text}")
