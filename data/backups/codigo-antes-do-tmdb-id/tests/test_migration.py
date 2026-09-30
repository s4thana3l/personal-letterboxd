import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import init_database
from migrations import migrate_to_tmdb_ids

# w Schema antigo (imdb_id como chave), mantido aqui para simular um banco ainda não migrado.
OLD_SCHEMA = '''
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE movies (
    imdb_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    year TEXT,
    media_type TEXT,
    poster_url TEXT,
    cached_poster_path TEXT,
    genre TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE user_movies (
    user_id INTEGER NOT NULL,
    imdb_id TEXT NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
    watched INTEGER NOT NULL DEFAULT 0 CHECK (watched IN (0, 1)),
    rating REAL CHECK (
        rating IS NULL
        OR (rating >= 0 AND rating <= 5 AND rating * 2 = CAST(rating * 2 AS INTEGER))
    ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, imdb_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (imdb_id) REFERENCES movies(imdb_id) ON DELETE CASCADE
);
CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    imdb_id TEXT NOT NULL,
    body TEXT NOT NULL CHECK (length(trim(body)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, imdb_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (imdb_id) REFERENCES movies(imdb_id) ON DELETE CASCADE
);
'''

TMDB_IDS = {'tt0092991': 765, 'tt0069089': 20000}


