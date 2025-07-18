from flask import Flask, render_template, request, redirect, session, url_for, flash
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import random
import base64
import os # Import the os module
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file (for local development)
# This line should be at the very top, after imports
load_dotenv()

app = Flask(__name__)
# Get the secret key from an environment variable, with a fallback for development
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'a_very_secret_and_random_fallback_key_for_dev_only')

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'), # Get DB host from environment variable
    'database': os.getenv('DB_DATABASE', 'media_hub'), # Get DB name from environment variable
    'user': os.getenv('DB_USER', 'root'), # Get DB user from environment variable
    'password': os.getenv('DB_PASSWORD', ''), # Get DB password from environment variable
}

# --- API Configurations ---
GOOGLE_BOOKS_API_KEY = os.getenv('GOOGLE_BOOKS_API_KEY') # Get Google Books API key from environment variable
LASTFM_API_KEY = os.getenv('LASTFM_API_KEY') # Get Last.fm API key from environment variable

LASTFM_API_URL = 'http://ws.audioscrobbler.com/2.0/'

# --- List of valid sections in the desired display order. ---
VALID_SECTIONS = ['movies', 'songs', 'bookmarks', 'books']


def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# --- Main Routes ---
@app.route("/")
def landing():
    return render_template("landing.html", page_type='landing')

@app.route('/home')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    user_data = {}
    recommendation = session.pop('recommendation', None)
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return render_template('index.html', data={}, username=session.get('username'), recommendation=recommendation)
    cursor = conn.cursor(dictionary=True)
    for section in VALID_SECTIONS:
        cursor.execute(f"SELECT id, title, link FROM {section} WHERE user_id = %s", (user_id,))
        user_data[section] = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', data=user_data, username=session.get('username'), recommendation=recommendation)

# --- User and Item Management Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "error")
            return render_template('login.html')
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user is None:
            flash(f"Username '{username}' not found. Please register.", 'warning')
            cursor.close()
            conn.close()
            return redirect(url_for('register', username=username))
        if check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Logged in successfully!', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('index'))
        else:
            flash('Incorrect password, please try again.', 'error')
        cursor.close()
        conn.close()
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
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
            cursor.close()
            conn.close()
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
        new_user_id = cursor.lastrowid
        conn.commit()
        session['user_id'] = new_user_id
        session['username'] = username
        cursor.close()
        conn.close()
        flash("Registration successful! Welcome.", "success")
        return redirect(url_for('index'))
    username_to_prefill = request.args.get('username', '')
    return render_template('register.html', username=username_to_prefill)

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('landing'))

@app.route('/add_item', methods=['POST'])
def add_item():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    section = request.form.get('section')
    if section not in VALID_SECTIONS:
        flash("Invalid section.", "error")
        return redirect(url_for('index'))
    user_id = session['user_id']
    title = request.form.get('title')
    link = request.form.get('link')
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for('index'))
    cursor = conn.cursor()
    query = f"INSERT INTO {section} (user_id, title, link) VALUES (%s, %s, %s)"
    cursor.execute(query, (user_id, title, link))
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"Added '{title}' to {section}.", "success")
    return redirect(url_for('index'))

# --- NEW: Route to add a recommended item to the user's collection ---
@app.route('/add_recommendation', methods=['POST'])
def add_recommendation():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    title = request.form.get('title')
    section = request.form.get('section')
    
    if not title or not section:
        flash("Could not add recommendation due to missing information.", "error")
        return redirect(url_for('index'))

    if section not in VALID_SECTIONS:
        flash("Invalid section for recommendation.", "error")
        return redirect(url_for('index'))
        
    user_id = session['user_id']
    # Add with a placeholder link that the user can change later
    link = request.form.get('link') or '#'


    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for('index'))
    
    cursor = conn.cursor()
    query = f"INSERT INTO {section} (user_id, title, link) VALUES (%s, %s, %s)"
    cursor.execute(query, (user_id, title, link))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash(f"Added '{title}' to your {section}!", "success")
    return redirect(url_for('index'))

