from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY') or 'a_default_secret_key'
    DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
    
    # Google API Configuration
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    
    # RAG Configuration
    INDEX_PATH = 'index'
    
    # Supabase Configuration (for future database integration)
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')