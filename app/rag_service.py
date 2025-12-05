"""
RAG Service for Flask integration
Adapted from cbot_stlit/rag_chain_hybrid.py with smart retrieval
"""
from typing import Tuple, Generator
from langchain_community.vectorstores import FAISS
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
import os
import traceback
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logger
logger = logging.getLogger(__name__)

# Get base directory for reliable path resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Content moderation
DISALLOWED = ("how to make a bomb", "explosive materials", "hatred", "self-harm")

def is_allowed(question: str) -> bool:
    """Check if the question contains disallowed content"""
    ql = question.lower()
    return not any(term in ql for term in DISALLOWED)

def detect_embedding_type(persist_dir=None):
    """
    Detect which embedding model was used to create the index
    """
    if persist_dir is None:
        persist_dir = os.path.join(BASE_DIR, "index")
    
    metadata_file = os.path.join(persist_dir, "embedding_model.txt")
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            return f.read().strip()
    
    return "huggingface"  # Default to HuggingFace

def load_retriever(persist_dir=None, embedding_type=None):
    """
    Load retriever with automatic embedding model detection
    Returns the vector store (not retriever) for flexible querying
    """
    if persist_dir is None:
        persist_dir = os.path.join(BASE_DIR, "index")
    
    if embedding_type is None:
        embedding_type = detect_embedding_type(persist_dir)
    
    logger.info(f"Loading index with {embedding_type} embeddings...")
    
    try:
        if embedding_type == "huggingface":
            # For indexes created with open-source models
            # Use the same model that was used for ingestion
            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",  # Match your ingestion model
                model_kwargs={'device': 'cpu'},  # Use CPU for local inference
                encode_kwargs={'normalize_embeddings': True}
            )
        else:
            # For indexes created with Gemini API
            embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-001",
                task_type="RETRIEVAL_QUERY",
                async_client=False
            )
        
        vs = FAISS.load_local(persist_dir, embeddings, allow_dangerous_deserialization=True)
        logger.info(f"Successfully loaded index with {embedding_type} embeddings")
        return vs
        
    except Exception as e:
        logger.warning(f"Failed to load with {embedding_type} embeddings: {e}")
        
        # Try the other embedding type as fallback
        fallback_type = "gemini" if embedding_type == "huggingface" else "huggingface"
        logger.info(f"Trying fallback: {fallback_type} embeddings...")
        
        try:
            if fallback_type == "huggingface":
                embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",  # Match your ingestion model
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
            else:
                embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/gemini-embedding-001",
                    task_type="RETRIEVAL_QUERY",
                    async_client=False
                )
            
            vs = FAISS.load_local(persist_dir, embeddings, allow_dangerous_deserialization=True)
            logger.info(f"Successfully loaded index with {fallback_type} embeddings (fallback)")
            return vs
            
        except Exception as e2:
            logger.error(f"Both embedding types failed. Error: {e2}")
            raise e2


# Keep load_vectorstore as an alias for compatibility with existing code
def load_vectorstore(persist_dir=None, embedding_type=None):
    """
    Load vector store (not retriever) for flexible querying
    Returns FAISS vectorstore
    Alias for load_retriever for backward compatibility
    """
    return load_retriever(persist_dir, embedding_type)


def is_exhaustive_query(query: str) -> bool:
    """
    Detect if the query is asking for exhaustive/comprehensive results
    """
    exhaustive_keywords = [
        "all", "list", "every", "give me all", "show me all",
        "how many", "what are all", "enumerate", "complete list"
    ]
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in exhaustive_keywords)


