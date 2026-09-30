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


# w Versão do schema; a 3 acrescenta public_rating em movies para os filtros da Etapa 6.3.
SCHEMA_VERSION = 3

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
        public_rating REAL,
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


# w Acrescenta a coluna public_rating sem mexer nos dados existentes, se ainda não existir.
def _ensure_public_rating_column(connection: sqlite3.Connection) -> None:
    columns = {row['name'] for row in connection.execute('PRAGMA table_info(movies)').fetchall()}
    if 'public_rating' not in columns:
        connection.execute('ALTER TABLE movies ADD COLUMN public_rating REAL')
        connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        connection.commit()


# w Cria o schema com tmdb_id em bancos novos e aplica migrações aditivas em bancos existentes.
def init_database(database_path: Path) -> None:
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = get_connection(database_path)
    try:
        # w Se movies já existe, o banco é antigo ou já migrado; só migrate_to_tmdb_ids converte a chave.
        has_movies = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'movies'"
        ).fetchone()
        if has_movies:
            _ensure_public_rating_column(connection)
            return
        connection.execute('BEGIN')
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        connection.commit()
    finally:
        connection.close()


# w Garante um tmdbID numérico e um título antes de qualquer escrita no banco.
def _require_movie(movie: dict[str, Any]) -> None:
    tmdb_id = movie.get('tmdbID')
    if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool) or tmdb_id <= 0 or not movie.get('Title'):
        raise ValueError('O filme precisa de um tmdbID numérico e de Title.')


