import sqlite3
from pathlib import Path
from typing import Any
from werkzeug.security import generate_password_hash, check_password_hash


# w Abre uma conexão configurada para retornar linhas acessíveis por nome.
def get_connection(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


# w Versão do schema em que o tmdb_id identifica os filmes, guardada em PRAGMA user_version.
SCHEMA_VERSION = 2

# w Schema com tmdb_id como chave; o imdb_id é opcional porque nem todo filme do TMDb possui um.
SCHEMA_STATEMENTS = (
    '''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        password_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, tmdb_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (tmdb_id) REFERENCES movies(tmdb_id) ON DELETE CASCADE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        tmdb_id INTEGER NOT NULL,
        body TEXT NOT NULL CHECK (length(trim(body)) > 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, tmdb_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (tmdb_id) REFERENCES movies(tmdb_id) ON DELETE CASCADE
    )
    ''',
)


# w Cria o schema com tmdb_id em bancos novos e deixa qualquer banco existente intacto.
def init_database(database_path: Path) -> None:
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = get_connection(database_path)
    try:
        # w Se movies já existe, o banco é antigo ou já migrado; só migrate_to_tmdb_ids o converte.
        has_movies = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'movies'"
        ).fetchone()
        if has_movies:
            return
        connection.execute('BEGIN')
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        connection.commit()
    finally:
        connection.close()


# w Salva os dados básicos de um filme sem criar registros duplicados.
def save_movie(database_path: Path, movie: dict[str, Any]) -> None:
    required_id = movie.get('imdbID')
    title = movie.get('Title')
    if not required_id or not title:
        raise ValueError('O filme precisa de imdbID e Title.')

    connection = get_connection(database_path)
    try:
        connection.execute(
            '''
            INSERT INTO movies (
                imdb_id, title, year, media_type, poster_url,
                cached_poster_path, genre
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(imdb_id) DO UPDATE SET
                title = excluded.title,
                year = excluded.year,
                media_type = excluded.media_type,
                poster_url = excluded.poster_url,
                cached_poster_path = excluded.cached_poster_path,
                genre = excluded.genre
            ''',
            (
                required_id,
                title,
                movie.get('Year'),
                movie.get('Type'),
                movie.get('Poster'),
                movie.get('_poster'),
                movie.get('Genre'),
            ),
        )
        connection.commit()
    finally:
        connection.close()


