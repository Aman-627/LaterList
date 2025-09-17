from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import random
import os
from dotenv import load_dotenv
import json
from groq import Groq

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'a_very_secret_and_random_fallback_key_for_dev_only')

# --- API Configurations ---
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
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
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        return conn
    except psycopg2.OperationalError as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return None

def get_spotify_token():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("Spotify credentials are not configured.")
        return None
    auth_url = 'https://accounts.spotify.com/api/token'
    response = requests.post(auth_url, {
        'grant_type': 'client_credentials',
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret': SPOTIFY_CLIENT_SECRET,
    })
    if response.status_code != 200:
        print(f"Failed to get Spotify token: {response.text}")
        return None
    return response.json().get('access_token')

def get_ai_generated_link(title, category):
    encoded_title = requests.utils.quote(title)
    if category == 'books':
        return f"https://www.google.com/search?q={encoded_title}+book"
    return f"https://www.google.com/search?q={encoded_title}"

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route('/home')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user_data = {}
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return render_template('index.html', data={}, username=session.get('username'))
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        for section in VALID_SECTIONS:
            if section == 'songs':
                cursor.execute(f"SELECT id, title, link, album_art_url FROM {section} WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
            else:
                 cursor.execute(f"SELECT id, title, link FROM {section} WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
            user_data[section] = cursor.fetchall()
    except psycopg2.Error as e:
        flash(f"Error fetching data: {e}", "error")
    finally:
        if conn:
            cursor.close()
            conn.close()
    return render_template('index.html', data=user_data, username=session.get('username'))

@app.route('/api/add_item', methods=['POST'])
def api_add_item():
    if 'user_id' not in session: return jsonify({'status': 'error', 'message': 'Authentication required.'}), 401
    data = request.get_json()
    section, title = data.get('section'), data.get('title')
    if not all([section, title]) or section not in VALID_SECTIONS: return jsonify({'status': 'error', 'message': 'Title and a valid Category are required.'}), 400
    conn = get_db_connection()
    if not conn: return jsonify({'status': 'error', 'message': 'Database connection failed.'}), 500
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if section == 'movies':
            search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={requests.utils.quote(title)}"
            search_res = requests.get(search_url).json()
            best_match = next((item for item in search_res.get('results', []) if item.get('media_type') in ['movie', 'tv']), None)
            if not best_match: return jsonify({'status': 'error', 'message': f"Could not find '{title}'."}), 404
            tmdb_id, media_type = best_match.get('id'), best_match.get('media_type')
            item_title = best_match.get('title') or best_match.get('name')
            link = f"https://www.themoviedb.org/{media_type}/{tmdb_id}"
            query = "INSERT INTO movies (user_id, title, link, tmdb_id, media_type) VALUES (%s, %s, %s, %s, %s) RETURNING id"
            cursor.execute(query, (session['user_id'], item_title, link, tmdb_id, media_type))
            item = {'id': cursor.fetchone()['id'], 'title': item_title, 'link': link, 'section': section}
            conn.commit()
            return jsonify({'status': 'success', 'message': f"Added '{item_title}'.", 'item': item})

        elif section == 'songs':
            token = get_spotify_token()
            if not token: return jsonify({'status': 'error', 'message': 'Spotify auth failed.'}), 500
            search_url = f"https://api.spotify.com/v1/search?q={requests.utils.quote(title)}&type=track&limit=1"
            headers = {"Authorization": f"Bearer {token}"}
            search_res = requests.get(search_url, headers=headers).json()
            tracks = search_res.get('tracks', {}).get('items', [])
            if not tracks: return jsonify({'status': 'error', 'message': f"Could not find '{title}' on Spotify."}), 404
            best_match = tracks[0]
            spotify_id, song_name = best_match.get('id'), best_match.get('name')
            artist_name = best_match.get('artists', [{}])[0].get('name', 'Unknown Artist')
            album_art_url = best_match.get('album', {}).get('images', [{}])[0].get('url')
            link = best_match.get('external_urls', {}).get('spotify')
            item_title = f"{song_name} by {artist_name}"
            query = "INSERT INTO songs (user_id, title, link, spotify_id, album_art_url) VALUES (%s, %s, %s, %s, %s) RETURNING id"
            cursor.execute(query, (session['user_id'], item_title, link, spotify_id, album_art_url))
            item = {'id': cursor.fetchone()['id'], 'title': item_title, 'link': link, 'section': section, 'album_art_url': album_art_url}
            conn.commit()
            return jsonify({'status': 'success', 'message': f"Added '{item_title}'.", 'item': item})

        else: # books, bookmarks
            link = get_ai_generated_link(title, section)
            query = f"INSERT INTO {section} (user_id, title, link) VALUES (%s, %s, %s) RETURNING id"
            cursor.execute(query, (session['user_id'], title, link))
            item = {'id': cursor.fetchone()['id'], 'title': title, 'link': link, 'section': section}
            conn.commit()
            return jsonify({'status': 'success', 'message': f"Added '{title}'.", 'item': item})

    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': f'Database error: {e}'}), 500
    finally:
        if conn:
            cursor.close()
            conn.close()

@app.route('/api/delete_item/<section>/<int:item_id>', methods=['POST'])
def api_delete_item(section, item_id):
    if 'user_id' not in session: return jsonify({'status': 'error', 'message': 'Auth required.'}), 401
    if section not in VALID_SECTIONS: return jsonify({'status': 'error', 'message': 'Invalid section.'}), 400
    conn = get_db_connection()
    if not conn: return jsonify({'status': 'error', 'message': 'DB connection failed.'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {section} WHERE id = %s AND user_id = %s", (item_id, session['user_id']))
        conn.commit()
        if cursor.rowcount == 0: return jsonify({'status': 'error', 'message': 'Item not found.'}), 404
    except psycopg2.Error as e:
        return jsonify({'status': 'error', 'message': f'DB error: {e}'}), 500
    finally:
        if conn:
            cursor.close()
            conn.close()
    return jsonify({'status': 'success', 'message': 'Item deleted.'})

@app.route('/api/recommend/<category>', methods=['POST'])
def api_get_recommendation(category):
    if 'user_id' not in session: return jsonify({'status': 'error', 'message': 'Auth required.'}), 401
    if category not in ['movies', 'songs', 'books']: return jsonify({'status': 'error', 'message': 'Invalid category.'}), 400
    
    data = request.get_json()
    all_excluded_titles = list(set(data.get('disliked_items', []) + data.get('excluded_from_recs', [])))
    conn = get_db_connection()
    if not conn: return jsonify({'status': 'error', 'message': 'DB connection failed.'}), 500

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if category == 'movies':
            cursor.execute("SELECT title, tmdb_id, media_type FROM movies WHERE user_id = %s AND tmdb_id IS NOT NULL", (session['user_id'],))
            all_items = cursor.fetchall()
            eligible_items = [item for item in all_items if item['title'] not in all_excluded_titles]
            if not eligible_items: return jsonify({'status': 'error', 'message': "All items are excluded."}), 400
            base_item = random.choice(eligible_items)
            based_on_title, tmdb_id, media_type = base_item['title'], base_item['tmdb_id'], base_item['media_type']
            rec_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/recommendations?api_key={TMDB_API_KEY}"
            rec_res = requests.get(rec_url).json()
            if not rec_res.get('results'): return jsonify({'status': 'error', 'message': f'No recommendations for "{based_on_title}".'}), 404
            final_recs = [rec for rec in rec_res['results'] if (rec.get('title') or rec.get('name')) not in all_excluded_titles]
            rec_list = [{'title': item.get('title') or item.get('name'), 'link': f"https://www.themoviedb.org/{item.get('media_type', media_type)}/{item.get('id')}", 'reason': f"Because you liked {based_on_title}"} for item in final_recs[:5]]
            return jsonify({'status': 'success', 'recommendations': {'results': rec_list, 'based_on': based_on_title, 'section': category}})

        elif category == 'songs':
            cursor.execute("SELECT spotify_id, title FROM songs WHERE user_id = %s AND spotify_id IS NOT NULL", (session['user_id'],))
            all_items = cursor.fetchall()
            if not all_items:
                return jsonify({'status': 'error', 'message': "Add some songs to get a recommendation!"}), 400
            eligible_items = [item for item in all_items if item['title'] not in all_excluded_titles]
            if not eligible_items:
                return jsonify({'status': 'error', 'message': "All songs are excluded."}), 400
            base_item = random.choice(eligible_items)
            spotify_id, based_on_title = base_item['spotify_id'], base_item['title']

    # Validate spotify_id exists and is not empty
            if not spotify_id:
                return jsonify({'status': 'error', 'message': f'No valid Spotify ID for "{based_on_title}".'}), 400

            token = get_spotify_token()
            if not token:
                return jsonify({'status': 'error', 'message': 'Spotify auth failed.'}), 500

    # Use the correct Spotify recommendations API URL
            rec_url = f"https://api.spotify.com/v1/recommendations?seed_tracks={spotify_id}&limit=5"
            headers = {"Authorization": f"Bearer {token}"}
    
            print(f"Requesting recommendations for spotify_id: {spotify_id}")
            print(f"Request URL: {rec_url}")
    
            resp = requests.get(rec_url, headers=headers)

    # Debug logging
            print(f"Spotify recommendations response: {resp.status_code}")
            if resp.status_code != 200:
                print(f"Error response: {resp.text[:500]}")

            if resp.status_code == 400:
                return jsonify({'status': 'error', 'message': f'Invalid Spotify track ID for "{based_on_title}". Try re-adding the song.'}), 400
            elif resp.status_code != 200:
                return jsonify({'status': 'error', 'message': f"Spotify API error {resp.status_code}: {resp.text}"}), 500

            try:
                rec_res = resp.json()
            except Exception as e:
                return jsonify({'status': 'error', 'message': f"Invalid JSON from Spotify: {e}"}), 500

            if not rec_res.get('tracks'):
                return jsonify({'status': 'error', 'message': f'No recommendations available for "{based_on_title}".'}), 404

            rec_list = []
            for track in rec_res['tracks']:
                track_title = f"{track.get('name')} by {track.get('artists', [{}])[0].get('name', 'Unknown')}"
                link = track.get('external_urls', {}).get('spotify')
                if link:  # Only add tracks with valid Spotify links
                    rec_list.append({'title': track_title, 'link': link, 'reason': f"Because you liked {based_on_title}"})

                if not rec_list:
                    return jsonify({'status': 'error', 'message': f'No valid recommendations found for "{based_on_title}".'}), 404

            return jsonify({'status': 'success', 'recommendations': {'results': rec_list, 'based_on': based_on_title, 'section': category}})

        else: # books
            cursor.execute(f"SELECT title FROM {category} WHERE user_id = %s", (session['user_id'],))
            items = cursor.fetchall()
            if not items: return jsonify({'status': 'error', 'message': f"Add some {category} to get a recommendation!"}), 400
            if not groq_client: return jsonify({'status': 'error', 'message': "AI engine not configured."}), 500
            item_titles = [item['title'] for item in items]
            eligible_items = [title for title in item_titles if title not in all_excluded_titles]
            if not eligible_items: return jsonify({'status': 'error', 'message': f"All {category} are excluded."}), 400
            based_on_item = random.choice(eligible_items)
            system_prompt = "You are a recommendation assistant. Respond with a single JSON object: {'recommendations': [...]}. Each item must have 'title', 'author', and 'reason' keys."
            prompt = f"A user likes these books: {', '.join(eligible_items)}. Do not recommend any of these: {', '.join(all_excluded_titles)}. Recommend 3 new books."
            try:
                chat_completion = groq_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}], model="gemma2-9b-it", temperature=0.7, response_format={"type": "json_object"})
                rec_data = json.loads(chat_completion.choices[0].message.content).get('recommendations', [])
                rec_list = [{'title': f"{item.get('title', 'Unknown')} by {item.get('author', 'Unknown')}", 'link': get_ai_generated_link(f"{item.get('title', '')} {item.get('author', '')}", 'books'), 'reason': item.get('reason', '')} for item in rec_data]
                return jsonify({'status': 'success', 'recommendations': {'results': rec_list, 'based_on': based_on_item, 'section': category}})
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'AI error: {e}'}), 500
    finally:
        if conn:
            cursor.close()
            conn.close()

