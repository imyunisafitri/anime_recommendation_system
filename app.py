import time
import pickle
from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import pandas as pd

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DB_FILE = 'anime_recommendation.db'

def get_db_connection():
    retries = 5
    for _ in range(retries):
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError:
            time.sleep(1)
    raise sqlite3.OperationalError("Could not connect to the database after multiple retries")

# Load models and data
with open('cf_model.pkl', 'rb') as f:
    algo_knn = pickle.load(f)
with open('cbf_cosine_sim.pkl', 'rb') as f:
    cosine_sim = pickle.load(f)
with open('df_anime.pkl', 'rb') as f:
    df_anime = pickle.load(f)
with open('predictions.pkl', 'rb') as f:
    predictions = pickle.load(f)


def get_cf_recommendations(user_id, topN=5):
    user_predictions = [pred for pred in predictions if pred.uid == user_id]
    if not user_predictions:
        return pd.DataFrame(columns=['anime_id', 'name', 'image_url'])
    user_predictions = sorted(user_predictions, key=lambda x: x.est, reverse=True)[:topN]
    result_data = []
    for pred in user_predictions:
        anime_id = pred.iid
        if anime_id not in df_anime['anime_id'].values:
            continue
        anime_data = df_anime.loc[df_anime['anime_id'] == anime_id, ['name', 'image_url']].iloc[0]
        result_data.append({'anime_id': anime_id, 'name': anime_data['name'], 'image_url': anime_data['image_url']})
    return pd.DataFrame(result_data)

def get_cbf_recommendations(anime_name, cosine_sim, topN=5):
    anime_name_lower = anime_name.lower()
    idx = df_anime.index[(df_anime['name'].str.lower() == anime_name_lower) | 
                         (df_anime['english_name'].str.lower() == anime_name_lower)].tolist()
    
    if not idx:
        return pd.DataFrame(columns=['anime_id', 'name', 'image_url'])
    
    idx = idx[0]
    sim_scores = list(enumerate(cosine_sim[idx]))
    sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
    sim_scores = sim_scores[1:topN+1]
    anime_indices = [i[0] for i in sim_scores]
    
    recommendations = pd.DataFrame({
        'anime_id': df_anime['anime_id'].iloc[anime_indices],
        'name': df_anime['name'].iloc[anime_indices],
        'image_url': df_anime['image_url'].iloc[anime_indices]
    })
    
    return recommendations.head()

