"""
RAG Service for Flask integration
Adapted from cbot_stlit/rag_chain_hybrid.py with smart retrieval
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
    
    return "huggingface"  # Default to HuggingFace

def load_retriever(persist_dir="index", embedding_type=None):
    """
    Load retriever with automatic embedding model detection
    Returns the vector store (not retriever) for flexible querying
    """
    if embedding_type is None:
        embedding_type = detect_embedding_type(persist_dir)
    
    print(f"🔍 Loading index with {embedding_type} embeddings...")
    
    try:
        if embedding_type == "huggingface":
            # For indexes created with open-source models
            # Use the same model that was used for ingestion
            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},
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
        print(f"✅ Successfully loaded index with {embedding_type} embeddings")
        return vs
        
    except Exception as e:
        print(f"❌ Failed to load with {embedding_type} embeddings: {e}")
        
        # Try the other embedding type as fallback
        fallback_type = "gemini" if embedding_type == "huggingface" else "huggingface"
        print(f"🔄 Trying fallback: {fallback_type} embeddings...")
        
        try:
            if fallback_type == "huggingface":
                embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
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
            print(f"✅ Successfully loaded index with {fallback_type} embeddings (fallback)")
            return vs
            
        except Exception as e2:
            print(f"❌ Both embedding types failed. Error: {e2}")
            raise e2


# Keep load_vectorstore as an alias for compatibility with existing code
def load_vectorstore(persist_dir="index", embedding_type=None):
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
        print(f"🔍 Detected exhaustive query - using adaptive retrieval (k=50)")
        docs_with_scores = vectorstore.similarity_search_with_score(query, k=50)
        
        # Debug: Show score distribution
        if docs_with_scores:
            scores = [score for _, score in docs_with_scores[:10]]
            print(f"📊 Sample scores (top 10): min={min(scores):.3f}, max={max(scores):.3f}")
        
        # Dynamic threshold based on score distribution
        if docs_with_scores:
            best_score = docs_with_scores[0][1]
            threshold = min(best_score * 1.5, 2.0)
            print(f"🎯 Using adaptive threshold: {threshold:.3f} (based on best score: {best_score:.3f})")
            
            filtered_docs = [doc for doc, score in docs_with_scores if score <= threshold]
        else:
            filtered_docs = []
        
        print(f"✅ Retrieved {len(filtered_docs)} relevant documents")
        return filtered_docs
    else:
        # Standard semantic search: top-k most relevant
        print(f"🔍 Standard semantic search (k=6)")
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


def format_chat_history(messages: list, max_exchanges: int = 5) -> str:
    """
    Format chat history for inclusion in the prompt
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        max_exchanges: Maximum number of exchanges to include (default 5 = 10 messages)
    
    Returns:
        Formatted string of conversation history
    """
    if not messages:
        return ""
    
    # Take last N messages (max_exchanges * 2 for user+bot pairs)
    recent_messages = messages[-(max_exchanges * 2):]
    
    history_lines = []
    for msg in recent_messages:
        role = "Human" if msg['role'] == 'user' else "Assistant"
        content = msg['content']
        
        # Truncate very long messages to prevent token overflow
        if len(content) > 500:
            content = content[:500] + "..."
        
        history_lines.append(f"{role}: {content}")
    
    return "\n".join(history_lines)


# Load abstract and title data files
try:
    abstract_file = os.path.join("index", "data_abstract.txt")
    title_file = os.path.join("index", "data_title_url.txt")
    
    file_content1 = ""
    file_content2 = ""
    
    if os.path.exists(abstract_file):
        with open(abstract_file, "r", encoding="utf-8") as f1:
            file_content1 = f1.read()
            print(f"✅ Loaded data_abstract.txt")
    
    if os.path.exists(title_file):
        with open(title_file, "r", encoding="utf-8") as f2:
            file_content2 = f2.read()
            print(f"✅ Loaded data_title_url.txt")
except Exception as e:
    print(f"⚠️ Could not load data files: {e}")
    file_content1 = ""
    file_content2 = ""


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
- Maintain conversation context and refer back to previous exchanges when relevant

RESPONSE GUIDELINES:
- Always answer based STRICTLY on the provided context
- Always answer direct to the point
- Use conversation history to provide contextual responses (e.g., "As I mentioned earlier...", "Regarding the thesis we discussed...")
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
- Follow-up questions → Use conversation history to maintain context

CITATION FORMAT:
Use APA style
Example: [Santos et al. AI in Education. 2023. Computer Science Dept, CSPC]

Remember: You are helping unlock CSPC's academic knowledge for the research community."""

# Updated prompt template with conversation history
CONVERSATIONAL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{chat_history}\n\nCurrent Question: {question}\n\nRelevant Context:\n{context}"),
])


def build_chain(embedding_type=None) -> Tuple:
    """
    Build basic RAG chain (non-streaming) - matches rag_chain.py exactly
    Returns: (chain, vectorstore)
    """
    vectorstore = load_retriever(embedding_type=embedding_type)
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    # Create a custom retrieval function that uses smart_retrieve
    def custom_retrieve(inputs: dict) -> str:
        question = inputs.get("question", "")
        docs = smart_retrieve(question, vectorstore)
        return format_docs(docs)
    
    # Build chain with smart retrieval integration and conversation history
    chain = (
        {
            "context": custom_retrieve, 
            "question": lambda x: x.get("question", ""),
            "chat_history": lambda x: x.get("chat_history", "")
        }
        | CONVERSATIONAL_PROMPT
        | llm
        | StrOutputParser()
    )
    
    # Return both chain and vectorstore for flexibility
    return chain, vectorstore


def build_streaming_chain(persist_dir="index"):
    """
    Build RAG chain with streaming support, smart retrieval, and conversation memory
    Uses same configuration as build_chain but with streaming enabled
    Returns: (chain, vectorstore)
    """
    try:
        print("🚀 Building streaming RAG chain with conversation memory...")
        
        # Load vectorstore using the same function as build_chain
        vectorstore = load_retriever(persist_dir)
        
        print("🤖 Initializing Gemini LLM with streaming...")
        # Create LLM with streaming - using same model as rag_chain.py
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            streaming=True
        )
        
        # Create custom retrieval function that uses smart_retrieve
        def custom_retrieve(inputs: dict) -> str:
            question = inputs.get("question", "")
            docs = smart_retrieve(question, vectorstore)
            formatted = format_docs(docs)
            
            # Log context size to detect overload
            print(f"📏 Context size: {len(formatted)} chars, {len(docs)} docs")
            
            # Warn if context is too large
            if len(formatted) > 50000:
                print(f"⚠️  Large context detected ({len(formatted)} chars) - may cause truncation")
            
            return formatted
        
        # Build chain with smart retrieval and conversation history
        chain = (
            {
                "context": custom_retrieve,
                "question": lambda x: x.get("question", ""),
                "chat_history": lambda x: x.get("chat_history", "")
            }
            | CONVERSATIONAL_PROMPT
            | llm
            | StrOutputParser()
        )
        
        print("✅ Streaming RAG chain with conversation memory built successfully")
        print(f"   - Model: gemini-2.5-flash")
        print(f"   - Temperature: 0")
        print(f"   - Streaming: enabled")
        print(f"   - Conversation memory: enabled")
        return chain, vectorstore
        
    except Exception as e:
        print(f"❌ Failed to build streaming chain: {str(e)}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        raise e