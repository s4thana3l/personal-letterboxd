import sys
from pathlib import Path

from config import CACHE_DIR, DATABASE_PATH
from database import get_connection


# w Reúne as chaves (tmdb_id e imdb_id) de todos os filmes que ainda existem no banco.
def _valid_keys(database_path: Path) -> set[str]:
    connection = get_connection(database_path)
    try:
        rows = connection.execute('SELECT tmdb_id, imdb_id FROM movies').fetchall()
    finally:
        connection.close()
    keys = set()
    for row in rows:
        keys.add(str(row['tmdb_id']))
        if row['imdb_id']:
            keys.add(row['imdb_id'])
    return keys


# w Mostra os posters sem filme correspondente no banco e só apaga com confirmação explícita.
def main() -> int:
    valid_keys = _valid_keys(DATABASE_PATH)
    orphans = [
        path for path in sorted(CACHE_DIR.glob('*.jpg'))
        if path.stem not in valid_keys
    ]

    if not orphans:
        print('Nenhum poster órfão encontrado no cache.')
        return 0

    total_size = sum(path.stat().st_size for path in orphans)
    print(f'{len(orphans)} poster(s) órfão(s) encontrado(s) ({total_size / 1024:.0f} KB):')
    for path in orphans:
        print(f'  {path.name}')

    # w Remove um BOM que alguns terminais inserem ao repassar texto por pipe.
    answer = input('\nConfirma a remoção desses arquivos? (s/N) ').strip().lstrip('﻿').lower()
    if answer != 's':
        print('Limpeza cancelada. Nada foi alterado.')
        return 1

    for path in orphans:
        path.unlink()
    print(f'{len(orphans)} poster(s) removido(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