def get_hybrid_recommendations(user_id, topN=10):
    recommended = []
    with get_db_connection() as conn:
        user_rated_anime_ids = pd.read_sql_query(f"SELECT anime_id FROM ratings WHERE user_id = {user_id}", conn)
        user_rated_anime_ids = user_rated_anime_ids['anime_id'].unique()
    
    if len(user_rated_anime_ids) == 0:
        return pd.DataFrame(columns=['anime_id', 'name', 'image_url'])

    cbf_result = pd.DataFrame(columns=['anime_id', 'name', 'image_url'])
    for anime_id in user_rated_anime_ids:
        if anime_id not in df_anime['anime_id'].values:
            continue
        anime_name = df_anime.loc[df_anime['anime_id'] == anime_id, 'name'].values[0]
        cbf_recommendations = get_cbf_recommendations(anime_name, cosine_sim, topN)
        if not cbf_recommendations.empty:
            cbf_result = pd.concat([cbf_result, cbf_recommendations])
    
    if not cbf_result.empty:
        cbf_result = cbf_result.drop_duplicates(subset='anime_id', keep='first').head(topN // 2)
    
    cf_result = get_cf_recommendations(user_id, topN // 2)
    if cf_result.empty:
        return pd.DataFrame(columns=['anime_id', 'name', 'image_url'])

    recommended.extend(cbf_result.to_dict('records'))
    recommended.extend(cf_result.to_dict('records'))

    recommended_df = pd.DataFrame(recommended)
    return recommended_df

# Function to generate popular item recommendations
def get_popular_recommendations(conn, topN=10):
    # Load data from the database
    df_ratings = pd.read_sql_query('SELECT * FROM ratings', conn)
    df_anime = pd.read_sql_query('SELECT * FROM anime', conn)

    # Step 1: Count the number of animes rated by each user
    count_user = df_ratings.groupby('user_id')['anime_id'].count()

    # Step 2: Count the number of ratings provided by each user and sort in descending order
    count_rating = df_ratings.groupby('user_id')['rating'].count().sort_values(ascending=False)

    # Step 3: Calculate the average number of animes rated per user
    average = count_user.mean()

    # Step 4: Identify active users who have rated more than or equal to the average number of animes
    rated = count_rating >= average
    active_user = count_rating[rated]

    # Step 5: Filter ratings to include only those from active users
    active_ratings = df_ratings[df_ratings['user_id'].isin(active_user.index)].reset_index(drop=True)

    # Step 6: Count the number of ratings for each anime and sort in descending order
    popular_item = active_ratings['anime_id'].value_counts().reset_index()
    popular_item.columns = ['anime_id', 'rating_count']

    # Step 7: Create lists to store the popular anime details
    anime_id = []
    title = []
    studios = []
    count_rating = []
    image_urls = []

    # Step 8: Get details for the top 10 popular items
    for item in popular_item.head(topN).itertuples(index=False):
        anime_id.append(item.anime_id)
        anime_details = df_anime[df_anime['anime_id'] == item.anime_id].iloc[0]
        title.append(anime_details['name'])
        studios.append(anime_details['studios'])
        count_rating.append(item.rating_count)
        image_urls.append(anime_details['image_url'])

    # Step 9: Create the recommendation list
    recommendation = list(zip(anime_id, title, studios, count_rating, image_urls))
    
    # Convert to DataFrame to be compatible with rendering
    recommendation_df = pd.DataFrame(recommendation, columns=['anime_id', 'name', 'studios', 'rating_count', 'image_url'])
    
    return recommendation_df.to_dict('records')

def get_genre_based_recommendations(conn, selected_genres, topN_per_genre=2):
    df_anime = pd.read_sql_query('SELECT * FROM anime', conn)

    recommendations = []
    for genre in selected_genres:
        print(f"Processing genre: {genre}")
        
        # Mengambil genre pertama dari setiap string genre
        df_anime['first_genre'] = df_anime['genres'].apply(lambda genres: genres.split(', ')[0] if pd.notnull(genres) else '')
        
        # Memfilter anime berdasarkan genre pertama saja
        filtered_anime = df_anime[df_anime['first_genre'] == genre]
        
        if filtered_anime.empty:
            print(f"No anime found for genre: {genre}")
            continue
        
        # Ambil hanya genre, judul, dan URL gambar, tanpa rating
        recommended_anime = filtered_anime[['anime_id', 'name', 'genres', 'image_url']].head(topN_per_genre)
        
        recommendations.append(recommended_anime)
    
    if recommendations:
        final_recommendations = pd.concat(recommendations).drop_duplicates('anime_id').reset_index(drop=True)
        print(f"Final recommendations: {final_recommendations}")
        return final_recommendations[['anime_id', 'name', 'genres', 'image_url']].to_dict(orient='records')
    else:
        print("No recommendations found")
        return []




@app.route('/')
def home():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        username = session.get('username')
        user_id = None
        recommendations = []
        is_new_user = False
        show_popular = True

        if username:
            user = cursor.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if user:
                user_id = user['user_id']
                user_ratings = cursor.execute('SELECT * FROM ratings WHERE user_id = ?', (user_id,)).fetchall()
                if user_ratings:
                    recommendations = get_hybrid_recommendations(user_id)
                    if not recommendations.empty:
                        recommendations = recommendations.to_dict('records')
                    else:
                        recommendations = []
                    show_popular = False
                else:
                    user_genres = cursor.execute('SELECT g.genre_name FROM user_genres ug JOIN genres g ON ug.genre_id = g.genre_id WHERE ug.user_id = ?', (user_id,)).fetchall()
                    if user_genres:
                        selected_genres = [g['genre_name'] for g in user_genres]
                        recommendations = get_genre_based_recommendations(conn, selected_genres)
                        is_new_user = True
            else:
                print(f"User {username} not found in database")

        if show_popular:
            animes = get_popular_recommendations(conn, topN=10)
        else:
            animes = []

    return render_template('home.html', username=username, user_id=user_id, recommendations=recommendations, animes=animes, is_new_user=is_new_user)

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        user_id = request.form['user_id']
        with get_db_connection() as conn:
            cursor = conn.cursor()
            user = cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if user:
                session['username'] = user['username']
                return redirect(url_for('home'))
            else:
                error = "User ID not found. Please try again."
                return render_template('login.html', error=error)
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

@app.route('/register', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        username = request.form['username']
        genres = request.form.getlist('genres')
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Insert user into the database
                cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
                user_id = cursor.lastrowid

                # Insert user genres into the database
                for genre in genres:
                    genre_id = cursor.execute("SELECT genre_id FROM genres WHERE genre_name = ?", (genre,)).fetchone()
                    if genre_id:
                        cursor.execute("INSERT INTO user_genres (user_id, genre_id) VALUES (?, ?)", (user_id, genre_id['genre_id']))
                
                conn.commit()
                session['username'] = username
                return redirect(url_for('home'))
        except sqlite3.Error as e:
            conn.rollback() 
            error = f"An error occurred: {e}"
            return render_template('register.html', error=error)
    
    # Fetch genres for display in the registration form
    with get_db_connection() as conn:
        cursor = conn.cursor()
        genres = cursor.execute('SELECT genre_name FROM genres').fetchall()
    return render_template('register.html', genres=genres)


@app.route('/evaluasi')
def evaluasi():
    # Data untuk grafik pencarian nilai k terbaik untuk hasil MAE terbaik pada CF
    mae_cf_data = [
        {'k': 50, 'mae': 1.126751},
        {'k': 100, 'mae': 1.116682},
        {'k': 150, 'mae': 1.119354},
        {'k': 200, 'mae': 1.123809},
        {'k': 250, 'mae': 1.125811},
    ]

    # Data untuk perbandingan MAE setiap model
    mae_values = [
        {'no': 1, 'method': 'CBF', 'mae': 2.318},
        {'no': 2, 'method': 'CF', 'mae': 1.116},
        {'no': 3, 'method': 'Hybrid', 'mae': 0.417},
    ]

    # Data untuk grafik ILS pada Top-N
    ils_data = [
        {'model': 'CBF', 'n': 6, 'ils': 0.560362},
        {'model': 'CBF', 'n': 8, 'ils': 0.560362},
        {'model': 'CBF', 'n': 10, 'ils': 0.560362},
        {'model': 'CF', 'n': 6, 'ils': 0.308798},
        {'model': 'CF', 'n': 8, 'ils': 0.302304},
        {'model': 'CF', 'n': 10, 'ils': 0.301962},
        {'model': 'Hybrid', 'n': 6, 'ils': 0.387691},
        {'model': 'Hybrid', 'n': 8, 'ils': 0.380886},
        {'model': 'Hybrid', 'n': 10, 'ils': 0.374583},
    ]

    return render_template('evaluasi.html', mae_cf_data=mae_cf_data, mae_values=mae_values, ils_data=ils_data)

if __name__ == '__main__':
    app.run(debug=True)