import os
import sqlite3
import pandas as pd

# Nama file database dan CSV
DB_FILE = 'anime_recommendation.db'
ANIME_CSV = '../dataset/df_anime.csv'
USERS_CSV = '../dataset/df_ratings.csv'

def create_tables():
    """Create tables in the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Tabel anime
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anime (
            anime_id INTEGER PRIMARY KEY,
            name TEXT,
            english_name TEXT,
            genres TEXT,
            studios TEXT,
            image_url TEXT,
            content TEXT,
            content_prep TEXT
        );
    """)

    # Tabel users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT UNIQUE
        );
    """)

    # Tabel ratings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id INTEGER,
            anime_id INTEGER,
            rating INTEGER,
            PRIMARY KEY (user_id, anime_id),
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (anime_id) REFERENCES anime (anime_id)
        );
    """)

    # Tabel genres
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS genres (
            genre_id INTEGER PRIMARY KEY AUTOINCREMENT,
            genre_name TEXT UNIQUE
        );
    """)

    # Tabel user_genres
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_genres (
            user_id INTEGER,
            genre_id INTEGER,
            PRIMARY KEY (user_id, genre_id),
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (genre_id) REFERENCES genres (genre_id)
        );
    """)

    conn.commit()
    conn.close()

def import_anime_data():
    """Import anime data from CSV file into the database."""
    conn = sqlite3.connect(DB_FILE)
    df_anime = pd.read_csv(ANIME_CSV)

    # Menyimpan data ke tabel 'anime'
    df_anime.to_sql('anime', conn, if_exists='replace', index=False)
    conn.close()

def import_users_and_ratings():
    """Import users and ratings data from CSV file into the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Membaca data dari users.csv
    df_users = pd.read_csv(USERS_CSV)

    # Menyimpan data pengguna ke tabel 'users'
    df_users_unique = df_users[['user_id', 'username']].drop_duplicates()
    for index, row in df_users_unique.iterrows():
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (row['user_id'], row['username']))

    # Menyimpan rating ke tabel 'ratings'
    df_ratings = df_users[['user_id', 'anime_id', 'rating']].drop_duplicates()
    df_ratings.to_sql('ratings', conn, if_exists='append', index=False)

    conn.commit()
    conn.close()

def add_genres():
    """Add predefined genres to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Contoh daftar genre, bisa diambil dari data atau ditambahkan manual
    genres = ["Adventure", "Avant Garde", "Award Winning", "Comedy", "Drama", 
              "Fantasy", "Gourmet", "Horror", "Mystery", "Romance", "Sci-Fi", 
              "Slice of Life", "Sports", "Supernatural", "Suspense", "Action"]
    for genre in genres:
        cursor.execute("INSERT OR IGNORE INTO genres (genre_name) VALUES (?)", (genre,))
    conn.commit()
    conn.close()

def add_user(username):
    """Add a new user to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
    conn.commit()
    conn.close()

def add_user_genres(user_id, genres):
    """Add preferred genres for a user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Ambil genre_id berdasarkan nama genre
    cursor.execute("SELECT genre_id FROM genres WHERE genre_name IN ({})".format(','.join(['?']*len(genres))), genres)
    genre_ids = [row[0] for row in cursor.fetchall()]

    for genre_id in genre_ids:
        cursor.execute("INSERT INTO user_genres (user_id, genre_id) VALUES (?, ?)", (user_id, genre_id))

    conn.commit()
    conn.close()

def check_data():
    """Check and print data from the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Cek data di tabel 'users'
    cursor.execute("SELECT * FROM users LIMIT 5")
    users = cursor.fetchall()
    print("Users:")
    for user in users:
        print(user)

    # Cek data di tabel 'ratings'
    cursor.execute("SELECT * FROM ratings LIMIT 5")
    ratings = cursor.fetchall()
    print("\nRatings:")
    for rating in ratings:
        print(rating)

    conn.close()

# Menjalankan fungsi untuk pembuatan dan pengisian database
create_tables()
import_anime_data()
import_users_and_ratings()
add_genres()

# Contoh penggunaan fungsi untuk menambah data pengguna dan genre
# add_user('User1')
# add_user_genres(1, ['Action', 'Comedy', 'Drama'])  # Contoh user_id = 1, genres = ['Action', 'Comedy', 'Drama']

# Memeriksa data di database
check_data()
