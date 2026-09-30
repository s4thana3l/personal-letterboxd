#!/usr/bin/env python3
"""
Script para migrar dados de SQLite para PostgreSQL.
Uso: python migrate_data.py <postgresql_url>
Exemplo: python migrate_data.py "postgresql://user:password@host:5432/dbname"
"""

import sqlite3
import psycopg2
from pathlib import Path
import sys


def migrate():
    if len(sys.argv) < 2:
        print("Erro: Forneça a URL do PostgreSQL")
        print('Uso: python migrate_data.py "postgresql://user:password@host:5432/dbname"')
        sys.exit(1)

    pg_url = sys.argv[1]
    sqlite_path = Path(__file__).parent / 'data' / 'app.sqlite3'

    if not sqlite_path.exists():
        print(f"Erro: Arquivo {sqlite_path} não encontrado")
        sys.exit(1)

    print(f"Conectando ao PostgreSQL...")
    pg_conn = psycopg2.connect(pg_url)
    pg_cursor = pg_conn.cursor()

    print(f"Abrindo SQLite de {sqlite_path}...")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    try:
        # Migrar users
        print("Migrando users...")
        sqlite_cursor.execute('SELECT * FROM users')
        for row in sqlite_cursor.fetchall():
            pg_cursor.execute(
                '''
                INSERT INTO users (id, username, display_name, password_hash, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(id) DO NOTHING
                ''',
                (row['id'], row['username'], row['display_name'], row['password_hash'], row['created_at'])
            )
        pg_conn.commit()
        print("✓ Users migrados")

        # Migrar movies
        print("Migrando movies...")
        sqlite_cursor.execute('SELECT * FROM movies')
        for row in sqlite_cursor.fetchall():
            pg_cursor.execute(
                '''
                INSERT INTO movies (
                    tmdb_id, imdb_id, title, year, media_type, poster_url,
                    cached_poster_path, genre, public_rating, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(tmdb_id) DO NOTHING
                ''',
                (
                    row['tmdb_id'], row['imdb_id'], row['title'], row['year'],
                    row['media_type'], row['poster_url'], row['cached_poster_path'],
                    row['genre'], row['public_rating'], row['created_at']
                )
            )
        pg_conn.commit()
        print("✓ Movies migrados")

        # Migrar user_movies
        print("Migrando user_movies...")
        sqlite_cursor.execute('SELECT * FROM user_movies')
        for row in sqlite_cursor.fetchall():
            pg_cursor.execute(
                '''
                INSERT INTO user_movies (
                    user_id, tmdb_id, favorite, watched, rating, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(user_id, tmdb_id) DO NOTHING
                ''',
                (
                    row['user_id'], row['tmdb_id'], row['favorite'], row['watched'],
                    row['rating'], row['created_at'], row['updated_at']
                )
            )
        pg_conn.commit()
        print("✓ User_movies migrados")

        # Migrar reviews
        print("Migrando reviews...")
        sqlite_cursor.execute('SELECT * FROM reviews')
        for row in sqlite_cursor.fetchall():
            pg_cursor.execute(
                '''
                INSERT INTO reviews (id, user_id, tmdb_id, body, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(id) DO NOTHING
                ''',
                (row['id'], row['user_id'], row['tmdb_id'], row['body'], row['created_at'], row['updated_at'])
            )
        pg_conn.commit()
        print("✓ Reviews migrados")

        print("\n✅ Migração concluída com sucesso!")

    except Exception as e:
        pg_conn.rollback()
        print(f"\n❌ Erro durante migração: {e}")
        sys.exit(1)
    finally:
        sqlite_cursor.close()
        sqlite_conn.close()
        pg_cursor.close()
        pg_conn.close()


if __name__ == '__main__':
    migrate()
