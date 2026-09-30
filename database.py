import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Any
from werkzeug.security import generate_password_hash, check_password_hash


def get_connection(database_url: str):
    connection = psycopg2.connect(database_url)
    return connection


SCHEMA_VERSION = 3

SCHEMA_STATEMENTS = (
    '''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        password_hash TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS movies (
        tmdb_id INTEGER PRIMARY KEY,
        imdb_id TEXT UNIQUE,
        title TEXT NOT NULL,
        year TEXT,
        media_type TEXT,
        poster_url TEXT,
        cached_poster_path TEXT,
        genre TEXT,
        public_rating REAL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS user_movies (
        user_id INTEGER NOT NULL,
        tmdb_id INTEGER NOT NULL,
        favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
        watched INTEGER NOT NULL DEFAULT 0 CHECK (watched IN (0, 1)),
        rating REAL CHECK (
            rating IS NULL
            OR (rating >= 0 AND rating <= 5 AND rating * 2 = CAST(rating * 2 AS INTEGER))
        ),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, tmdb_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (tmdb_id) REFERENCES movies(tmdb_id) ON DELETE CASCADE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS reviews (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        tmdb_id INTEGER NOT NULL,
        body TEXT NOT NULL CHECK (length(trim(body)) > 0),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, tmdb_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (tmdb_id) REFERENCES movies(tmdb_id) ON DELETE CASCADE
    )
    ''',
)


def init_database(database_url: str) -> None:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor()
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def _require_movie(movie: dict[str, Any]) -> None:
    tmdb_id = movie.get('tmdbID')
    if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool) or tmdb_id <= 0 or not movie.get('Title'):
        raise ValueError('O filme precisa de um tmdbID numérico e de Title.')


def _upsert_movie(cursor, movie: dict[str, Any]) -> None:
    _require_movie(movie)
    cursor.execute(
        '''
        INSERT INTO movies (
            tmdb_id, imdb_id, title, year, media_type, poster_url,
            cached_poster_path, genre, public_rating
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(tmdb_id) DO UPDATE SET
            imdb_id = COALESCE(EXCLUDED.imdb_id, movies.imdb_id),
            title = EXCLUDED.title,
            year = EXCLUDED.year,
            media_type = EXCLUDED.media_type,
            poster_url = EXCLUDED.poster_url,
            cached_poster_path = EXCLUDED.cached_poster_path,
            genre = EXCLUDED.genre,
            public_rating = COALESCE(EXCLUDED.public_rating, movies.public_rating)
        ''',
        (
            movie['tmdbID'],
            movie.get('imdbID'),
            movie['Title'],
            movie.get('Year'),
            movie.get('Type'),
            movie.get('Poster'),
            movie.get('_poster'),
            movie.get('Genre'),
            movie.get('public_rating'),
        ),
    )


def save_movie(database_url: str, movie: dict[str, Any]) -> None:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor()
        _upsert_movie(cursor, movie)
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def get_movie(database_url: str, tmdb_id: int) -> dict[str, Any] | None:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT
                tmdb_id AS "tmdbID",
                imdb_id AS "imdbID",
                title AS "Title",
                year AS "Year",
                media_type AS "Type",
                poster_url AS "Poster",
                cached_poster_path AS "_poster",
                genre AS "Genre",
                public_rating
            FROM movies
            WHERE tmdb_id = %s
            ''',
            (tmdb_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return dict(row) if row else None
    finally:
        connection.close()


def ensure_user_password(database_url: str, username: str, password: str) -> None:
    password_hash = generate_password_hash(password)
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            'SELECT id, password_hash FROM users WHERE LOWER(username) = LOWER(%s)',
            (username,),
        )
        existing_user = cursor.fetchone()
        if existing_user:
            if existing_user['password_hash'] is None:
                cursor.execute(
                    'UPDATE users SET password_hash = %s WHERE id = %s',
                    (password_hash, existing_user['id']),
                )
        else:
            cursor.execute(
                '''
                INSERT INTO users (username, display_name, password_hash)
                VALUES (%s, %s, %s)
                ''',
                (username, username, password_hash),
            )
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def authenticate_user(database_url: str, username: str, password: str) -> dict[str, Any] | None:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT id, username, display_name, password_hash
            FROM users
            WHERE LOWER(username) = LOWER(%s)
            ''',
            (username.strip(),),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row or not row['password_hash'] or not check_password_hash(row['password_hash'], password):
            return None
        return {
            'id': row['id'],
            'username': row['username'],
            'display_name': row['display_name'],
        }
    finally:
        connection.close()