@app.route('/delete/<section>/<int:item_id>', methods=['POST'])
def delete_item(section, item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if section not in VALID_SECTIONS:
        flash("Invalid section.", "error")
        return redirect(url_for('index'))
    user_id = session['user_id']
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for('index'))
    cursor = conn.cursor()
    query = f"DELETE FROM {section} WHERE id = %s AND user_id = %s"
    cursor.execute(query, (item_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Item deleted.", "success")
    return redirect(url_for('index'))

# --- Admin Routes ---
@app.route('/admin')
def admin_view():
    if 'username' not in session or session['username'] != 'admin':
        flash("You do not have permission to view this page.", "error")
        return redirect(url_for('index'))
    all_data = {}
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)
    for section in VALID_SECTIONS:
        query = f"SELECT i.id, i.title, i.link, u.username FROM {section} i JOIN users u ON i.user_id = u.id ORDER BY u.username"
        cursor.execute(query)
        all_data[section] = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin.html', data=all_data, username=session.get('username'))

@app.route('/admin/delete/<section>/<int:item_id>', methods=['POST'])
def admin_delete_item(section, item_id):
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))
    if section not in VALID_SECTIONS:
        flash("Invalid section.", "error")
        return redirect(url_for('admin_view'))
    conn = get_db_connection()
    if not conn:
        flash("Database connection error.", "error")
        return redirect(url_for('admin_view'))
    cursor = conn.cursor()
    query = f"DELETE FROM {section} WHERE id = %s"
    cursor.execute(query, (item_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Item deleted by admin.", "success")
    return redirect(url_for('admin_view'))

# --- Recommendation Routes ---
@app.route('/recommend_song', methods=['POST'])
def recommend_song():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check if the API key is configured
    if not LASTFM_API_KEY:
        flash("Last.fm API key is not configured. Please set LASTFM_API_KEY environment variable.", "error")
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT title FROM songs WHERE user_id = %s", (session['user_id'],))
    songs = cursor.fetchall()
    cursor.close()
    conn.close()

    if not songs:
        flash("Add songs to get a recommendation!", "warning")
        return redirect(url_for('index'))

    random_song_title = random.choice(songs)['title']

    try:
        # Step 1: Search the song on Last.fm
        search_params = {
            'method': 'track.search',
            'track': random_song_title,
            'api_key': LASTFM_API_KEY,
            'format': 'json',
            'limit': 1
        }
        search_res = requests.get(LASTFM_API_URL, params=search_params)
        search_res.raise_for_status()
        search_json = search_res.json()

        trackmatches = search_json.get('results', {}).get('trackmatches', {}).get('track', [])
        if not trackmatches:
            flash(f"Could not find '{random_song_title}' on Last.fm.", "warning")
            return redirect(url_for('index'))

        found_track = trackmatches[0]
        artist_name = found_track['artist']
        track_name = found_track['name']

        # Step 2: Get similar tracks
        similar_params = {
            'method': 'track.getSimilar',
            'artist': artist_name,
            'track': track_name,
            'api_key': LASTFM_API_KEY,
            'format': 'json'
        }
        rec_res = requests.get(LASTFM_API_URL, params=similar_params)
        rec_res.raise_for_status()
        rec_json = rec_res.json()

        similar_tracks = rec_json.get('similartracks', {}).get('track', [])
        if not similar_tracks:
            flash(f"Could not find similar songs for '{track_name}'.", "warning")
            return redirect(url_for('index'))

        user_song_titles = {s['title'].lower() for s in songs}
        possible_recs = []

        for track in similar_tracks:
            formatted_title = f"{track['name']} by {track['artist']['name']}"
            if formatted_title.lower() not in user_song_titles:
                possible_recs.append(track)

        if not possible_recs:
            flash("Found recommendations, but they are already in your list!", "info")
            return redirect(url_for('index'))

        # Step 3: Pick one recommendation and build the link
        selected = random.choice(possible_recs)
        recommended_title = f"{selected['name']} by {selected['artist']['name']}"
        search_query = f"{selected['name']} {selected['artist']['name']}"
        search_encoded = requests.utils.quote(search_query)
        # Using a generic Google search link for Last.fm tracks as a placeholder
        track_url = f"https://www.google.com/search?q={search_encoded}&btnI"


        session['recommendation'] = {
            'recommended_title': recommended_title,
            'based_on': random_song_title,
            'section': 'songs',
            'link': track_url
        }

        flash("Here's a song recommendation for you!", "success")

    except requests.exceptions.RequestException as e:
        print(f"Error calling Last.fm API: {e}")
        flash("Error contacting the song recommendation service.", "error")

    return redirect(url_for('index'))
@app.route('/recommend_book', methods=['POST'])
def recommend_book():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Check if the API key is configured
    if not GOOGLE_BOOKS_API_KEY:
        flash("Google Books API key is not configured. Please set GOOGLE_BOOKS_API_KEY environment variable.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT title FROM books WHERE user_id = %s", (session['user_id'],))
    books = cursor.fetchall()
    cursor.close()
    conn.close()

    if not books:
        flash("Add books to get a recommendation!", "warning")
        return redirect(url_for('index'))

    random_book_title = random.choice(books)['title']

    try:
        # Step 1: Search for the selected book
        search_params = {
            'q': f'intitle:{random_book_title}',
            'key': GOOGLE_BOOKS_API_KEY
        }
        search_res = requests.get("https://www.googleapis.com/books/v1/volumes", params=search_params)
        search_res.raise_for_status()
        search_json = search_res.json()

        if search_json.get('totalItems', 0) == 0:
            flash(f"Could not find details for '{random_book_title}' on Google Books.", "warning")
            return redirect(url_for('index'))

        first_book = search_json['items'][0]['volumeInfo']
        category = first_book.get('categories', [None])[0]

        if not category:
            flash(f"Could not determine a category for '{random_book_title}'.", "warning")
            return redirect(url_for('index'))

        # Step 2: Get books in same category
        rec_params = {
            'q': f'subject:{category}',
            'key': GOOGLE_BOOKS_API_KEY,
            'maxResults': 20
        }
        rec_res = requests.get("https://www.googleapis.com/books/v1/volumes", params=rec_params)
        rec_res.raise_for_status()
        rec_json = rec_res.json()

        user_book_titles = {b['title'].lower() for b in books}
        possible_recs = []

        for item in rec_json.get('items', []):
            book_info = item.get('volumeInfo', {})
            title = book_info.get('title')
            if title and title.lower() not in user_book_titles and title.lower() != random_book_title.lower():
                possible_recs.append(item)

        if not possible_recs:
            flash("Found recommendations, but they are already in your list!", "info")
            return redirect(url_for('index'))

        # Step 3: Pick one and extract title and link
        recommended_item = random.choice(possible_recs)
        book_info = recommended_item.get('volumeInfo', {})
        recommended_title = book_info.get('title')
        book_link = book_info.get('infoLink', '#')

        if 'authors' in book_info:
            recommended_title += f" by {', '.join(book_info['authors'])}"

        session['recommendation'] = {
            'recommended_title': recommended_title,
            'based_on': random_book_title,
            'section': 'books',
            'link': book_link
        }

        flash("Here's a book recommendation for you!", "success")

    except requests.exceptions.RequestException as e:
        print(f"Error calling Google Books API: {e}")
        flash("Error contacting the book recommendation service.", "error")

    return redirect(url_for('index'))


if __name__ == "__main__":
    app.run(debug=True)