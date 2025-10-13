from flask import Flask
from config import Config
import os
import traceback

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Verify GOOGLE_API_KEY is loaded
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("❌ GOOGLE_API_KEY not found in environment variables")
        raise ValueError("GOOGLE_API_KEY not found in environment variables")
    
    print(f"✅ Google API Key loaded: {google_api_key[:20]}...")
    
    # Set the API key in environment for langchain
    os.environ["GOOGLE_API_KEY"] = google_api_key
    
    # Initialize RAG chain (cached globally)
    try:
        print("🔧 Initializing RAG chain...")
        from .rag_service import build_streaming_chain
        
        # Check if index exists
        index_path = app.config.get('INDEX_PATH', 'cbot_stlit/index')
        if not os.path.exists(index_path):
            print(f"⚠️  Index path not found: {index_path}")
            print(f"📂 Current directory: {os.getcwd()}")
            print(f"📂 Directory contents: {os.listdir('.')}")
        
        chain, retriever = build_streaming_chain(persist_dir=index_path)
        app.config['RAG_CHAIN'] = chain
        app.config['RAG_RETRIEVER'] = retriever
        print("✅ RAG chain initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize RAG chain: {str(e)}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        print("⚠️  App will continue but RAG features may not work")
        app.config['RAG_CHAIN'] = None
        app.config['RAG_RETRIEVER'] = None
    
    # Register blueprints
    with app.app_context():
        from . import routes
        app.register_blueprint(routes.bp)
    
    return app