# --- All other routes (generate_ideas, auth, admin) unchanged ---
@app.route('/generate_ideas', methods=['POST'])
def generate_ideas():
    if not groq_client:
        return jsonify({'error': 'AI suggestion engine is not configured.'}), 500
    data = request.get_json()
    user_prompt = data.get('prompt')
    if not user_prompt:
        return jsonify({'error': 'No prompt provided.'}), 400

    creative_phrases = [
        "Give me some fresh and unique ideas.",
        "Surprise me with your suggestions.",
        "Suggest something unexpected.",
        "I'm looking for hidden gems.",
        "What would you recommend for this mood?"
    ]
    random_phrase = random.choice(creative_phrases)

    full_prompt = f"You are a media suggestion assistant. Based on the user's mood or request, suggest 3 media items (movie, book, or song). {random_phrase} Respond with a single, raw JSON object with a single key 'suggestions' which contains an array of 3 items. Each item must have 'title', 'category', and 'reason' keys. User request: \"{user_prompt}\""

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a media suggestion assistant. You only respond with a single JSON object containing 'suggestions' array."},
                {"role": "user", "content": full_prompt}
            ],
            model="gemma2-9b-it",
            temperature=0.7, 
            response_format={"type": "json_object"},
        )
        
        response_text = chat_completion.choices[0].message.content.strip()
        return jsonify(json.loads(response_text).get('suggestions', []))
    except Exception as e:
        print(f"Error during Groq idea generation: {e}")
        return jsonify({'error': 'Could not get suggestions from the AI.'}), 500

