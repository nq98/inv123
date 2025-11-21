import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GOOGLE_CLOUD_PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT_ID', 'invoicereader-477008')
    GCS_INPUT_BUCKET = os.getenv('GCS_INPUT_BUCKET', 'payouts-invoices')
    REGION = os.getenv('REGION', 'us-central1')
    
    DOCAI_PROCESSOR_ID = os.getenv('DOCAI_PROCESSOR_ID', '919c19aabdb1802d')
    DOCAI_LOCATION = os.getenv('DOCAI_LOCATION', 'us')
    
    VERTEX_SEARCH_DATA_STORE_ID = os.getenv('VERTEX_SEARCH_DATA_STORE_ID', 'invoices-ds')
    VERTEX_SEARCH_COLLECTION = os.getenv('VERTEX_SEARCH_COLLECTION', 'default_collection')
    
    GOOGLE_GEMINI_API_KEY = os.getenv('GOOGLE_GEMINI_API_KEY')
    
    GMAIL_CLIENT_ID = os.getenv('GMAIL_CLIENT_ID')
    GMAIL_CLIENT_SECRET = os.getenv('GMAIL_CLIENT_SECRET')
    
    VERTEX_RUNNER_SA_PATH = os.getenv('VERTEX_RUNNER_SA_PATH', 'vertex-runner.json')
    DOCUMENTAI_ACCESS_SA_PATH = os.getenv('DOCUMENTAI_ACCESS_SA_PATH', 'documentai-access.json')
    
    @property
    def DOCAI_PROCESSOR_NAME(self):
        return f"projects/{self.GOOGLE_CLOUD_PROJECT_ID}/locations/{self.DOCAI_LOCATION}/processors/{self.DOCAI_PROCESSOR_ID}"
    
    @property
    def VERTEX_SEARCH_SERVING_CONFIG(self):
        return f"projects/{self.GOOGLE_CLOUD_PROJECT_ID}/locations/global/collections/{self.VERTEX_SEARCH_COLLECTION}/dataStores/{self.VERTEX_SEARCH_DATA_STORE_ID}/servingConfigs/default_search"

config = Config()
