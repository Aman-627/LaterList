# LaterList - Your Private Media Sanctuary

<p align="center">
  <img src="https://i.imgur.com/your-app-demo.gif" alt="LaterList App Demo"/>
</p>

**LaterList** is a full-stack web application designed to be your personal, private space for saving media you want to get to later. Instead of a dozen open tabs or scattered notes, you can save movies, songs, books, and bookmarks all in one place. The app features a sleek, modern interface and is powered by an AI recommendation engine to help you discover your next favorite thing.

**[Live Demo](https://laterlist-m513.onrender.com/)** 
---

## ✨ Features

* **Secure User Authentication**: Full registration, login, and password management system with secure password hashing.
* **Multi-Category Lists**: Save and manage four distinct types of media:
    * 🎬 **Movies**: Fetches details and poster art automatically from The Movie Database (TMDb).
    * 🎵 **Songs**: Fetches details and album art from the Spotify API.
    * 📚 **Books**: Manually add books you want to read.
    * 🔖 **Bookmarks**: Save any URL with a title for later.
* **Sleek & Responsive UI**: A beautiful dark-mode interface built with **Tailwind CSS** and Jinja2 templates, designed to work flawlessly on desktop and mobile.
* **Dynamic Dashboard**: Add, delete, and manage items on your dashboard without full page reloads, thanks to client-side JavaScript and `fetch` API calls.


---

## 🛠️ Tech Stack

This project uses a modern set of tools and technologies:

| Category      | Technologies                                                                                                                                                                                                                                                                                                                           |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Backend** | <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/> <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask"/> <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/> |
| **Frontend** | <img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" alt="JavaScript"/> <img src="https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white" alt="HTML5"/> <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind CSS"/> |
| **APIs** | <img src="https://img.shields.io/badge/Groq-000000?style=for-the-badge&logo=groq&logoColor=white" alt="Groq"/> <img src="https://img.shields.io/badge/TMDb-01B4E4?style=for-the-badge&logo=themoviedatabase&logoColor=white" alt="TMDb"/> <img src="https://img.shields.io/badge/Spotify-1ED760?style=for-the-badge&logo=spotify&logoColor=white" alt="Spotify"/> |
| **Deployment**| <img src="https://img.shields.io/badge/Render-46E3B7?style=for-the-badge&logo=render&logoColor=white" alt="Render"/> 
---

## ⚙️ Setup and Installation

Follow these steps to get the application running locally on your machine.

### 1. Prerequisites

* **Python 3.9+**
* **PostgreSQL** installed and running.
* **Git** for cloning the repository.

### 2. Clone the Repository

```bash
git clone https://github.com/Amankalyankar/LaterList.git
cd laterlist
```
### 3. Set Up a Virtual Environment
```
# Create a virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 4. Install Dependencies
Create a requirements.txt file with the following content:

* Flask
* psycopg2-binary
* werkzeug
* requests
* python-dotenv
* groq

Then, install the packages with :

```
pip install -r requirements.txt

```
### 5. Database Setup
Connect to your PostgreSQL instance and run the following SQL commands to create the necessary database and tables.
```
-- 1. Create the database
CREATE DATABASE laterlist_db;

-- 2. Connect to the new database and run the following table creation scripts:

-- Users Table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE
);

-- Movies Table
CREATE TABLE movies (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    tmdb_id INTEGER,
    poster_path VARCHAR(255),
    overview TEXT,
    release_date VARCHAR(50),
    exclude_from_recs BOOLEAN DEFAULT FALSE,
    added_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Songs Table
CREATE TABLE songs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    artist VARCHAR(255),
    spotify_id VARCHAR(100),
    album_art_url VARCHAR(255),
    spotify_link VARCHAR(255),
    exclude_from_recs BOOLEAN DEFAULT FALSE,
    added_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Bookmarks Table
CREATE TABLE bookmarks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    added_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Books Table
CREATE TABLE books (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    author VARCHAR(255),
    added_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```
### 6. Environment Variables
Create a file named .env in the root of the project. Copy the contents below and fill in your own credentials.

```
# Flask Configuration
FLASK_SECRET_KEY='your_super_secret_flask_key_here'

# Database URL
# Format: postgresql://<user>:<password>@<host>:<port>/<database_name>
DATABASE_URL="postgresql://postgres:mysecretpassword@localhost:5432/laterlist_db"

# API Keys
GROQ_API_KEY="your_groq_api_key"
TMDB_API_KEY="your_tmdb_api_key"
SPOTIFY_CLIENT_ID="your_spotify_client_id"
SPOTIFY_CLIENT_SECRET="your_spotify_client_secret"

# Spotify settings (optional, but recommended)
SPOTIFY_MARKET="US"
Where to get API Keys:
Groq: GroqCloud Console

TMDb: The Movie Database API

Spotify: Spotify for Developers Dashboard
```
### 7. Run the Application
Bash
```
flask run

```

The application should now be running at http://127.0.0.1:5000.