# w Busca um filme pelo IMDb ID e devolve um dicionário pronto para a aplicação.
def get_movie(database_path: Path, imdb_id: str) -> dict[str, Any] | None:
    connection = get_connection(database_path)
    try:
        row = connection.execute(
            '''
            SELECT
                imdb_id AS imdbID,
                title AS Title,
                year AS Year,
                media_type AS Type,
                poster_url AS Poster,
                cached_poster_path AS _poster,
                genre AS Genre
            FROM movies
            WHERE imdb_id = ?
            ''',
            (imdb_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


# w Cria ou atualiza a senha somente quando a conta ainda não possui uma.
def ensure_user_password(database_path: Path, username: str, password: str) -> None:
    password_hash = generate_password_hash(password)
    connection = get_connection(database_path)
    try:
        existing_user = connection.execute(
            'SELECT id, password_hash FROM users WHERE lower(username) = lower(?)',
            (username,),
        ).fetchone()
        if existing_user:
            if existing_user['password_hash'] is None:
                connection.execute(
                    'UPDATE users SET password_hash = ? WHERE id = ?',
                    (password_hash, existing_user['id']),
                )
        else:
            connection.execute(
                '''
                INSERT INTO users (username, display_name, password_hash)
                VALUES (?, ?, ?)
                ''',
                (username, username, password_hash),
            )
        connection.commit()
    finally:
        connection.close()


# w Valida usuário e senha sem expor a senha original ao restante da aplicação.
def authenticate_user(database_path: Path, username: str, password: str) -> dict[str, Any] | None:
    connection = get_connection(database_path)
    try:
        row = connection.execute(
            '''
            SELECT id, username, display_name, password_hash
            FROM users
            WHERE lower(username) = lower(?)
            ''',
            (username.strip().casefold(),),
        ).fetchone()
        if not row or not row['password_hash'] or not check_password_hash(row['password_hash'], password):
            return None
        return {
            'id': row['id'],
            'username': row['username'],
            'display_name': row['display_name'],
        }
    finally:
        connection.close()


# w Cria uma conta com a senha protegida por hash e rejeita usuários duplicados.
def create_user(database_path: Path, username: str, password: str) -> dict[str, Any]:
    username = username.strip()
    if len(username) < 2 or len(username) > 30:
        raise ValueError('O usuário precisa ter entre 2 e 30 caracteres.')
    if not username.replace('_', '').replace('-', '').isalnum():
        raise ValueError('O usuário pode conter apenas letras, números, "_" ou "-".')
    if not password:
        raise ValueError('A senha não pode ficar vazia.')

    connection = get_connection(database_path)
    try:
        existing = connection.execute(
            'SELECT 1 FROM users WHERE lower(username) = lower(?)',
            (username,),
        ).fetchone()
        if existing:
            raise ValueError('Este usuário já está em uso.')

        cursor = connection.execute(
            '''
            INSERT INTO users (username, display_name, password_hash)
            VALUES (?, ?, ?)
            ''',
            (username, username, generate_password_hash(password)),
        )
        connection.commit()
        return {
            'id': cursor.lastrowid,
            'username': username,
            'display_name': username,
        }
    finally:
        connection.close()


# w Retorna somente os filmes e dados pessoais do usuário autenticado.
def get_user_library(database_path: Path, user_id: int) -> dict[str, dict[str, Any]]:
    connection = get_connection(database_path)
    try:
        rows = connection.execute(
            '''
            SELECT
                m.imdb_id AS imdbID, m.title AS Title, m.year AS Year,
                m.media_type AS Type, m.poster_url AS Poster,
                m.cached_poster_path AS _poster, m.genre AS Genre,
                um.favorite, um.watched, um.rating, r.body AS review
            FROM movies m
            LEFT JOIN user_movies um ON um.imdb_id = m.imdb_id AND um.user_id = ?
            LEFT JOIN reviews r ON r.user_id = ? AND r.imdb_id = m.imdb_id
            WHERE um.user_id IS NOT NULL OR r.user_id IS NOT NULL
            ''',
            (user_id, user_id),
        ).fetchall()
        return {
            row['imdbID']: {
                **dict(row),
                'favorite': bool(row['favorite'] or 0),
                'watched': bool(row['watched'] or 0),
            }
            for row in rows
        }
    finally:
        connection.close()


# w Salva o filme e o estado pessoal em uma transação curta e consistente.
def save_user_movie_state(
    database_path: Path,
    user_id: int,
    movie: dict[str, Any],
    favorite: bool,
    watched: bool,
    rating: float | None,
) -> dict[str, Any]:
    if not movie.get('imdbID') or not movie.get('Title'):
        raise ValueError('O filme precisa de imdbID e Title.')
    if rating is not None and (rating < 0 or rating > 5 or rating * 2 != int(rating * 2)):
        raise ValueError('A nota precisa estar entre 0 e 5, em passos de 0,5.')

    connection = get_connection(database_path)
    try:
        connection.execute(
            '''
            INSERT INTO movies (imdb_id, title, year, media_type, poster_url, cached_poster_path, genre)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(imdb_id) DO UPDATE SET
                title = excluded.title, year = excluded.year, media_type = excluded.media_type,
                poster_url = excluded.poster_url, cached_poster_path = excluded.cached_poster_path,
                genre = excluded.genre
            ''',
            (
                movie['imdbID'], movie['Title'], movie.get('Year'), movie.get('Type'),
                movie.get('Poster'), movie.get('_poster'), movie.get('Genre'),
            ),
        )
        connection.execute(
            '''
            INSERT INTO user_movies (user_id, imdb_id, favorite, watched, rating)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, imdb_id) DO UPDATE SET
                favorite = excluded.favorite, watched = excluded.watched,
                rating = excluded.rating, updated_at = CURRENT_TIMESTAMP
            ''',
            (user_id, movie['imdbID'], int(favorite), int(watched), rating),
        )
        connection.commit()
    finally:
        connection.close()
    return get_user_library(database_path, user_id)[movie['imdbID']]


# w Cria, atualiza ou remove a review do filme do usuário autenticado.
def save_user_review(database_path: Path, user_id: int, movie: dict[str, Any], review: str) -> None:
    if not movie.get('imdbID') or not movie.get('Title'):
        raise ValueError('O filme precisa de imdbID e Title.')
    review = review.strip()
    if len(review) > 2000:
        raise ValueError('A review não pode ultrapassar 2.000 caracteres.')

    connection = get_connection(database_path)
    try:
        connection.execute(
            '''
            INSERT INTO movies (imdb_id, title, year, media_type, poster_url, cached_poster_path, genre)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(imdb_id) DO UPDATE SET
                title = excluded.title, year = excluded.year, media_type = excluded.media_type,
                poster_url = excluded.poster_url, cached_poster_path = excluded.cached_poster_path,
                genre = excluded.genre
            ''',
            (
                movie['imdbID'], movie['Title'], movie.get('Year'), movie.get('Type'),
                movie.get('Poster'), movie.get('_poster'), movie.get('Genre'),
            ),
        )
        if review:
            connection.execute(
                '''
                INSERT INTO reviews (user_id, imdb_id, body) VALUES (?, ?, ?)
                ON CONFLICT(user_id, imdb_id) DO UPDATE SET
                    body = excluded.body, updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, movie['imdbID'], review),
            )
        else:
            connection.execute(
                'DELETE FROM reviews WHERE user_id = ? AND imdb_id = ?',
                (user_id, movie['imdbID']),
            )
        connection.commit()
    finally:
        connection.close()