def smart_retrieve(query: str, vectorstore):
    """
    Adaptive retrieval that adjusts k and uses threshold filtering based on query intent
    
    - For exhaustive queries ("give me all X"): Uses high k + threshold filtering
    - For specific queries: Uses standard top-k retrieval
    """
    is_exhaustive = is_exhaustive_query(query)
    
    if is_exhaustive:
        # Exhaustive query: retrieve more docs and filter by similarity threshold
        logger.debug(f"Detected exhaustive query - using adaptive retrieval (k=50)")
        docs_with_scores = vectorstore.similarity_search_with_score(query, k=50)
        
        # Debug: Show score distribution
        if docs_with_scores:
            scores = [score for _, score in docs_with_scores[:10]]
            logger.debug(f"Sample scores (top 10): min={min(scores):.3f}, max={max(scores):.3f}")
        
        # Dynamic threshold based on score distribution
        # For HuggingFace: typically 0.8-1.5 range, use higher threshold
        # For Gemini: typically 0.3-0.8 range, use lower threshold
        # Strategy: Take documents within 150% of the best score
        if docs_with_scores:
            best_score = docs_with_scores[0][1]
            # Use adaptive threshold: 1.5x the best score, capped at 2.0
            threshold = min(best_score * 1.5, 2.0)
            logger.debug(f"Using adaptive threshold: {threshold:.3f} (based on best score: {best_score:.3f})")
            
            filtered_docs = [doc for doc, score in docs_with_scores if score <= threshold]
        else:
            filtered_docs = []
        
        logger.debug(f"Retrieved {len(filtered_docs)} relevant documents")
        return filtered_docs
    else:
        # Standard semantic search: top-k most relevant
        logger.debug(f"Standard semantic search (k=6)")
        return vectorstore.similarity_search(query, k=6)


def format_docs(docs):
    """Format documents with enhanced metadata for thesis-specific retrieval."""
    out = []
    abstract_docs = []
    other_docs = []
    
    # Separate abstracts and other content for prioritization
    for doc in docs:
        meta = doc.metadata or {}
        if meta.get("content_type") == "abstract":
            abstract_docs.append(doc)
        else:
            other_docs.append(doc)
    
    # Process abstracts first (higher priority)
    for i, d in enumerate(abstract_docs, 1):
        meta = d.metadata or {}
        src = meta.get("source", "document").replace("\\", "/").split("/")[-1]
        page = meta.get("page", "")
        content_type = meta.get("content_type", "")
        chapter = meta.get("chapter", "")
        
        label_parts = [f"S{i}", src]
        if page:
            label_parts.append(f"p.{page}")
        if content_type:
            label_parts.append(f"({content_type})")
        if chapter:
            label_parts.append(f"Ch.{chapter}")
        
        label = f"[{' '.join(label_parts)}]"
        out.append(d.page_content + f"\n{label}")
    
    # Then process other documents
    start_idx = len(abstract_docs) + 1
    for i, d in enumerate(other_docs, start_idx):
        meta = d.metadata or {}
        src = meta.get("source", "document").replace("\\", "/").split("/")[-1]
        page = meta.get("page", "")
        content_type = meta.get("content_type", "")
        chapter = meta.get("chapter", "")
        
        label_parts = [f"S{i}", src]
        if page:
            label_parts.append(f"p.{page}")
        if content_type:
            label_parts.append(f"({content_type})")
        if chapter:
            label_parts.append(f"Ch.{chapter}")
        
        label = f"[{' '.join(label_parts)}]"
        out.append(d.page_content + f"\n{label}")
    
    return "\n\n".join(out)


# Load abstract and title data files using absolute paths
def _load_data_files():
    """Load abstract and title data files at module initialization"""
    abstract_file = os.path.join(BASE_DIR, "index", "data_abstract.txt")
    title_file = os.path.join(BASE_DIR, "index", "data_title_url.txt")
    
    content1 = ""
    content2 = ""
    
    try:
        if os.path.exists(abstract_file):
            with open(abstract_file, "r", encoding="utf-8") as f1:
                content1 = f1.read()
                logger.info("Loaded data_abstract.txt")
        else:
            logger.warning(f"data_abstract.txt not found at {abstract_file}")
        
        if os.path.exists(title_file):
            with open(title_file, "r", encoding="utf-8") as f2:
                content2 = f2.read()
                logger.info("Loaded data_title_url.txt")
        else:
            logger.warning(f"data_title_url.txt not found at {title_file}")
    except Exception as e:
        logger.warning(f"Could not load data files: {e}")
    
    return content1, content2

file_content1, file_content2 = _load_data_files()


