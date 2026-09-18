import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)

API_BASE_URL = os.getenv("API_BASE_URL", "https://reqres.in/api")
FAKESTORE_BASE_URL = os.getenv("FAKESTORE_BASE_URL", "https://fakestoreapi.com")

PAYMENT_MOCK_HOST = os.getenv("PAYMENT_MOCK_HOST", "127.0.0.1")
PAYMENT_MOCK_PORT = int(os.getenv("PAYMENT_MOCK_PORT", "8001"))
PAYMENT_MOCK_URL = f"http://{PAYMENT_MOCK_HOST}:{PAYMENT_MOCK_PORT}"

QUEUE_MOCK_HOST = os.getenv("QUEUE_MOCK_HOST", "127.0.0.1")
QUEUE_MOCK_PORT = int(os.getenv("QUEUE_MOCK_PORT", "8002"))
QUEUE_MOCK_URL = f"http://{QUEUE_MOCK_HOST}:{QUEUE_MOCK_PORT}"
QUEUE_PROCESSING_DELAY_MS = int(os.getenv("QUEUE_PROCESSING_DELAY_MS", "200"))

E2E_BASE_URL = os.getenv("E2E_BASE_URL", "https://www.saucedemo.com")
E2E_USERNAME = os.getenv("E2E_USERNAME", "standard_user")
E2E_PASSWORD = os.getenv("E2E_PASSWORD", "secret_sauce")
E2E_HEADLESS = os.getenv("E2E_HEADLESS", "true").lower() == "true"
