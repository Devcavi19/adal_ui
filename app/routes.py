from flask import Blueprint, render_template, request, jsonify, Response, current_app, redirect, url_for, session
import json
import time
import traceback
import threading
from functools import wraps

bp = Blueprint('main', __name__)

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('main.login'))
    return render_template('chat.html')

@bp.route('/login')
def login():
    if 'user' in session:
        return redirect(url_for('main.chat'))
    return render_template('login.html')

@bp.route('/signup')
def signup():
    if 'user' in session:
        return redirect(url_for('main.chat'))
    return render_template('signup.html')

@bp.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

# Authentication API Routes
@bp.route('/api/auth/signup', methods=['POST'])
def api_signup():
    """Handle email signup"""
    from .auth_service import auth_service
    
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    
    result, status_code = auth_service.sign_up_with_email(email, password, full_name)
    return jsonify(result), status_code

@bp.route('/api/auth/signin', methods=['POST'])
def api_signin():
    """Handle email signin"""
    from .auth_service import auth_service
    
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    result, status_code = auth_service.sign_in_with_email(email, password)
    
    if status_code == 200:
        session['user'] = result['user']
        session['access_token'] = result['session']['access_token']
    
    return jsonify(result), status_code

@bp.route('/api/auth/google')
def api_google_auth():
    """Get Google OAuth URL"""
    from .auth_service import auth_service
    
    result, status_code = auth_service.sign_in_with_google()
    return jsonify(result), status_code

@bp.route('/auth/callback')
def auth_callback():
    """Handle OAuth callback - both hash fragment and query params"""
    from .auth_service import auth_service
    
    # Check for authorization code in query params (OAuth flow)
    code = request.args.get('code')
    
    if code:
        # Exchange code for session
        result, status_code = auth_service.exchange_code_for_session(code)
        
        if status_code == 200:
            session['user'] = result['user']
            session['access_token'] = result['session']['access_token']
            return redirect(url_for('main.chat'))
        else:
            return redirect(url_for('main.login', error='auth_failed'))
    
    # Otherwise render callback page to handle hash fragment
    return render_template('auth_callback.html')

@bp.route('/api/auth/callback/session', methods=['POST'])
def api_callback_session():
    """Handle session creation from OAuth callback"""
    from .auth_service import auth_service
    
    data = request.get_json()
    access_token = data.get('access_token')
    
    if not access_token:
        return jsonify({'error': 'Access token required'}), 400
    
    # Get user info from token
    result, status_code = auth_service.get_user(access_token)
    
    if status_code == 200:
        session['user'] = result['user']
        session['access_token'] = access_token
        return jsonify({'success': True, 'redirect': '/chat'}), 200
    
    return jsonify({'error': 'Failed to get user info'}), status_code

@bp.route('/api/auth/signout', methods=['POST'])
def api_signout():
    """Handle signout"""
    from .auth_service import auth_service
    
    session.clear()
    result, status_code = auth_service.sign_out()
    return jsonify(result), status_code

@bp.route('/api/auth/user', methods=['GET'])
def api_get_user():
    """Get current user"""
    if 'user' in session:
        return jsonify({'user': session['user']}), 200
    return jsonify({'error': 'Not authenticated'}), 401

