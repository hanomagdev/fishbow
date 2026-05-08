import requests
import json

BASE_URL = 'http://localhost:2456/api'
USERNAME = 'ClearviewSolutions'
PASSWORD = 'Clearview7!'

def login():
    url = f'{BASE_URL}/login'
    payload = {
        "appName": "FishbowlAutoShip",
        "appDescription": "Automatic order fulfillment script for pickable orders",
        "appId": 2286,
        "username": USERNAME,
        "password": PASSWORD
    }
    response = requests.post(url, json=payload)
    return response.json()['token']

def quick_ship(token, so_number):
    url = f'{BASE_URL}/quick-ship'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {'SONumber': so_number}
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

token = login()
print(f'Token: {token}')
result = quick_ship(token, 'SS279448')
print(f'Result: {json.dumps(result, indent=2)}')