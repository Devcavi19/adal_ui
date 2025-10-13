"""
RAG Service for Flask integration
Adapted from cbot_stlit/rag_chain_hybrid.py
"""
from typing import Tuple, Generator
from langchain_community.vectorstores import FAISS
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
import os
import traceback
from dotenv import load_dotenv

load_dotenv()

# Content moderation
DISALLOWED = ("how to make a bomb", "explosive materials", "hatred", "self-harm")

def is_allowed(question: str) -> bool:
    """Check if the question contains disallowed content"""
    ql = question.lower()
    return not any(term in ql for term in DISALLOWED)

def detect_embedding_type(persist_dir="index"):
    """
    Detect which embedding model was used to create the index
    """
    metadata_file = os.path.join(persist_dir, "embedding_model.txt")
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            return f.read().strip()
    
    # Try to detect based on index dimensions
    try:
        import pickle
        with open(os.path.join(persist_dir, "index.faiss"), 'rb') as f:
            # FAISS index stores dimension info
            pass
    except:
        pass
    
    return "huggingface"  # Default to HuggingFace as it's more common

def load_retriever(persist_dir="index", embedding_type=None):
    """
    Load retriever with automatic embedding model detection
    """
    if embedding_type is None:
        embedding_type = detect_embedding_type(persist_dir)
    
    print(f"🔍 Loading index with {embedding_type} embeddings from {persist_dir}...")
    
    # Check if index directory exists
    if not os.path.exists(persist_dir):
        raise FileNotFoundError(f"Index directory not found: {persist_dir}")
    
    # Check for required FAISS files
    required_files = ['index.faiss', 'index.pkl']
    for file in required_files:
        file_path = os.path.join(persist_dir, file)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Required index file not found: {file_path}")
    
    try:
        if embedding_type == "huggingface":
            print("📦 Loading HuggingFace embeddings...")
            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            print(f"✅ HuggingFace embeddings loaded (dimension: 384)")
        else:
            print("📦 Loading Gemini embeddings...")
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not found in environment")
            
            embeddings = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=api_key,
                task_type="retrieval_document"
            )
            print(f"✅ Gemini embeddings loaded (dimension: 768)")
        
        print(f"📂 Loading FAISS index from {persist_dir}...")
        vs = FAISS.load_local(
            persist_dir, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
        print(f"✅ Successfully loaded index with {embedding_type} embeddings")
        
        # Get index info
        print(f"📊 Index info: {vs.index.ntotal} vectors")
        
        return vs.as_retriever(search_kwargs={"k": 6})
        
    except AssertionError as e:
        print(f"❌ Dimension mismatch error with {embedding_type} embeddings")
        print(f"📋 This usually means the index was created with a different embedding model")
        
        # Try fallback
        fallback_type = "gemini" if embedding_type == "huggingface" else "huggingface"
        print(f"🔄 Trying fallback: {fallback_type} embeddings...")
        
        try:
            if fallback_type == "huggingface":
                embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
                print(f"✅ HuggingFace embeddings loaded (dimension: 384)")
            else:
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY not found in environment")
                
                embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/embedding-001",
                    google_api_key=api_key,
                    task_type="retrieval_document"
                )
                print(f"✅ Gemini embeddings loaded (dimension: 768)")
            
            vs = FAISS.load_local(persist_dir, embeddings, allow_dangerous_deserialization=True)
            print(f"✅ Successfully loaded index with {fallback_type} embeddings (fallback)")
            return vs.as_retriever(search_kwargs={"k": 6})
            
        except Exception as e2:
            print(f"❌ Both embedding types failed.")
            print(f"📋 Error: {str(e2)}")
            print(f"💡 Suggestion: Check which embedding model was used to create the index")
            print(f"💡 You may need to recreate the index with the correct embedding model")
            raise e2
    
    except Exception as e:
        print(f"❌ Failed to load with {embedding_type} embeddings: {str(e)}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        raise e

SYSTEM_PROMPT = """You are Adal, an AI assistant specialized in CSPC (Camarines Sur Polytechnic College) thesis and academic research retrieval.

CORE RESPONSIBILITIES:
- Help users discover and explore CSPC thesis documents and academic research
- Provide complete abstracts when requested or when relevant to the query
- Generate proper APA citations for thesis sources
- Suggest related research based on semantic similarity
- Support both Filipino and English academic content

RESPONSE GUIDELINES:
- Always answer based STRICTLY on the provided context
- If information is not in the context, clearly state "I don't have that information in the available documents"
- Reply in the SAME language as the user's question (Filipino or English)
- When providing abstracts, give the COMPLETE abstract text if available in context
- For thesis-related queries, prioritize abstract and metadata information
- Include proper APA citations at the end using format: [Author, Year. Title. Department, CSPC]

QUERY TYPES TO HANDLE:
- "What is [thesis title] about?" → Provide abstract and key findings
- "Find research about [topic]" → List relevant theses with brief descriptions
- "Show abstract of [title]" → Provide complete abstract
- "Who wrote about [topic]?" → List authors and their works
- "What's available in [department]?" → List department-specific research

Context from documents:
{context}

User Question: {question}

Answer:"""

def build_streaming_chain(persist_dir="index"):
    """
    Build RAG chain with streaming support for Flask
    Returns: (chain, retriever)
    """
    try:
        print("🚀 Building streaming RAG chain...")
        
        # Load retriever
        retriever = load_retriever(persist_dir)
        
        # Get API key
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")
        
        print("🤖 Initializing Gemini LLM...")
        # Create LLM with streaming
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0.3,
            max_output_tokens=2048,
            streaming=True
        )
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)
        
        # Build chain
        chain = (
            {"context": retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        
        print("✅ Streaming RAG chain built successfully")
        return chain, retriever
        
    except Exception as e:
        print(f"❌ Failed to build streaming chain: {str(e)}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        raise e