def create_user(database_url: str, username: str, password: str) -> dict[str, Any]:
    username = username.strip()
    if len(username) < 2 or len(username) > 30:
        raise ValueError('O usuário precisa ter entre 2 e 30 caracteres.')
    if not username.replace('_', '').replace('-', '').isalnum():
        raise ValueError('O usuário pode conter apenas letras, números, "_" ou "-".')
    if not password:
        raise ValueError('A senha não pode ficar vazia.')

    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            'SELECT 1 FROM users WHERE LOWER(username) = LOWER(%s)',
            (username,),
        )
        if cursor.fetchone():
            raise ValueError('Este usuário já está em uso.')

        cursor.execute(
            '''
            INSERT INTO users (username, display_name, password_hash)
            VALUES (%s, %s, %s)
            RETURNING id
            ''',
            (username, username, generate_password_hash(password)),
        )
        user_id = cursor.fetchone()['id']
        connection.commit()
        cursor.close()
        return {
            'id': user_id,
            'username': username,
            'display_name': username,
        }
    finally:
        connection.close()


def get_user_profile(database_url: str, user_id: int) -> dict[str, Any] | None:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            'SELECT id, username, display_name, created_at FROM users WHERE id = %s',
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return dict(row) if row else None
    finally:
        connection.close()