# Chat API Routes - OPTIMIZED FOR STREAMING
@bp.route('/api/chat', methods=['POST'])
@login_required
def chat_api():
    """Handle chat messages with OPTIMIZED streaming (save to DB after streaming)"""
    from .rag_service import is_allowed
    from .auth_service import auth_service
    
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        chat_id = data.get('chat_id', None)
        
        print(f"📨 Received message: {user_message}")
        
        if not is_allowed(user_message):
            return jsonify({'error': 'Sorry, I can\'t assist with that.'}), 400
        
        user_id = session.get('user', {}).get('id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        # Create new chat session if needed (lightweight operation)
        if not chat_id:
            title = user_message[:50] + ('...' if len(user_message) > 50 else '')
            chat_session, status = auth_service.create_chat_session(user_id, title)
            
            if status != 200:
                print(f"❌ Failed to create chat session: {chat_session}")
                return jsonify({'error': 'Failed to create chat session'}), 500
            
            chat_id = chat_session['id']
            print(f"✅ Created new chat session: {chat_id}")
        
        chain = current_app.config.get('RAG_CHAIN')
        
        if chain is None:
            print("⚠️  RAG chain not available, using fallback")
            def generate_fallback():
                yield json.dumps({'chat_id': chat_id}) + '\n'
                response = "I apologize, but the AI system is currently unavailable. Please try again later."
                for char in response:
                    yield json.dumps({'token': char}) + '\n'
                    time.sleep(0.03)
            
            return Response(generate_fallback(), mimetype='application/json')
        
        bot_response = ""
        
        def save_messages_async():
            """Save messages to database in background thread AFTER streaming completes"""
            try:
                print(f"💾 Saving messages to database in background...")
                
                # Save user message
                msg_result, msg_status = auth_service.save_chat_message(chat_id, 'user', user_message)
                if msg_status == 200:
                    print(f"✅ User message saved")
                else:
                    print(f"⚠️  Failed to save user message: {msg_result}")
                
                # Save bot response
                if bot_response:
                    msg_result, msg_status = auth_service.save_chat_message(chat_id, 'bot', bot_response)
                    if msg_status == 200:
                        print(f"✅ Bot response saved ({len(bot_response)} chars)")
                    else:
                        print(f"⚠️  Failed to save bot response: {msg_result}")
                        
            except Exception as e:
                print(f"❌ Error saving messages in background: {str(e)}")
                print(f"📋 Traceback: {traceback.format_exc()}")
        
        def generate():
            nonlocal bot_response
            try:
                print(f"🔄 Starting FAST RAG stream (NO database blocking)...")
                chunk_count = 0
                
                # Send chat_id FIRST - immediate flush
                yield json.dumps({'chat_id': chat_id}) + '\n'
                
                # Stream the response IMMEDIATELY with aggressive flushing
                for chunk in chain.stream(user_message):
                    if chunk:
                        bot_response += chunk
                        chunk_count += 1
                        # Yield each token immediately - no buffering
                        yield json.dumps({'token': chunk}) + '\n'
                
                print(f"✅ Streamed {chunk_count} chunks (total: {len(bot_response)} chars)")
                
                # Save to database AFTER streaming completes (in background thread)
                threading.Thread(target=save_messages_async, daemon=True).start()
                
            except Exception as e:
                error_msg = "An error occurred while processing your request."
                print(f"❌ Error in RAG chain: {str(e)}")
                print(f"📋 Traceback: {traceback.format_exc()}")
                
                # Stream error message
                for char in error_msg:
                    yield json.dumps({'token': char}) + '\n'
        
        return Response(generate(), mimetype='application/json')
        
    except Exception as e:
        print(f"❌ Error in chat_api: {str(e)}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500

@bp.route('/api/chat/history', methods=['GET'])
@login_required
def get_chat_history():
    """Return chat history for student"""
    from .auth_service import auth_service
    
    user_id = session.get('user', {}).get('id')
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401
    
    sessions, status = auth_service.get_user_chat_sessions(user_id)
    
    if status == 200:
        return jsonify({'history': sessions})
    
    return jsonify({'error': 'Failed to load chat history'}), 500

@bp.route('/api/chat/<chat_id>', methods=['GET'])
@login_required
def get_chat(chat_id):
    """Get specific chat conversation"""
    from .auth_service import auth_service
    
    messages, status = auth_service.get_chat_messages(chat_id)
    
    if status == 200:
        return jsonify({'chat_id': chat_id, 'messages': messages})
    
    return jsonify({'error': 'Failed to load chat'}), 500

@bp.route('/api/chat/<chat_id>', methods=['DELETE'])
@login_required
def delete_chat(chat_id):
    """Delete a chat session"""
    from .auth_service import auth_service
    
    result, status = auth_service.delete_chat_session(chat_id)
    return jsonify(result), status

@bp.route('/api/chat/<chat_id>/title', methods=['PUT'])
@login_required
def update_chat_title(chat_id):
    """Update chat session title"""
    from .auth_service import auth_service
    
    data = request.get_json()
    title = data.get('title', '')
    
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    
    result, status = auth_service.update_chat_session_title(chat_id, title)
    return jsonify(result), status

@bp.route('/api/search', methods=['POST'])
@login_required
def search_documents():
    """Search for relevant documents using the vectorstore"""
    from .rag_service import is_allowed, smart_retrieve
    
    data = request.get_json()
    query = data.get('query', '')
    
    if not is_allowed(query):
        return jsonify({'error': 'Sorry, I can\'t assist with that.'}), 400
    
    vectorstore = current_app.config.get('RAG_VECTORSTORE')
    
    if vectorstore is None:
        return jsonify({'error': 'Search system unavailable'}), 503
    
    try:
        # Use smart retrieval
        docs = smart_retrieve(query, vectorstore)
        
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