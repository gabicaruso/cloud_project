import requests
from datetime import datetime
import json
import sys

with open("dns.txt", "r") as file:
    dns = file.read()

url = "http://" + dns + "/tasks"

for arg in sys.argv:
    print(arg)


def get_tasks():
    response = requests.get(url + '/get')

    if response.status_code != 200:
        file = open("out.txt", "w")
        file.write(response.text)
        file.close()
    else:
        print(f"Request Answer: {response.json()}")
    print(f"Request Status Code: {response.status_code}")


def add_task(payload):
    response = requests.post(url + '/add', data=json.dumps(payload))

    if response.status_code != 201:
        file = open("out.txt", "w")
        file.write(response.text)
        file.close()
    else:
        print(f"Request Answer: {response.json()}")
    print(f"Request Status Code: {response.status_code}")


def del_tasks():
    response = requests.delete(url + '/del')

    if response.status_code != 200:
        file = open("out.txt", "w")
        file.write(response.text)
        file.close()
    else:
        print(f"Request Answer: {response.json()}")
    print(f"Request Status Code: {response.status_code}")


if __name__ == '__main__':

    if sys.argv[1] == 'get_tasks':
        print("Looking for route /get_tasks...")
        get_tasks()

    elif sys.argv[1] == 'add_task':
        if len(sys.argv) >= 4:
            print("Looking for route /add_task...")
            title = sys.argv[2]
            description = sys.argv[3]
            pub_date = datetime.now().isoformat()
            payload = {'title': title, 'pub_date': pub_date,
                       'description': description}
            add_task(payload)
        else:
            print(
                "Insufficient arguments. Must insert 3 (add_task, title and description).")

    elif sys.argv[1] == 'del_tasks':
        print("Looking for route /del_task...")
        del_tasks()