def update_display_name(database_url: str, user_id: int, display_name: str) -> None:
    display_name = display_name.strip()
    if len(display_name) < 2 or len(display_name) > 40:
        raise ValueError('O nome de exibição precisa ter entre 2 e 40 caracteres.')

    connection = get_connection(database_url)
    try:
        cursor = connection.cursor()
        cursor.execute(
            'UPDATE users SET display_name = %s WHERE id = %s',
            (display_name, user_id),
        )
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def change_user_password(
    database_url: str,
    user_id: int,
    current_password: str,
    new_password: str,
) -> None:
    if not new_password:
        raise ValueError('A nova senha não pode ficar vazia.')

    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            'SELECT password_hash FROM users WHERE id = %s',
            (user_id,),
        )
        row = cursor.fetchone()
        if not row or not row['password_hash'] or not check_password_hash(row['password_hash'], current_password):
            raise ValueError('Senha atual incorreta.')
        cursor.execute(
            'UPDATE users SET password_hash = %s WHERE id = %s',
            (generate_password_hash(new_password), user_id),
        )
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def delete_user_account(database_url: str, user_id: int, password: str) -> None:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            'SELECT password_hash FROM users WHERE id = %s',
            (user_id,),
        )
        row = cursor.fetchone()
        if not row or not row['password_hash'] or not check_password_hash(row['password_hash'], password):
            raise ValueError('Senha incorreta.')
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def get_user_library(database_url: str, user_id: int) -> dict[int, dict[str, Any]]:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT
                m.tmdb_id AS "tmdbID", m.imdb_id AS "imdbID", m.title AS "Title", m.year AS "Year",
                m.media_type AS "Type", m.poster_url AS "Poster",
                m.cached_poster_path AS "_poster", m.genre AS "Genre",
                m.public_rating,
                um.favorite, um.watched, um.rating, r.body AS review,
                r.updated_at AS review_updated_at
            FROM movies m
            LEFT JOIN user_movies um ON um.tmdb_id = m.tmdb_id AND um.user_id = %s
            LEFT JOIN reviews r ON r.user_id = %s AND r.tmdb_id = m.tmdb_id
            WHERE um.user_id IS NOT NULL OR r.user_id IS NOT NULL
            ''',
            (user_id, user_id),
        )
        rows = cursor.fetchall()
        cursor.close()
        return {
            row['tmdbID']: {
                **dict(row),
                'favorite': bool(row['favorite'] or 0),
                'watched': bool(row['watched'] or 0),
            }
            for row in rows
        }
    finally:
        connection.close()


def get_user_activity(database_url: str, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT
                m.tmdb_id AS "tmdbID", m.title AS "Title", m.year AS "Year",
                m.cached_poster_path AS "_poster", m.poster_url AS "Poster",
                um.favorite, um.watched, um.rating, um.updated_at AS timestamp
            FROM user_movies um
            JOIN movies m ON m.tmdb_id = um.tmdb_id
            WHERE um.user_id = %s
            ''',
            (user_id,),
        )
        movie_rows = cursor.fetchall()

        cursor.execute(
            '''
            SELECT
                m.tmdb_id AS "tmdbID", m.title AS "Title", m.year AS "Year",
                m.cached_poster_path AS "_poster", m.poster_url AS "Poster",
                r.body AS review, r.updated_at AS timestamp
            FROM reviews r
            JOIN movies m ON m.tmdb_id = r.tmdb_id
            WHERE r.user_id = %s
            ''',
            (user_id,),
        )
        review_rows = cursor.fetchall()
        cursor.close()
    finally:
        connection.close()

    activity = []
    for row in movie_rows:
        if not (row['favorite'] or row['watched'] or row['rating'] is not None):
            continue
        activity.append({
            'type': 'movie_state',
            'tmdbID': row['tmdbID'],
            'Title': row['Title'],
            'Year': row['Year'],
            '_poster': row['_poster'],
            'Poster': row['Poster'],
            'favorite': bool(row['favorite']),
            'watched': bool(row['watched']),
            'rating': row['rating'],
            'timestamp': str(row['timestamp']),
        })
    for row in review_rows:
        activity.append({
            'type': 'review',
            'tmdbID': row['tmdbID'],
            'Title': row['Title'],
            'Year': row['Year'],
            '_poster': row['_poster'],
            'Poster': row['Poster'],
            'review': row['review'],
            'timestamp': str(row['timestamp']),
        })
    activity.sort(key=lambda item: item['timestamp'], reverse=True)
    return activity[:limit]


def _most_common(values: list[str]) -> dict[str, Any] | None:
    counts: dict[str, int] = {}
    for value in values:
        for part in str(value or '').split(','):
            trimmed = part.strip()
            if trimmed:
                counts[trimmed] = counts.get(trimmed, 0) + 1
    if not counts:
        return None
    name = max(counts, key=lambda key: counts[key])
    return {'name': name, 'count': counts[name]}