# w Insere ou atualiza o filme pelo tmdb_id, sem apagar um imdb_id que já era conhecido.
def _upsert_movie(connection: sqlite3.Connection, movie: dict[str, Any]) -> None:
    _require_movie(movie)
    connection.execute(
        '''
        INSERT INTO movies (
            tmdb_id, imdb_id, title, year, media_type, poster_url,
            cached_poster_path, genre, public_rating
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tmdb_id) DO UPDATE SET
            imdb_id = COALESCE(excluded.imdb_id, movies.imdb_id),
            title = excluded.title,
            year = excluded.year,
            media_type = excluded.media_type,
            poster_url = excluded.poster_url,
            cached_poster_path = excluded.cached_poster_path,
            genre = excluded.genre,
            public_rating = COALESCE(excluded.public_rating, movies.public_rating)
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


# w Salva os dados básicos de um filme sem criar registros duplicados.
def save_movie(database_path: Path, movie: dict[str, Any]) -> None:
    connection = get_connection(database_path)
    try:
        _upsert_movie(connection, movie)
        connection.commit()
    finally:
        connection.close()


# w Busca um filme pelo tmdb_id e devolve um dicionário pronto para a aplicação.
def get_movie(database_path: Path, tmdb_id: int) -> dict[str, Any] | None:
    connection = get_connection(database_path)
    try:
        row = connection.execute(
            '''
            SELECT
                tmdb_id AS tmdbID,
                imdb_id AS imdbID,
                title AS Title,
                year AS Year,
                media_type AS Type,
                poster_url AS Poster,
                cached_poster_path AS _poster,
                genre AS Genre,
                public_rating
            FROM movies
            WHERE tmdb_id = ?
            ''',
            (tmdb_id,),
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


# w Retorna os dados públicos do perfil, sem expor o hash da senha.
def get_user_profile(database_path: Path, user_id: int) -> dict[str, Any] | None:
    connection = get_connection(database_path)
    try:
        row = connection.execute(
            'SELECT id, username, display_name, created_at FROM users WHERE id = ?',
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


# w Atualiza o nome de exibição, mantendo o username (login) intacto.
def update_display_name(database_path: Path, user_id: int, display_name: str) -> None:
    display_name = display_name.strip()
    if len(display_name) < 2 or len(display_name) > 40:
        raise ValueError('O nome de exibição precisa ter entre 2 e 40 caracteres.')

    connection = get_connection(database_path)
    try:
        connection.execute(
            'UPDATE users SET display_name = ? WHERE id = ?',
            (display_name, user_id),
        )
        connection.commit()
    finally:
        connection.close()


# w Só troca a senha depois de confirmar a senha atual, para evitar sequestro de sessão.
def change_user_password(
    database_path: Path,
    user_id: int,
    current_password: str,
    new_password: str,
) -> None:
    if not new_password:
        raise ValueError('A nova senha não pode ficar vazia.')

    connection = get_connection(database_path)
    try:
        row = connection.execute(
            'SELECT password_hash FROM users WHERE id = ?',
            (user_id,),
        ).fetchone()
        if not row or not row['password_hash'] or not check_password_hash(row['password_hash'], current_password):
            raise ValueError('Senha atual incorreta.')
        connection.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (generate_password_hash(new_password), user_id),
        )
        connection.commit()
    finally:
        connection.close()


# w Exige a senha atual antes de apagar a conta; user_movies e reviews caem em cascata.
def delete_user_account(database_path: Path, user_id: int, password: str) -> None:
    connection = get_connection(database_path)
    try:
        row = connection.execute(
            'SELECT password_hash FROM users WHERE id = ?',
            (user_id,),
        ).fetchone()
        if not row or not row['password_hash'] or not check_password_hash(row['password_hash'], password):
            raise ValueError('Senha incorreta.')
        connection.execute('DELETE FROM users WHERE id = ?', (user_id,))
        connection.commit()
    finally:
        connection.close()


# w Retorna somente os filmes e dados pessoais do usuário autenticado.
def get_user_library(database_path: Path, user_id: int) -> dict[int, dict[str, Any]]:
    connection = get_connection(database_path)
    try:
        rows = connection.execute(
            '''
            SELECT
                m.tmdb_id AS tmdbID, m.imdb_id AS imdbID, m.title AS Title, m.year AS Year,
                m.media_type AS Type, m.poster_url AS Poster,
                m.cached_poster_path AS _poster, m.genre AS Genre,
                m.public_rating,
                um.favorite, um.watched, um.rating, r.body AS review,
                r.updated_at AS review_updated_at
            FROM movies m
            LEFT JOIN user_movies um ON um.tmdb_id = m.tmdb_id AND um.user_id = ?
            LEFT JOIN reviews r ON r.user_id = ? AND r.tmdb_id = m.tmdb_id
            WHERE um.user_id IS NOT NULL OR r.user_id IS NOT NULL
            ''',
            (user_id, user_id),
        ).fetchall()
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


# w Junta as mudanças em user_movies e reviews num histórico só, mais recente primeiro.
# w Cada linha do banco vira um evento por vez (não por clique), pois é o que existe registrado.
def get_user_activity(database_path: Path, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    connection = get_connection(database_path)
    try:
        movie_rows = connection.execute(
            '''
            SELECT
                m.tmdb_id AS tmdbID, m.title AS Title, m.year AS Year,
                m.cached_poster_path AS _poster, m.poster_url AS Poster,
                um.favorite, um.watched, um.rating, um.updated_at AS timestamp
            FROM user_movies um
            JOIN movies m ON m.tmdb_id = um.tmdb_id
            WHERE um.user_id = ?
            ''',
            (user_id,),
        ).fetchall()
        review_rows = connection.execute(
            '''
            SELECT
                m.tmdb_id AS tmdbID, m.title AS Title, m.year AS Year,
                m.cached_poster_path AS _poster, m.poster_url AS Poster,
                r.body AS review, r.updated_at AS timestamp
            FROM reviews r
            JOIN movies m ON m.tmdb_id = r.tmdb_id
            WHERE r.user_id = ?
            ''',
            (user_id,),
        ).fetchall()
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
            'timestamp': row['timestamp'],
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
            'timestamp': row['timestamp'],
        })
    activity.sort(key=lambda item: item['timestamp'], reverse=True)
    return activity[:limit]


# w Conta ocorrências de um campo separado por vírgula (gênero) e devolve o mais comum.
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


# w Resume os números pessoais do usuário: assistidos, favoritos, notas, gênero/década preferidos.
def get_user_statistics(database_path: Path, user_id: int) -> dict[str, Any]:
    connection = get_connection(database_path)
    try:
        watched_rows = connection.execute(
            '''
            SELECT m.tmdb_id AS tmdbID, m.title AS Title, m.year AS Year, m.genre AS Genre, um.rating
            FROM user_movies um
            JOIN movies m ON m.tmdb_id = um.tmdb_id
            WHERE um.user_id = ? AND um.watched = 1
            ''',
            (user_id,),
        ).fetchall()
        favorite_count = connection.execute(
            'SELECT COUNT(*) FROM user_movies WHERE user_id = ? AND favorite = 1',
            (user_id,),
        ).fetchone()[0]
        review_count = connection.execute(
            'SELECT COUNT(*) FROM reviews WHERE user_id = ?',
            (user_id,),
        ).fetchone()[0]
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


# w Compara os participantes da casa (por username, ver config.HOUSEHOLD_USERNAMES): quem
# w assistiu mais, filmes em comum e maior divergência de nota. Outras contas do app ficam fora.
def get_household_statistics(database_path: Path, usernames: tuple[str, ...]) -> dict[str, Any]:
    placeholders = ','.join('?' for _ in usernames)
    connection = get_connection(database_path)
    try:
        users = connection.execute(
            f'SELECT id, display_name FROM users WHERE username IN ({placeholders}) ORDER BY display_name',
            usernames,
        ).fetchall()
        per_user_counts = connection.execute(
            f'''
            SELECT
                u.id AS user_id, u.display_name,
                COUNT(*) FILTER (WHERE um.watched = 1) AS watched_count,
                COUNT(*) FILTER (WHERE um.favorite = 1) AS favorite_count
            FROM users u
            LEFT JOIN user_movies um ON um.user_id = u.id
            WHERE u.username IN ({placeholders})
            GROUP BY u.id
            ORDER BY watched_count DESC, u.display_name
            ''',
            usernames,
        ).fetchall()
        watched_rows = connection.execute(
            f'''
            SELECT m.tmdb_id AS tmdbID, m.title AS Title, u.display_name, um.rating
            FROM user_movies um
            JOIN movies m ON m.tmdb_id = um.tmdb_id
            JOIN users u ON u.id = um.user_id
            WHERE um.watched = 1 AND u.username IN ({placeholders})
            ''',
            usernames,
        ).fetchall()
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


# w Igual a get_user_activity, mas dos participantes da casa juntos (por username, ver
# w config.HOUSEHOLD_USERNAMES), com o nome de quem fez o quê. Serve para o resumo da /home;
# w a versão pessoal em get_user_activity segue usada em /atividade.
def get_household_activity(database_path: Path, usernames: tuple[str, ...], limit: int = 10) -> list[dict[str, Any]]:
    placeholders = ','.join('?' for _ in usernames)
    connection = get_connection(database_path)
    try:
        movie_rows = connection.execute(
            f'''
            SELECT
                m.tmdb_id AS tmdbID, m.title AS Title, m.year AS Year,
                m.cached_poster_path AS _poster, m.poster_url AS Poster,
                u.display_name, um.favorite, um.watched, um.rating, um.updated_at AS timestamp
            FROM user_movies um
            JOIN movies m ON m.tmdb_id = um.tmdb_id
            JOIN users u ON u.id = um.user_id
            WHERE u.username IN ({placeholders})
            ''',
            usernames,
        ).fetchall()
        review_rows = connection.execute(
            f'''
            SELECT
                m.tmdb_id AS tmdbID, m.title AS Title, m.year AS Year,
                m.cached_poster_path AS _poster, m.poster_url AS Poster,
                u.display_name, r.body AS review, r.updated_at AS timestamp
            FROM reviews r
            JOIN movies m ON m.tmdb_id = r.tmdb_id
            JOIN users u ON u.id = r.user_id
            WHERE u.username IN ({placeholders})
            ''',
            usernames,
        ).fetchall()
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
            'timestamp': row['timestamp'],
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
            'timestamp': row['timestamp'],
        })
    activity.sort(key=lambda item: item['timestamp'], reverse=True)
    return activity[:limit]


# w Salva o filme e o estado pessoal em uma transação curta e consistente.
def save_user_movie_state(
    database_path: Path,
    user_id: int,
    movie: dict[str, Any],
    favorite: bool,
    watched: bool,
    rating: float | None,
) -> dict[str, Any]:
    _require_movie(movie)
    if rating is not None and (rating < 0 or rating > 5 or rating * 2 != int(rating * 2)):
        raise ValueError('A nota precisa estar entre 0 e 5, em passos de 0,5.')

    connection = get_connection(database_path)
    try:
        _upsert_movie(connection, movie)
        connection.execute(
            '''
            INSERT INTO user_movies (user_id, tmdb_id, favorite, watched, rating)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, tmdb_id) DO UPDATE SET
                favorite = excluded.favorite, watched = excluded.watched,
                rating = excluded.rating, updated_at = CURRENT_TIMESTAMP
            ''',
            (user_id, movie['tmdbID'], int(favorite), int(watched), rating),
        )
        connection.commit()
    finally:
        connection.close()
    return get_user_library(database_path, user_id)[movie['tmdbID']]


# w Cria, atualiza ou remove a review do filme do usuário autenticado.
def save_user_review(database_path: Path, user_id: int, movie: dict[str, Any], review: str) -> None:
    _require_movie(movie)
    review = review.strip()
    if len(review) > 2000:
        raise ValueError('A review não pode ultrapassar 2.000 caracteres.')

    connection = get_connection(database_path)
    try:
        _upsert_movie(connection, movie)
        if review:
            connection.execute(
                '''
                INSERT INTO reviews (user_id, tmdb_id, body) VALUES (?, ?, ?)
                ON CONFLICT(user_id, tmdb_id) DO UPDATE SET
                    body = excluded.body, updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, movie['tmdbID'], review),
            )
        else:
            connection.execute(
                'DELETE FROM reviews WHERE user_id = ? AND tmdb_id = ?',
                (user_id, movie['tmdbID']),
            )
        connection.commit()
    finally:
        connection.close()
