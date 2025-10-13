from flask import Blueprint, render_template, request, jsonify, Response, current_app
import json
import time
import traceback

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('chat.html')

@bp.route('/chat')
def chat():
    return render_template('chat.html')

@bp.route('/api/chat', methods=['POST'])
def chat_api():
    """Handle chat messages and return streaming response using RAG"""
    from .rag_service import is_allowed
    
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        chat_id = data.get('chat_id', None)
        
        print(f"📨 Received message: {user_message}")
        
        # Check if message is allowed
        if not is_allowed(user_message):
            return jsonify({'error': 'Sorry, I can\'t assist with that.'}), 400
        
        # Get RAG chain from app config
        chain = current_app.config.get('RAG_CHAIN')
        
        if chain is None:
            print("⚠️  RAG chain not available, using fallback")
            # Fallback response if RAG is not initialized
            def generate_fallback():
                response = "I apologize, but the AI system is currently unavailable. Please try again later."
                for char in response:
                    yield json.dumps({'token': char}) + '\n'
                    time.sleep(0.03)
            
            return Response(generate_fallback(), mimetype='application/json')
        
        def generate():
            try:
                print(f"🔄 Starting stream for: {user_message}")
                chunk_count = 0
                
                # Stream response from RAG chain
                for chunk in chain.stream(user_message):
                    if chunk:
                        chunk_count += 1
                        yield json.dumps({'token': chunk}) + '\n'
                
                print(f"✅ Streamed {chunk_count} chunks successfully")
                
            except Exception as e:
                error_msg = f"An error occurred while processing your request."
                print(f"❌ Error in RAG chain: {str(e)}")
                print(f"📋 Traceback: {traceback.format_exc()}")
                
                for char in error_msg:
                    yield json.dumps({'token': char}) + '\n'
        
        return Response(generate(), mimetype='application/json')
        
    except Exception as e:
        print(f"❌ Error in chat_api: {str(e)}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500

@bp.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    """Return chat history for student"""
    # TODO: Implement actual history retrieval from database
    mock_history = [
        {'id': '1', 'title': 'Help me understand calculus...'},
        {'id': '2', 'title': 'Write an essay about...'},
        {'id': '3', 'title': 'Explain photosynthesis...'}
    ]
    return jsonify({'history': mock_history})

@bp.route('/api/chat/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    """Get specific chat conversation"""
    # TODO: Implement actual chat retrieval from database
    return jsonify({'chat_id': chat_id, 'messages': []})

@bp.route('/api/search', methods=['POST'])
def search_documents():
    """Search for relevant documents using the retriever"""
    from .rag_service import is_allowed
    
    data = request.get_json()
    query = data.get('query', '')
    
    if not is_allowed(query):
        return jsonify({'error': 'Sorry, I can\'t assist with that.'}), 400
    
    retriever = current_app.config.get('RAG_RETRIEVER')
    
    if retriever is None:
        return jsonify({'error': 'Search system unavailable'}), 503
    
    try:
        # Get relevant documents
        docs = retriever.get_relevant_documents(query)
        
        # Format results
        results = []
        for doc in docs:
            results.append({
                'content': doc.page_content,
                'metadata': doc.metadata
            })
        
        return jsonify({'results': results})
    
    except Exception as e:
        print(f"❌ Search error: {e}")
        return jsonify({'error': 'Search failed'}), 500