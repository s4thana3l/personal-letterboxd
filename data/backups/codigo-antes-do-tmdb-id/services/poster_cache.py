import requests
from pathlib import Path


# Centraliza a lógica de cache e download de posters para manter o backend mais limpo.
class PosterCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # Retorna o caminho em disco do poster associado a um filme.
    def get_path(self, imdb_id: str) -> Path:
        return self.cache_dir / f'{imdb_id}.jpg'

    # Salva o poster na pasta de cache quando ele ainda não existe.
    def download_if_missing(self, imdb_id: str, poster_url: str) -> str | None:
        if not poster_url or poster_url == 'N/A':
            return None
        target = self.get_path(imdb_id)
        if target.exists():
            return f'/cache/{target.name}'
        try:
            response = requests.get(poster_url, timeout=12)
            response.raise_for_status()
            target.write_bytes(response.content)
            return f'/cache/{target.name}'
        except requests.RequestException:
            return None

    # Adiciona o campo interno do poster ao JSON do filme quando o download for bem-sucedido.
    def attach_to_movie(self, movie: dict, imdb_id: str) -> dict:
        poster_url = movie.get('Poster')
        poster_path = self.download_if_missing(imdb_id, poster_url)
        if poster_path:
            movie['_poster'] = poster_path
        return movie