# --- Admin, login, register, change_password, logout, health routes remain unchanged ---
@app.route('/admin')  
def admin_view():
    if 'user_id' not in session or session.get('username') != 'DuniyaKaPapa':
        flash("You do not have permission to access this page.", "error")
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return render_template('admin.html', data={})
        
    all_data = {}
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        for section in VALID_SECTIONS:
            query = f"""
                SELECT i.id, i.title, i.link, u.username 
                FROM {section} AS i 
                JOIN users AS u ON i.user_id = u.id 
                ORDER BY u.username, i.id DESC
            """
            cursor.execute(query)
            all_data[section] = cursor.fetchall()
    except psycopg2.Error as e:
        flash(f"Error fetching admin data: {e}", "error")
    finally:
        cursor.close()
        conn.close()
            
    return render_template('admin.html', data=all_data)

@app.route('/admin/delete/<section>/<int:item_id>', methods=['POST'])
def admin_delete_item(section, item_id):
    if 'user_id' not in session or session.get('username') != 'DuniyaKaPapa':
        flash("You do not have permission to perform this action.", "error")
        return redirect(url_for('admin_view'))
        
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for('admin_view'))
        
    try:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {section} WHERE id = %s", (item_id,))
        conn.commit()
        if cursor.rowcount > 0:
            flash("Item deleted successfully.", "success")
        else:
            flash("Item not found.", "warning")
    except psycopg2.Error as e:
        flash(f"Error deleting item: {e}", "error")
    finally:
        cursor.close()
        conn.close()
            
    return redirect(url_for('admin_view'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "error")
            return render_template('login.html')
        
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                session['user_id'], session['username'] = user['id'], user['username']
                flash('Logged in successfully!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Incorrect username or password, please try again.', 'error')
        except psycopg2.Error as e:
            flash(f"An error occurred: {e}", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username, password = request.form['username'].strip(), request.form['password'].strip()
        if not username or not password:
            flash("Username and password are required.", "warning")
            return render_template('register.html', username=username)
            
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "error")
            return render_template('register.html', username=username)

        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                flash("Username already exists. Please choose another.", "warning")
                return render_template('register.html', username=username)
            
            hashed_password = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s) RETURNING id",
                (username, hashed_password)
            )
            new_user = cursor.fetchone()
            conn.commit()
            
            session['user_id'], session['username'] = new_user['id'], username
            flash("Registration successful! Welcome.", "success")
            return redirect(url_for('index'))
        except psycopg2.Error as e:
            flash(f"An error occurred during registration: {e}", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required.', 'warning')
            return redirect(url_for('change_password'))

        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('change_password'))

        user_id = session['user_id']
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('change_password'))

        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

            if not user or not check_password_hash(user['password'], current_password):
                flash('Incorrect current password.', 'error')
                return redirect(url_for('change_password'))

            hashed_password = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
            conn.commit()
            flash('Your password has been updated successfully.', 'success')
            return redirect(url_for('index'))

        except psycopg2.Error as e:
            flash(f'An error occurred: {e}', 'error')
        finally:
            cursor.close()
            conn.close()

    return render_template('change_password.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('landing'))

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)