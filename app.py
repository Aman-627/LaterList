from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import random
import os
from dotenv import load_dotenv
import json
from groq import Groq

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'a_very_secret_and_random_fallback_key_for_dev_only')

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_DATABASE', 'media_hub'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
}

# --- API Configurations ---
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
VALID_SECTIONS = ['movies', 'songs', 'bookmarks', 'books']

# --- API Clients ---
groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        print("Groq client initialized successfully.")
    except Exception as e:
        print(f"Could not initialize Groq client: {e}")


def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def get_ai_generated_link(title, category):
    if not groq_client: return f"https://www.google.com/search?q={requests.utils.quote(f'{title} {category}')}"
    service_map = {'songs': 'Spotify, YouTube Music, or Apple Music', 'movies': 'IMDb, Rotten Tomatoes, or Letterboxd', 'books': 'Goodreads, Google Books, or Amazon'}
    service_suggestion = service_map.get(category, 'a relevant website')
    prompt = f"Generate a single, direct URL for the {category.rstrip('s')} titled '{title}'. The user wants a link to {service_suggestion}. Respond with ONLY the URL and nothing else."
    try:
        chat_completion = groq_client.chat.completions.create(messages=[{"role": "system", "content": "You are a URL generation assistant. You only respond with a single, valid, direct URL."}, {"role": "user", "content": prompt}], model="llama3-8b-8192", temperature=0.2)
        url = chat_completion.choices[0].message.content.strip()
        if url.startswith("http://") or url.startswith("https://"): return url
    except Exception as e: print(f"Error generating link via AI for '{title}': {e}")
    return f"https://www.google.com/search?q={requests.utils.quote(f'{title} {category}')}"


@app.route("/")
def landing(): return render_template("landing.html")

