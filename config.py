import os
import secrets
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


# w Usa FLASK_SECRET_KEY se foi definida; senão gera uma chave aleatória na primeira execução
# w e reaproveita o mesmo valor depois, para não derrubar sessões abertas a cada reinício.
def get_secret_key(secret_key_path: Path) -> str:
    env_key = os.environ.get('FLASK_SECRET_KEY', '').strip()
    if env_key:
        return env_key
    if secret_key_path.exists():
        return secret_key_path.read_text(encoding='utf-8').strip()
    secret_key_path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_hex(32)
    secret_key_path.write_text(generated, encoding='utf-8')
    return generated


# w Mantém as configurações externas da aplicação em um único lugar.
TMDB_API_KEY = get_tmdb_api_key()
TMDB_URL = 'https://api.themoviedb.org/3'
CACHE_DIR = Path(__file__).parent / 'cache' / 'posters'
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://user:password@localhost:5432/apifilmes')
SECRET_KEY = get_secret_key(Path(__file__).parent / 'data' / 'secret_key.txt')

# w Interface de rede em que o Flask escuta; 0.0.0.0 permite acesso pela VPN (Etapa 7), não só
# w da própria máquina. Pode ser travado em 127.0.0.1 via env var para voltar ao modo só-local.
HOST = os.environ.get('FLASK_HOST', '0.0.0.0')

# w Quem entra nas estatísticas/atividade "da casa"; outras contas do app ficam de fora dessa comparação.
HOUSEHOLD_USERNAMES = ('Nathan', 'lannie', 'karmageddon')

# w Porta em que o Flask escuta; padrão 5000 em dev, 8080 em produção (Fly.io).
PORT = int(os.environ.get('FLASK_PORT', '5000'))
