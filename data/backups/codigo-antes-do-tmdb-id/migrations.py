import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from database import SCHEMA_STATEMENTS, SCHEMA_VERSION, get_connection


# w Copia o banco com a API de backup do SQLite, que gera uma cópia consistente.
def backup_database(database_path: Path, backup_dir: Path, label: str) -> Path:
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f'app-{datetime.now():%Y%m%d-%H%M%S}-{label}.sqlite3'
    source = sqlite3.connect(database_path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


# w Consulta o TMDb para todos os filmes antes de alterar o banco; qualquer falha interrompe tudo.
def _resolve_tmdb_ids(
    connection: sqlite3.Connection,
    find_tmdb_id: Callable[[str], int | None],
) -> dict[str, int]:
    tmdb_ids: dict[str, int] = {}
    missing = []
    for row in connection.execute('SELECT imdb_id, title FROM movies ORDER BY title').fetchall():
        tmdb_id = find_tmdb_id(row['imdb_id'])
        if tmdb_id is None:
            missing.append(f"{row['title']} ({row['imdb_id']})")
        else:
            tmdb_ids[row['imdb_id']] = tmdb_id
    if missing:
        raise ValueError('O TMDb não encontrou: ' + ', '.join(missing) + '.')
    if len(set(tmdb_ids.values())) != len(tmdb_ids):
        raise ValueError('Dois filmes do banco apontam para o mesmo ID do TMDb.')
    return tmdb_ids


# w Conta as linhas das três tabelas que serão reconstruídas.
def _count_rows(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        for table in ('movies', 'user_movies', 'reviews')
    }


# w Reconstrói as tabelas com tmdb_id em uma única transação: ou tudo funciona, ou nada muda.
def _rebuild_tables(connection: sqlite3.Connection, tmdb_ids: dict[str, int]) -> dict[str, int]:
    # w O Python não abre transações sozinho para comandos DDL, então o controle fica manual.
    connection.isolation_level = None
    connection.execute('PRAGMA foreign_keys = OFF')
    connection.execute('BEGIN IMMEDIATE')
    try:
        orphans_removed = 0
        for table in ('user_movies', 'reviews'):
            orphans_removed += connection.execute(
                f'DELETE FROM {table} WHERE user_id NOT IN (SELECT id FROM users)'
            ).rowcount
        before = _count_rows(connection)

        for table in ('movies', 'user_movies', 'reviews'):
            connection.execute(f'CREATE TABLE {table}_old AS SELECT * FROM {table}')
        for table in ('reviews', 'user_movies', 'movies'):
            connection.execute(f'DROP TABLE {table}')
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        connection.execute(
            'CREATE TEMP TABLE tmdb_map (imdb_id TEXT PRIMARY KEY, tmdb_id INTEGER NOT NULL)'
        )
        connection.executemany('INSERT INTO tmdb_map VALUES (?, ?)', tmdb_ids.items())
        connection.execute(
            '''
            INSERT INTO movies (
                tmdb_id, imdb_id, title, year, media_type,
                poster_url, cached_poster_path, genre, created_at
            )
            SELECT
                map.tmdb_id, m.imdb_id, m.title, m.year, m.media_type,
                m.poster_url, m.cached_poster_path, m.genre, m.created_at
            FROM movies_old m
            JOIN tmdb_map map ON map.imdb_id = m.imdb_id
            '''
        )
        connection.execute(
            '''
            INSERT INTO user_movies (
                user_id, tmdb_id, favorite, watched, rating, created_at, updated_at
            )
            SELECT
                um.user_id, map.tmdb_id, um.favorite, um.watched, um.rating,
                um.created_at, um.updated_at
            FROM user_movies_old um
            JOIN tmdb_map map ON map.imdb_id = um.imdb_id
            '''
        )
        connection.execute(
            '''
            INSERT INTO reviews (id, user_id, tmdb_id, body, created_at, updated_at)
            SELECT r.id, r.user_id, map.tmdb_id, r.body, r.created_at, r.updated_at
            FROM reviews_old r
            JOIN tmdb_map map ON map.imdb_id = r.imdb_id
            '''
        )
        for table in ('movies_old', 'user_movies_old', 'reviews_old', 'tmdb_map'):
            connection.execute(f'DROP TABLE {table}')

        # w Antes de confirmar, nenhuma linha pode ter se perdido e nenhuma chave pode estar quebrada.
        after = _count_rows(connection)
        if after != before:
            raise ValueError(f'A contagem de linhas mudou na migração: {before} -> {after}.')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('A migração deixaria chaves estrangeiras inválidas.')

        connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        connection.execute('COMMIT')
        return {**after, 'orphans_removed': orphans_removed}
    except Exception:
        if connection.in_transaction:
            connection.execute('ROLLBACK')
        raise
    finally:
        connection.execute('PRAGMA foreign_keys = ON')


# w Converte o banco antigo (imdb_id como chave) para o schema com tmdb_id, com backup opcional.
def migrate_to_tmdb_ids(
    database_path: Path,
    find_tmdb_id: Callable[[str], int | None],
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    connection = get_connection(database_path)
    try:
        if connection.execute('PRAGMA user_version').fetchone()[0] >= SCHEMA_VERSION:
            return {'status': 'already_migrated'}
        tmdb_ids = _resolve_tmdb_ids(connection, find_tmdb_id)
        backup = None
        if backup_dir is not None:
            backup = backup_database(database_path, backup_dir, 'antes-do-tmdb-id')
        counts = _rebuild_tables(connection, tmdb_ids)
        return {'status': 'migrated', 'backup': backup, **counts}
    finally:
        connection.close()