@app.route('/home')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id, user_data, conn = session['user_id'], {}, get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return render_template('index.html', data={}, username=session.get('username'))
    cursor = conn.cursor(dictionary=True)
    for section in VALID_SECTIONS:
        cursor.execute(f"SELECT id, title, link FROM {section} WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        user_data[section] = cursor.fetchall()
    cursor.close(), conn.close()
    return render_template('index.html', data=user_data, username=session.get('username'))

@app.route('/api/add_item', methods=['POST'])
def api_add_item():
    if 'user_id' not in session: return jsonify({'status': 'error', 'message': 'Authentication required.'}), 401
    data = request.get_json()
    section, title, link = data.get('section'), data.get('title'), data.get('link')
    if not all([section, title]) or section not in VALID_SECTIONS: return jsonify({'status': 'error', 'message': 'Title and Category are required.'}), 400
    if not link: link = get_ai_generated_link(title, section)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = f"INSERT INTO {section} (user_id, title, link) VALUES (%s, %s, %s)"
    cursor.execute(query, (session['user_id'], title, link))
    new_id = cursor.lastrowid
    conn.commit(), cursor.close(), conn.close()
    return jsonify({'status': 'success', 'message': f"Added '{title}' to {section}.", 'item': {'id': new_id, 'title': title, 'link': link, 'section': section}})

@app.route('/api/delete_item/<section>/<int:item_id>', methods=['POST'])
def api_delete_item(section, item_id):
    if 'user_id' not in session: return jsonify({'status': 'error', 'message': 'Authentication required.'}), 401
    if section not in VALID_SECTIONS: return jsonify({'status': 'error', 'message': 'Invalid section.'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    query = f"DELETE FROM {section} WHERE id = %s AND user_id = %s"
    cursor.execute(query, (item_id, session['user_id']))
    conn.commit()
    if cursor.rowcount == 0:
        cursor.close(), conn.close()
        return jsonify({'status': 'error', 'message': 'Item not found or permission denied.'}), 404
    cursor.close(), conn.close()
    return jsonify({'status': 'success', 'message': 'Item deleted.'})

@app.route('/api/recommend/<category>', methods=['POST'])
def api_get_recommendation(category):
    if 'user_id' not in session: return jsonify({'status': 'error', 'message': 'Authentication required.'}), 401
    if category not in ['movies', 'songs', 'books']: return jsonify({'status': 'error', 'message': 'Invalid recommendation category.'}), 400
    if not groq_client: return jsonify({'status': 'error', 'message': f"Groq API key is not configured."}), 500
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT title FROM {category} WHERE user_id = %s", (session['user_id'],))
    items = cursor.fetchall()
    cursor.close(), conn.close()
    
    if not items: return jsonify({'status': 'error', 'message': f"Add some {category} to get a recommendation!"}), 400
    
    item_titles = [item['title'] for item in items]
    data = request.get_json()
    artist_preference = data.get('artist_preference')
    disliked_items = data.get('disliked_items', [])
    excluded_from_recs = data.get('excluded_from_recs', []) 
    
    # Combine disliked and explicitly excluded items
    all_excluded_items = list(set(disliked_items + excluded_from_recs))
    
    # Filter out excluded items from the list of items the user "likes" for "based_on" selection
    eligible_items = [title for title in item_titles if title not in all_excluded_items]

    if not eligible_items:
        return jsonify({'status': 'error', 'message': f"All your {category} are marked for exclusion. Add more or uncheck some to get recommendations."}), 400

    # Select a random item from the *eligible* items for the "based_on" display
    based_on_item = random.choice(eligible_items)
    
    system_prompt = "You are a helpful recommendation assistant. You will be given a list of items a user likes and you must recommend new items of the same category. You must respond with a single JSON object. The JSON object must have a single key named 'recommendations' which contains an array of the recommended items."
    
    prompt = f"A user likes these {', '.join(eligible_items)}. " # Only use eligible items for the AI's "likes"
    if all_excluded_items: prompt += f"Do not recommend any of these items: {', '.join(all_excluded_items)}. "
    
    if category == 'songs':
        prompt += f"The user wants songs by or very similar to the artist: '{artist_preference}'. " if artist_preference else "The user has not specified a particular artist. "
        prompt += f"Recommend 5 songs. Do not recommend any from the user's existing list. Each object in the 'recommendations' array should have 'song_name' and 'artist' keys."
    else:
        item_type = 'movie' if category == 'movies' else 'book'
        creator_key = 'director' if category == 'movies' else 'author'
        prompt += f"Recommend 3 new {item_type}s the user would enjoy. Do not recommend any from the list. Each object in the 'recommendations' array should have 'title', '{creator_key}', and 'reason' keys."

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            model="llama3-8b-8192",
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        
        rec_data = json.loads(chat_completion.choices[0].message.content).get('recommendations', [])
        rec_list = []
        
        if category == 'songs':
            for s in rec_data:
                if s.get("song_name") and s.get("artist"):
                    full_title = f"{s['song_name']} by {s['artist']}"
                    link = get_ai_generated_link(full_title, 'songs')
                    rec_list.append({'title': full_title, 'link': link, 'reason': ''})
        else: 
            creator_key = 'director' if category == 'movies' else 'author'
            for item in rec_data:
                creator = item.get(creator_key, "")
                title = item.get('title', 'Unknown Title')
                full_title = f"{title} by {creator}" if creator else title
                link = get_ai_generated_link(full_title, category)
                rec_list.append({'title': full_title, 'link': link, 'reason': item.get('reason', '')})
        
        return jsonify({'status': 'success', 'recommendations': {'results': rec_list, 'based_on': based_on_item, 'section': category}})
    except Exception as e:
        print(f"Error during recommendation: {e}")
        return jsonify({'status': 'error', 'message': 'Could not get a recommendation from the AI.'}), 500

@app.route('/generate_ideas', methods=['POST'])
def generate_ideas():
    # Now uses Groq client instead of Gemini
    if not groq_client: return jsonify({'error': 'Groq API key not configured.'}), 500
    data = request.get_json()
    user_prompt = data.get('prompt')
    if not user_prompt: return jsonify({'error': 'No prompt provided.'}), 400
    
    full_prompt = f"You are a media suggestion assistant. Based on the user's mood or request, suggest 3 media items (movie, book, or song). Respond with a single, raw JSON object with a single key 'suggestions' which contains an array of 3 items. Each item must have 'title', 'category', and 'reason' keys. User request: \"{user_prompt}\""
    
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a media suggestion assistant. You only respond with a single JSON object containing 'suggestions' array."},
                {"role": "user", "content": full_prompt}
            ],
            model="llama3-8b-8192", # You can choose a different Groq model if preferred
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        
        response_text = chat_completion.choices[0].message.content.strip()
        return jsonify(json.loads(response_text).get('suggestions', []))
    except Exception as e:
        print(f"Error during Groq idea generation: {e}")
        return jsonify({'error': 'Could not get suggestions from the AI.'}), 500

@app.route('/admin')
def admin_view():
    if 'user_id' not in session or session.get('username') != 'DuniyaKaPapa':
        flash("You do not have permission to access this page.", "error")
        return redirect(url_for('index'))
    conn = get_db_connection()
    if not conn: return render_template('admin.html', data={})
    cursor, all_data = conn.cursor(dictionary=True), {}
    for section in VALID_SECTIONS:
        cursor.execute(f"SELECT i.id, i.title, i.link, u.username FROM {section} AS i JOIN users AS u ON i.user_id = u.id ORDER BY u.username, i.id DESC")
        all_data[section] = cursor.fetchall()
    cursor.close(), conn.close()
    return render_template('admin.html', data=all_data)

@app.route('/admin/delete/<section>/<int:item_id>', methods=['POST'])
def admin_delete_item(section, item_id):
    if 'user_id' not in session or session.get('username') != 'DuniyaKaPapa':
        flash("You do not have permission to perform this action.", "error")
        return redirect(url_for('admin_view'))
    conn, cursor = get_db_connection(), conn.cursor()
    cursor.execute(f"DELETE FROM {section} WHERE id = %s", (item_id,))
    conn.commit()
    flash("Item deleted successfully." if cursor.rowcount > 0 else "Item not found.", "success" if cursor.rowcount > 0 else "warning")
    cursor.close(), conn.close()
    return redirect(url_for('admin_view'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "error")
            return render_template('login.html')
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'], session['username'] = user['id'], user['username']
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Incorrect password, please try again.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username, password = request.form['username'].strip(), request.form['password'].strip()
        if not username or not password:
            flash("Username and password are required.", "warning")
            return redirect(url_for('register'))
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "error")
            return redirect(url_for('register'))
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            flash("Username already exists. Please choose another.", "warning")
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
        conn.commit()
        session['user_id'], session['username'] = cursor.lastrowid, username
        flash("Registration successful! Welcome.", "success")
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('landing'))

if __name__ == "__main__": app.run(debug=True)