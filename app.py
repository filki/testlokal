from flask import Flask, render_template, request, send_file, abort, jsonify
from services.visualization_service import generate_top_authors_svg, create_top_genres_chart, create_top_publishers_chart, create_top_developers_chart, VisualizationService
from services.db_service import cached_get_reviews, get_total_reviews_count, get_review_by_id, get_games_list, get_unique_genres
from services.text_analysis_service import TextAnalysisService
import sqlite3

app = Flask(__name__)
visualizer = VisualizationService()
text_analysis_service = TextAnalysisService()

# Add built-in functions to Jinja2 context
app.jinja_env.globals.update(
    max=max,
    min=min,
    len=len,
    range=range
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['GET'])
def search():
    keyword = request.args.get('keyword', '')
    filter_option = request.args.get('filter_option', 'all')
    scoring_method = request.args.get('scoring_method', 'tfidf')
    selected_game = request.args.get('game_id', '')
    page = request.args.get('page', 1, type=int)
    
    # New filters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    min_playtime = request.args.get('min_playtime', type=int)
    min_funny = request.args.get('min_funny', type=int)
    received_free = request.args.get('received_free') == 'true'
    early_access = request.args.get('early_access') == 'true'
    
    # Get all games for the dropdown
    games_list = get_games_list()
    
    # Get reviews with all filters
    reviews = cached_get_reviews(
        page=page,
        keyword=keyword,
        filter_option=filter_option,
        scoring_method=scoring_method,
        game_id=selected_game,
        date_from=date_from,
        date_to=date_to,
        min_playtime=min_playtime,
        min_funny=min_funny,
        received_free=received_free,
        early_access=early_access
    )
    
    # Add text analysis including named entities for each review
    for review in reviews:
        if 'content' in review:
            review['analysis'] = text_analysis_service.analyze_text(review['content'])
    
    # Calculate total pages
    total_reviews = get_total_reviews_count(
        keyword=keyword,
        filter_option=filter_option,
        game_id=selected_game,
        date_from=date_from,
        date_to=date_to,
        min_playtime=min_playtime,
        min_funny=min_funny,
        received_free=received_free,
        early_access=early_access
    )
    
    per_page = 20
    total_pages = (total_reviews + per_page - 1) // per_page
    
    scoring_methods = [
        {'id': 'tfidf', 'name': 'TF-IDF', 'description': 'Zaawansowane wyszukiwanie uwzględniające częstość słów'},
        {'id': 'cosine', 'name': 'Cosine', 'description': 'Podobieństwo cosinusowe między dokumentami'},
        {'id': 'word2vec', 'name': 'Word2Vec', 'description': 'Wyszukiwanie semantyczne z wykorzystaniem embeddings'},
        {'id': 'jaccard', 'name': 'Jaccard', 'description': 'Proste porównanie na podstawie wspólnych słów'}
    ]
    
    return render_template('search.html',
                         reviews=reviews,
                         games=games_list,
                         current_page=page,
                         total_pages=total_pages,
                         search_params={
                             'keyword': keyword,
                             'filter_option': filter_option,
                             'scoring_method': scoring_method,
                             'game_id': selected_game,
                             'date_from': date_from,
                             'date_to': date_to,
                             'min_playtime': min_playtime,
                             'min_funny': min_funny,
                             'received_free': received_free,
                             'early_access': early_access
                         },
                         scoring_methods=scoring_methods)

@app.route('/visualizations')
def visualizations():
    top_genres = create_top_genres_chart()
    top_publishers = create_top_publishers_chart()
    top_developers = create_top_developers_chart()
    
    # Get unique genres for the filter dropdown
    genres = get_unique_genres()
    
    # Generate word cloud from all reviews
    word_cloud = visualizer.generate_word_cloud(visualizer.get_all_reviews_text())
    
    return render_template('visualizations.html',
                         top_genres=top_genres,
                         top_publishers=top_publishers,
                         top_developers=top_developers,
                         word_cloud_image=word_cloud,
                         genres=genres)

@app.route('/update_word_cloud')
def update_word_cloud():
    genre = request.args.get('genre', '')
    if genre:
        text = visualizer.get_reviews_text_by_genre(genre)
    else:
        text = visualizer.get_all_reviews_text()
    
    word_cloud = visualizer.generate_word_cloud(text)
    return jsonify({'word_cloud': word_cloud})

@app.route('/clear-cache')
def clear_cache():
    cached_get_reviews.cache_clear()
    return "Cache został wyczyszczony!"

@app.route('/review/<int:review_id>')
def review_detail(review_id):
    review = get_review_by_id(review_id)
    if review is None:
        abort(404)
    return render_template('review_detail.html', review=review)

@app.route('/games')
def show_games():
    # Connect to the database
    conn = sqlite3.connect('data/steam_reviews_with_authors.db')
    cursor = conn.cursor()

    # Get filter values from request
    name_filter = request.args.get('name', '')
    owner_filter = request.args.get('owners', '')
    developer_filter = request.args.get('developer', '')
    publisher_filter = request.args.get('publisher', '')
    language_filter = request.args.get('languages', '')
    genre_filter = request.args.get('genre', '')

    # Base query
    query = "SELECT * FROM games WHERE 1=1"
    params = []

    # Add filters if they exist
    if name_filter:
        query += " AND name LIKE ?"
        params.append(f"%{name_filter}%")
    if owner_filter:
        query += " AND owners = ?"
        params.append(owner_filter)
    if developer_filter:
        query += " AND developer = ?"
        params.append(developer_filter)
    if publisher_filter:
        query += " AND publisher = ?"
        params.append(publisher_filter)
    if language_filter:
        query += " AND languages LIKE ?"
        params.append(f"%{language_filter}%")
    if genre_filter:
        query += " AND genre = ?"
        params.append(genre_filter)

    # Get filtered games
    cursor.execute(query, params)
    games = cursor.fetchall()

    # Get unique values for dropdowns
    cursor.execute("SELECT DISTINCT owners FROM games ORDER BY owners")
    owners = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT developer FROM games ORDER BY developer")
    developers = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT publisher FROM games ORDER BY publisher")
    publishers = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT languages FROM games ORDER BY languages")
    languages = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT genre FROM games ORDER BY genre")
    genres = [row[0] for row in cursor.fetchall()]

    # Close the connection
    conn.close()

    return render_template('games.html', 
                         games=games,
                         owners=owners,
                         developers=developers,
                         publishers=publishers,
                         languages=languages,
                         genres=genres,
                         filters={
                             'name': name_filter,
                             'owners': owner_filter,
                             'developer': developer_filter,
                             'publisher': publisher_filter,
                             'languages': language_filter,
                             'genre': genre_filter
                         })

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == "__main__":
    app.run(debug=True)
