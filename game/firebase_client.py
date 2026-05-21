import json
import os

import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv


load_dotenv()


def get_firestore_client():
    """
    Tạo Firestore client.

    Local:
    - Dùng FIREBASE_CREDENTIALS=secrets/firebase-service-account.json

    Railway / Hosting:
    - Dùng FIREBASE_SERVICE_ACCOUNT_JSON={toàn bộ nội dung service account json}
    """

    if firebase_admin._apps:
        return firestore.client()

    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if service_account_json:
        try:
            service_account_info = json.loads(service_account_json)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "FIREBASE_SERVICE_ACCOUNT_JSON không phải JSON hợp lệ. "
                "Hãy copy toàn bộ nội dung firebase-service-account.json."
            ) from e

        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
        return firestore.client()

    cred_path = os.getenv("FIREBASE_CREDENTIALS")

    if not cred_path:
        raise RuntimeError(
            "Thiếu Firebase credentials. Cần FIREBASE_SERVICE_ACCOUNT_JSON "
            "trên hosting hoặc FIREBASE_CREDENTIALS khi chạy local."
        )

    if not os.path.exists(cred_path):
        raise RuntimeError(
            f"Không tìm thấy file Firebase credentials: {cred_path}"
        )

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

    return firestore.client()