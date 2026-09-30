import os
from pathlib import Path


# w Lê a chave do TMDb exclusivamente do ambiente.
def get_tmdb_api_key() -> str:
    # w Remove espaços acidentais colados junto com o token.
    api_key = os.environ.get('TMDB_API_KEY', '').strip()
    if api_key:
        return api_key
    raise RuntimeError(
        'TMDB_API_KEY não configurada. '
        'Defina essa variável de ambiente antes de iniciar a aplicação.'
    )


# w Mantém as configurações externas da aplicação em um único lugar.
TMDB_API_KEY = get_tmdb_api_key()
TMDB_URL = 'https://api.themoviedb.org/3'
CACHE_DIR = Path(__file__).parent / 'cache' / 'posters'
DATABASE_PATH = Path(__file__).parent / 'data' / 'app.sqlite3'
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'local-development-secret')
