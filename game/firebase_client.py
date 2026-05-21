import os

import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv


load_dotenv()


def get_firestore_client():
    """
    Tạo và trả về Firestore client.
    Hàm này chỉ initialize Firebase 1 lần.
    """

    if not firebase_admin._apps:
        cred_path = os.getenv("FIREBASE_CREDENTIALS")

        if not cred_path:
            raise RuntimeError("Thiếu FIREBASE_CREDENTIALS trong file .env")

        if not os.path.exists(cred_path):
            raise RuntimeError(f"Không tìm thấy file Firebase credentials: {cred_path}")

        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    return firestore.client()