SYSTEM_PROMPT = f"""
You are Adal, an AI assistant specialized in CSPC (Camarines Sur Polytechnic College) thesis and academic research retrieval.

You were created and are maintained by TEAM VIRGO.

Your current knowledge base only includes theses and research coming from the following CSPC colleges: BSM, BSN, CAS, CCS, and CTHBM. Note that the CCS collection does not yet contain Computer Science theses, and there are no engineering theses available in your data.

First:
 -Read the \n{file_content2} and look for clue that will help you answer the question and provide the url.


CORE RESPONSIBILITIES:
- Help users discover and explore CSPC thesis documents and academic research
- Provide complete abstracts when requested or when relevant to the query
- Generate proper APA citations for thesis sources
- Suggest related research based on semantic similarity
- Handle both specific queries (returns top relevant results) and exhaustive queries (returns all matching results)

RESPONSE GUIDELINES:
- Always answer based STRICTLY on the provided context
- Always answer direct to the point
- If information is not in the context, clearly state "I didn't find that information in my knowledge base, but you can try rephrasing your question and I'll search again"
- When providing abstracts, give the COMPLETE abstract text if available in context
- For thesis-related queries, prioritize abstract and metadata information
- Include proper APA citations at the end using format: [Author, Year. Title. Department, CSPC]
- If the question is too vague, ask clarifying questions to narrow down the topic
- For "give me all" or "list all" queries, provide a comprehensive list of ALL matching theses found in context

QUERY TYPES TO HANDLE:
- "What is [thesis title] about?" → Provide abstract and key findings
- "Show me the abstract of..." → Provide complete abstract text
- "Find theses about [topic]" → List relevant research with brief descriptions
- "Give me all research on [topic]" → List ALL matching theses comprehensively
- "How many theses about [topic]?" → Count and list all matching theses
- "Who wrote about [subject]?" → Identify authors and their work
- "What department studies [field]?" → Identify relevant departments and their research

CITATION FORMAT:
Use APA style
Example: [Santos et al. AI in Education. 2023. Computer Science Dept, CSPC]

Remember: You are helping unlock CSPC's academic knowledge for the research community."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Question: {question}\n\nContext:\n{context}"),
])


def build_chain(embedding_type=None) -> Tuple:
    """
    Build basic RAG chain (non-streaming) - matches rag_chain.py exactly
    Returns: (chain, vectorstore)
    """
    vectorstore = load_retriever(embedding_type=embedding_type)
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    # Create a custom retrieval function that uses smart_retrieve
    def custom_retrieve(question: str) -> str:
        docs = smart_retrieve(question, vectorstore)
        return format_docs(docs)
    
    # Build chain with smart retrieval integration
    chain = (
        {
            "context": lambda x: custom_retrieve(x), 
            "question": RunnablePassthrough()
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    
    # Return both chain and vectorstore for flexibility
    return chain, vectorstore


def build_streaming_chain(persist_dir=None):
    """
    Build RAG chain with streaming support and smart retrieval for Flask
    Uses same configuration as build_chain but with streaming enabled
    Returns: (chain, vectorstore)
    """
    if persist_dir is None:
        persist_dir = os.path.join(BASE_DIR, "index")
    
    try:
        logger.info("Building streaming RAG chain with smart retrieval...")
        
        # Load vectorstore using the same function as build_chain
        vectorstore = load_retriever(persist_dir)
        
        logger.info("Initializing Gemini LLM with streaming...")
        # Create LLM with streaming - using same model as rag_chain.py
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            streaming=True
        )
        
        # Create custom retrieval function that uses smart_retrieve
        def custom_retrieve(question: str) -> str:
            docs = smart_retrieve(question, vectorstore)
            formatted = format_docs(docs)
            
            # Log context size to detect overload
            logger.debug(f"Context size: {len(formatted)} chars, {len(docs)} docs")
            
            # Warn if context is too large
            if len(formatted) > 50000:
                logger.warning(f"Large context detected ({len(formatted)} chars) - may cause truncation")
            
            return formatted
        
        # Build chain with smart retrieval - using same structure as rag_chain.py
        chain = (
            {
                "context": lambda x: custom_retrieve(x),
                "question": RunnablePassthrough()
            }
            | prompt
            | llm
            | StrOutputParser()
        )
        
        logger.info("Streaming RAG chain built successfully (model: gemini-2.5-flash, streaming: enabled)")
        return chain, vectorstore
        
    except Exception as e:
        logger.error(f"Failed to build streaming chain: {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        raise e