# w Monta um banco antigo com dados válidos e com as linhas órfãs do usuário removido (id 1).
def build_old_database(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(OLD_SCHEMA)
        connection.executescript(
            '''
            INSERT INTO users (id, username, display_name, password_hash)
            VALUES (3, 'Nathan', 'Nathan', 'hash-nathan'), (6, 'lannie', 'lannie', 'hash-lannie');
            INSERT INTO movies (imdb_id, title, year, media_type, poster_url, cached_poster_path, genre)
            VALUES
                ('tt0092991', 'Evil Dead II', '1987', 'movie', 'https://x/e.jpg', '/cache/tt0092991.jpg', 'Comedy, Horror'),
                ('tt0069089', 'Pink Flamingos', '1976', 'movie', NULL, NULL, NULL);
            INSERT INTO user_movies (user_id, imdb_id, favorite, watched, rating)
            VALUES (3, 'tt0092991', 1, 1, 4.5), (6, 'tt0069089', 1, 0, NULL);
            INSERT INTO reviews (id, user_id, imdb_id, body)
            VALUES (10, 3, 'tt0092991', 'Um clássico.');
            INSERT INTO user_movies (user_id, imdb_id, favorite, watched, rating)
            VALUES (1, 'tt0092991', 1, 1, 4.5);
            INSERT INTO reviews (id, user_id, imdb_id, body)
            VALUES (11, 1, 'tt0092991', 'Review órfã.');
            '''
        )
        connection.commit()
    finally:
        connection.close()


# w Executa uma consulta e fecha a conexão, para o Windows conseguir apagar o arquivo depois.
def query(database_path: Path, sql: str) -> list[tuple]:
    connection = sqlite3.connect(database_path)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.database_path = self.directory / 'app.sqlite3'
        self.backup_dir = self.directory / 'backups'
        build_old_database(self.database_path)

    # w Confirma que o banco continua no schema antigo, com as órfãs e sem backup.
    def assert_database_untouched(self):
        self.assertEqual(query(self.database_path, 'PRAGMA user_version'), [(0,)])
        self.assertEqual(query(self.database_path, 'SELECT COUNT(*) FROM reviews'), [(2,)])
        columns = [row[1] for row in query(self.database_path, 'PRAGMA table_info(movies)')]
        self.assertIn('imdb_id', columns)
        self.assertNotIn('tmdb_id', columns)
        self.assertFalse(self.backup_dir.exists())

    # w Verifica que dados, notas, reviews e IDs são preservados e as órfãs são removidas.
    def test_migration_moves_data_to_tmdb_ids(self):
        result = migrate_to_tmdb_ids(self.database_path, TMDB_IDS.get, self.backup_dir)

        self.assertEqual(result['status'], 'migrated')
        self.assertEqual(
            {key: result[key] for key in ('movies', 'user_movies', 'reviews', 'orphans_removed')},
            {'movies': 2, 'user_movies': 2, 'reviews': 1, 'orphans_removed': 2},
        )
        self.assertEqual(
            query(self.database_path, 'SELECT tmdb_id, imdb_id, title, cached_poster_path FROM movies ORDER BY tmdb_id'),
            [(765, 'tt0092991', 'Evil Dead II', '/cache/tt0092991.jpg'), (20000, 'tt0069089', 'Pink Flamingos', None)],
        )
        self.assertEqual(
            query(self.database_path, 'SELECT user_id, tmdb_id, favorite, watched, rating FROM user_movies ORDER BY user_id'),
            [(3, 765, 1, 1, 4.5), (6, 20000, 1, 0, None)],
        )
        self.assertEqual(
            query(self.database_path, 'SELECT id, user_id, tmdb_id, body FROM reviews'),
            [(10, 3, 765, 'Um clássico.')],
        )
        self.assertEqual(query(self.database_path, 'PRAGMA user_version'), [(2,)])
        self.assertEqual(query(self.database_path, 'PRAGMA foreign_key_check'), [])

    # w Verifica que o backup guardado é o banco de antes da migração.
    def test_migration_creates_backup_of_old_database(self):
        result = migrate_to_tmdb_ids(self.database_path, TMDB_IDS.get, self.backup_dir)

        backup = result['backup']
        self.assertTrue(backup.exists())
        self.assertEqual(query(backup, 'SELECT COUNT(*) FROM reviews'), [(2,)])
        columns = [row[1] for row in query(backup, 'PRAGMA table_info(movies)')]
        self.assertIn('imdb_id', columns)
        self.assertNotIn('tmdb_id', columns)

    # w Verifica que o novo schema aceita vários filmes sem IMDb ID.
    def test_migrated_schema_accepts_movies_without_imdb_id(self):
        migrate_to_tmdb_ids(self.database_path, TMDB_IDS.get)

        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("INSERT INTO movies (tmdb_id, title) VALUES (901, 'Sem IMDb A')")
            connection.execute("INSERT INTO movies (tmdb_id, title) VALUES (902, 'Sem IMDb B')")
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(query(self.database_path, 'SELECT COUNT(*) FROM movies WHERE imdb_id IS NULL'), [(2,)])

    # w Verifica que um filme não encontrado no TMDb interrompe a migração sem alterar o banco.
    def test_migration_stops_when_movie_not_found(self):
        with self.assertRaisesRegex(ValueError, 'Pink Flamingos'):
            migrate_to_tmdb_ids(self.database_path, {'tt0092991': 765}.get, self.backup_dir)
        self.assert_database_untouched()

    # w Verifica que uma falha de rede interrompe a migração sem alterar o banco.
    def test_migration_stops_when_lookup_fails(self):
        def failing_lookup(imdb_id):
            raise RuntimeError('rede indisponível')

        with self.assertRaisesRegex(RuntimeError, 'rede indisponível'):
            migrate_to_tmdb_ids(self.database_path, failing_lookup, self.backup_dir)
        self.assert_database_untouched()

    # w Verifica que dois filmes com o mesmo ID do TMDb são recusados.
    def test_migration_rejects_duplicate_tmdb_ids(self):
        with self.assertRaisesRegex(ValueError, 'mesmo ID'):
            migrate_to_tmdb_ids(self.database_path, lambda imdb_id: 765, self.backup_dir)
        self.assert_database_untouched()

    # w Verifica que uma linha que se perderia na conversão desfaz tudo, inclusive a limpeza das órfãs.
    def test_migration_rolls_back_when_row_counts_change(self):
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "INSERT INTO user_movies (user_id, imdb_id) VALUES (3, 'tt9999999')"
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(ValueError, 'contagem de linhas'):
            migrate_to_tmdb_ids(self.database_path, TMDB_IDS.get)

        self.assertEqual(query(self.database_path, 'PRAGMA user_version'), [(0,)])
        self.assertEqual(query(self.database_path, 'SELECT COUNT(*) FROM user_movies'), [(4,)])
        self.assertEqual(query(self.database_path, 'SELECT COUNT(*) FROM reviews'), [(2,)])
        columns = [row[1] for row in query(self.database_path, 'PRAGMA table_info(movies)')]
        self.assertNotIn('tmdb_id', columns)

    # w Verifica que iniciar o app sobre um banco antigo não altera nada, nem as órfãs.
    def test_init_database_leaves_old_database_untouched(self):
        init_database(self.database_path)
        self.assert_database_untouched()
        self.assertEqual(query(self.database_path, 'SELECT COUNT(*) FROM user_movies'), [(3,)])

    # w Verifica que rodar a migração de novo não faz nada nem consulta o TMDb.
    def test_migration_is_idempotent(self):
        migrate_to_tmdb_ids(self.database_path, TMDB_IDS.get)

        def lookup_must_not_run(imdb_id):
            raise AssertionError('O TMDb não deveria ser consultado.')

        second = migrate_to_tmdb_ids(self.database_path, lookup_must_not_run)
        self.assertEqual(second, {'status': 'already_migrated'})


if __name__ == '__main__':
    unittest.main()
