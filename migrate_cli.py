import sys

from config import DATABASE_PATH, TMDB_API_KEY, TMDB_URL
from database import SCHEMA_VERSION, get_connection
from migrations import _resolve_tmdb_ids, migrate_to_tmdb_ids
from services.tmdb_service import TmdbService, TmdbServiceError

BACKUP_DIR = DATABASE_PATH.parent / 'backups'


# w Mostra o mapeamento título -> tmdb_id e só migra o banco real com confirmação explícita.
def main() -> int:
    connection = get_connection(DATABASE_PATH)
    try:
        has_movies = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'movies'"
        ).fetchone()
        current_version = connection.execute('PRAGMA user_version').fetchone()[0]
    finally:
        connection.close()

    if not has_movies:
        print('Nenhum banco existente encontrado; ele será criado automaticamente ao iniciar a aplicação.')
        return 0

    if current_version >= SCHEMA_VERSION:
        print('O banco já está no schema atual (tmdb_id). Nada a fazer.')
        return 0

    print('Banco no schema antigo (chave imdb_id) detectado.')
    print('Consultando o TMDb para descobrir o tmdb_id de cada filme...')
    tmdb_service = TmdbService(TMDB_API_KEY, TMDB_URL)

    connection = get_connection(DATABASE_PATH)
    try:
        try:
            tmdb_ids = _resolve_tmdb_ids(connection, tmdb_service.find_tmdb_id)
        except (ValueError, TmdbServiceError) as error:
            print(f'Não foi possível migrar: {error}')
            return 1
        movies = connection.execute('SELECT imdb_id, title FROM movies ORDER BY title').fetchall()
    finally:
        connection.close()

    print('\nTítulo -> tmdb_id')
    for row in movies:
        print(f"  {row['title']} -> {tmdb_ids[row['imdb_id']]}")

    answer = input('\nConfirma a migração do banco para tmdb_id? (s/N) ').strip().lower()
    if answer != 's':
        print('Migração cancelada. Nada foi alterado.')
        return 1

    result = migrate_to_tmdb_ids(DATABASE_PATH, tmdb_service.find_tmdb_id, backup_dir=BACKUP_DIR)
    print(f"\nMigração concluída. Backup salvo em: {result['backup']}")
    print(f"Filmes: {result['movies']} | Vínculos: {result['user_movies']} | Reviews: {result['reviews']}")
    if result['orphans_removed']:
        print(f"Registros órfãos removidos: {result['orphans_removed']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
