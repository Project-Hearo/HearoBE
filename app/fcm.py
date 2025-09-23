import json
import requests
from google.oauth2 import service_account
import google.auth.transport.requests

def send_fcm_v1(token: str, title: str, body: str):

    service_account_path = "app/service_account.json"

    credentials = service_account.Credentials.from_service_account_file(
        service_account_path,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)

    access_token = credentials.token

    project_id = credentials.project_id
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8",
    }

    message = {
        "message": {
            "token": token,
            "notification": {
                "title": title,
                "body": body
            },
            "data": {
                "title": title,
                "body": body
            }
        }
    }

    response = requests.post(url, headers=headers, data=json.dumps(message))
    if response.status_code == 200:
        print("v1 FCM 알림 전송 성공")
    else:
        print(f"v1 FCM 전송 실패: {response.status_code}, {response.text}")