def get_user_statistics(database_url: str, user_id: int) -> dict[str, Any]:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT m.tmdb_id AS "tmdbID", m.title AS "Title", m.year AS "Year", m.genre AS "Genre", um.rating
            FROM user_movies um
            JOIN movies m ON m.tmdb_id = um.tmdb_id
            WHERE um.user_id = %s AND um.watched = 1
            ''',
            (user_id,),
        )
        watched_rows = cursor.fetchall()

        cursor.execute(
            'SELECT COUNT(*) AS count FROM user_movies WHERE user_id = %s AND favorite = 1',
            (user_id,),
        )
        favorite_count = cursor.fetchone()['count']

        cursor.execute(
            'SELECT COUNT(*) AS count FROM reviews WHERE user_id = %s',
            (user_id,),
        )
        review_count = cursor.fetchone()['count']
        cursor.close()
    finally:
        connection.close()

    rated = [row for row in watched_rows if row['rating'] is not None]
    average_rating = sum(row['rating'] for row in rated) / len(rated) if rated else None
    best_movie = max(rated, key=lambda row: row['rating'], default=None)
    worst_movie = min(rated, key=lambda row: row['rating'], default=None)
    decades = [f"{(int(row['Year']) // 10) * 10}s" for row in watched_rows if (row['Year'] or '').isdigit()]

    return {
        'watched_count': len(watched_rows),
        'favorite_count': favorite_count,
        'review_count': review_count,
        'average_rating': average_rating,
        'top_genre': _most_common([row['Genre'] for row in watched_rows]),
        'top_decade': _most_common(decades),
        'best_movie': {'Title': best_movie['Title'], 'rating': best_movie['rating']} if best_movie else None,
        'worst_movie': {'Title': worst_movie['Title'], 'rating': worst_movie['rating']} if worst_movie else None,
    }


def get_household_statistics(database_url: str, usernames: tuple[str, ...]) -> dict[str, Any]:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            'SELECT id, display_name FROM users WHERE username IN %s ORDER BY display_name',
            (usernames,),
        )
        users = cursor.fetchall()

        cursor.execute(
            '''
            SELECT
                u.id AS user_id, u.display_name,
                COUNT(*) FILTER (WHERE um.watched = 1) AS watched_count,
                COUNT(*) FILTER (WHERE um.favorite = 1) AS favorite_count
            FROM users u
            LEFT JOIN user_movies um ON um.user_id = u.id
            WHERE u.username IN %s
            GROUP BY u.id
            ORDER BY watched_count DESC, u.display_name
            ''',
            (usernames,),
        )
        per_user_counts = cursor.fetchall()

        cursor.execute(
            '''
            SELECT m.tmdb_id AS "tmdbID", m.title AS "Title", u.display_name, um.rating
            FROM user_movies um
            JOIN movies m ON m.tmdb_id = um.tmdb_id
            JOIN users u ON u.id = um.user_id
            WHERE um.watched = 1 AND u.username IN %s
            ''',
            (usernames,),
        )
        watched_rows = cursor.fetchall()
        cursor.close()
    finally:
        connection.close()

    by_movie: dict[int, dict[str, Any]] = {}
    for row in watched_rows:
        entry = by_movie.setdefault(row['tmdbID'], {'Title': row['Title'], 'watchers': [], 'ratings': {}})
        entry['watchers'].append(row['display_name'])
        if row['rating'] is not None:
            entry['ratings'][row['display_name']] = row['rating']

    shared_movies = sorted(
        (
            {'Title': entry['Title'], 'watchers': entry['watchers'], 'watcher_count': len(entry['watchers'])}
            for entry in by_movie.values() if len(entry['watchers']) > 1
        ),
        key=lambda item: (-item['watcher_count'], item['Title'] or ''),
    )

    divergent_ratings = sorted(
        (
            {
                'Title': entry['Title'],
                'ratings': entry['ratings'],
                'difference': max(entry['ratings'].values()) - min(entry['ratings'].values()),
            }
            for entry in by_movie.values() if len(entry['ratings']) > 1
        ),
        key=lambda item: -item['difference'],
    )[:5]

    return {
        'users': [dict(user) for user in users],
        'per_user_counts': [dict(row) for row in per_user_counts],
        'shared_movies': shared_movies,
        'divergent_ratings': divergent_ratings,
    }


def get_household_activity(database_url: str, usernames: tuple[str, ...], limit: int = 10) -> list[dict[str, Any]]:
    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            '''
            SELECT
                m.tmdb_id AS "tmdbID", m.title AS "Title", m.year AS "Year",
                m.cached_poster_path AS "_poster", m.poster_url AS "Poster",
                u.display_name, um.favorite, um.watched, um.rating, um.updated_at AS timestamp
            FROM user_movies um
            JOIN movies m ON m.tmdb_id = um.tmdb_id
            JOIN users u ON u.id = um.user_id
            WHERE u.username IN %s
            ''',
            (usernames,),
        )
        movie_rows = cursor.fetchall()

        cursor.execute(
            '''
            SELECT
                m.tmdb_id AS "tmdbID", m.title AS "Title", m.year AS "Year",
                m.cached_poster_path AS "_poster", m.poster_url AS "Poster",
                u.display_name, r.body AS review, r.updated_at AS timestamp
            FROM reviews r
            JOIN movies m ON m.tmdb_id = r.tmdb_id
            JOIN users u ON u.id = r.user_id
            WHERE u.username IN %s
            ''',
            (usernames,),
        )
        review_rows = cursor.fetchall()
        cursor.close()
    finally:
        connection.close()

    activity = []
    for row in movie_rows:
        if not (row['favorite'] or row['watched'] or row['rating'] is not None):
            continue
        activity.append({
            'type': 'movie_state',
            'tmdbID': row['tmdbID'],
            'Title': row['Title'],
            'Year': row['Year'],
            '_poster': row['_poster'],
            'Poster': row['Poster'],
            'display_name': row['display_name'],
            'favorite': bool(row['favorite']),
            'watched': bool(row['watched']),
            'rating': row['rating'],
            'timestamp': str(row['timestamp']),
        })
    for row in review_rows:
        activity.append({
            'type': 'review',
            'tmdbID': row['tmdbID'],
            'Title': row['Title'],
            'Year': row['Year'],
            '_poster': row['_poster'],
            'Poster': row['Poster'],
            'display_name': row['display_name'],
            'review': row['review'],
            'timestamp': str(row['timestamp']),
        })
    activity.sort(key=lambda item: item['timestamp'], reverse=True)
    return activity[:limit]


def save_user_movie_state(
    database_url: str,
    user_id: int,
    movie: dict[str, Any],
    favorite: bool,
    watched: bool,
    rating: float | None,
) -> dict[str, Any]:
    _require_movie(movie)
    if rating is not None and (rating < 0 or rating > 5 or rating * 2 != int(rating * 2)):
        raise ValueError('A nota precisa estar entre 0 e 5, em passos de 0,5.')

    connection = get_connection(database_url)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        _upsert_movie(cursor, movie)
        cursor.execute(
            '''
            INSERT INTO user_movies (user_id, tmdb_id, favorite, watched, rating)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(user_id, tmdb_id) DO UPDATE SET
                favorite = EXCLUDED.favorite, watched = EXCLUDED.watched,
                rating = EXCLUDED.rating, updated_at = CURRENT_TIMESTAMP
            ''',
            (user_id, movie['tmdbID'], int(favorite), int(watched), rating),
        )
        connection.commit()
        cursor.close()
    finally:
        connection.close()
    return get_user_library(database_url, user_id)[movie['tmdbID']]


def save_user_review(database_url: str, user_id: int, movie: dict[str, Any], review: str) -> None:
    _require_movie(movie)
    review = review.strip()
    if len(review) > 2000:
        raise ValueError('A review não pode ultrapassar 2.000 caracteres.')

    connection = get_connection(database_url)
    try:
        cursor = connection.cursor()
        _upsert_movie(cursor, movie)
        if review:
            cursor.execute(
                '''
                INSERT INTO reviews (user_id, tmdb_id, body) VALUES (%s, %s, %s)
                ON CONFLICT(user_id, tmdb_id) DO UPDATE SET
                    body = EXCLUDED.body, updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, movie['tmdbID'], review),
            )
        else:
            cursor.execute(
                'DELETE FROM reviews WHERE user_id = %s AND tmdb_id = %s',
                (user_id, movie['tmdbID']),
            )
        connection.commit()
        cursor.close()
    finally:
        connection.close()
