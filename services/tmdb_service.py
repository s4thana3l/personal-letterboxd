import re

import requests
import truststore


# w Usa os certificados confiáveis do Windows, incluindo certificados de proxy corporativo.
truststore.inject_into_ssl()


# w Representa falhas de comunicação ou respostas inválidas do TMDb.
class TmdbServiceError(Exception):
    pass


class TmdbService:
    def __init__(self, api_key: str, base_url: str, timeout: int = 8):
        # w Normaliza o token para evitar falhas causadas por espaços ao colar.
        api_key = (api_key or '').strip()
        if not api_key:
            raise ValueError('TMDB_API_KEY não configurada.')
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    # w Valida o texto antes de enviá-lo ao endpoint de busca.
    def validate_query(self, query: str) -> str:
        cleaned = (query or '').strip()
        if not cleaned:
            raise ValueError('A busca não pode ficar vazia.')
        if len(cleaned) < 2:
            raise ValueError('Digite pelo menos 2 caracteres para buscar.')
        if len(cleaned) > 100:
            raise ValueError('A busca excedeu o limite de 100 caracteres.')
        return cleaned

    # w Mantém o mesmo formato de validação usado pelo provedor atual.
    def validate_imdb_id(self, imdb_id: str) -> str:
        cleaned = (imdb_id or '').strip()
        if not re.fullmatch(r'tt\d{7,8}', cleaned):
            raise ValueError('ID do filme inválido.')
        return cleaned

    # w Busca filmes por título e normaliza os campos principais para a aplicação.
    def search(self, query: str) -> list[dict]:
        response = self._request('/search/movie', {'query': query})
        return [self._normalize_search_result(movie) for movie in response.get('results', [])]

    # w Busca pessoas para permitir a futura seleção de diretores e atores.
    def search_people(self, query: str) -> list[dict]:
        response = self._request('/search/person', {'query': query})
        return [
            {
                'tmdbID': person.get('id'),
                'name': person.get('name'),
                'known_for_department': person.get('known_for_department'),
            }
            for person in response.get('results', [])
        ]

    # w Descobre filmes dirigidos por uma pessoa usando o ID do TMDb.
    def discover_by_director(self, person_id: int) -> list[dict]:
        response = self._request('/discover/movie', {'with_crew': person_id})
        return [self._normalize_search_result(movie) for movie in response.get('results', [])]

    # w Descobre o ID do TMDb de um IMDb ID antigo com uma única chamada.
    def find_tmdb_id(self, imdb_id: str) -> int | None:
        found = self._request(
            f'/find/{self.validate_imdb_id(imdb_id)}',
            {'external_source': 'imdb_id'},
        )
        matches = found.get('movie_results', [])
        return matches[0]['id'] if matches else None

    # w Busca detalhes por IMDb usando o endpoint de identificação externa do TMDb.
    def get_movie(self, imdb_id: str) -> dict | None:
        tmdb_id = self.find_tmdb_id(imdb_id)
        if tmdb_id is None:
            return None
        return self.get_movie_by_tmdb_id(tmdb_id, imdb_id)

    # w Busca detalhes completos e mantém o IMDb ID para compatibilidade gradual.
    def get_movie_by_tmdb_id(self, tmdb_id: int, imdb_id: str | None = None) -> dict:
        movie = self._request(
            f'/movie/{tmdb_id}',
            {'append_to_response': 'credits,external_ids'},
        )
        movie['poster_path'] = self._default_poster_path(tmdb_id) or movie.get('poster_path')
        return self._normalize_movie(movie, imdb_id)

    # w Converte o formato TMDb para os campos que a aplicação já conhece.
    def _normalize_search_result(self, movie: dict) -> dict:
        release_date = movie.get('release_date') or ''
        return {
            'tmdbID': movie.get('id'),
            'imdbID': movie.get('imdb_id'),
            'Title': movie.get('title') or movie.get('original_title'),
            'Year': release_date[:4] or 'N/A',
            'Type': 'movie',
            'Poster': self._poster_url(movie.get('poster_path')),
            'public_rating': movie.get('vote_average'),
            'vote_count': movie.get('vote_count'),
            'provider': 'tmdb',
        }

    # w Combina detalhes, créditos e nota pública em um formato estável.
    def _normalize_movie(self, movie: dict, imdb_id: str | None) -> dict:
        crew = movie.get('credits', {}).get('crew', [])
        directors = [person['name'] for person in crew if person.get('job') == 'Director']
        return {
            'tmdbID': movie.get('id'),
            'imdbID': imdb_id or movie.get('external_ids', {}).get('imdb_id'),
            'Title': movie.get('title') or movie.get('original_title'),
            'Year': (movie.get('release_date') or '')[:4] or 'N/A',
            'Type': 'movie',
            'Poster': self._poster_url(movie.get('poster_path')),
            'Genre': ', '.join(genre['name'] for genre in movie.get('genres', [])),
            'Runtime': f"{movie['runtime']} min" if movie.get('runtime') else None,
            'Director': ', '.join(directors),
            'Plot': movie.get('overview'),
            'public_rating': movie.get('vote_average'),
            'vote_count': movie.get('vote_count'),
            'provider': 'tmdb',
        }

    # w Busca o poster que o TMDb escolhe por padrão para en-US: o pôster oficial de divulgação,
    # w e não a arte alternativa/fã-feita que às vezes fica marcada como "sem idioma" nas imagens,
    # w nem a versão trocada especificamente para pt-BR (idioma padrão usado no restante da app).
    def _default_poster_path(self, tmdb_id: int) -> str | None:
        try:
            return self._request(f'/movie/{tmdb_id}', {'language': 'en-US'}).get('poster_path')
        except TmdbServiceError:
            return None

    # w Monta URLs de poster somente quando a API devolve um caminho válido.
    @staticmethod
    def _poster_url(path: str | None) -> str | None:
        return f'https://image.tmdb.org/t/p/w500{path}' if path else None

    # w Centraliza autenticação, timeout e tradução de falhas externas.
    def _request(self, path: str, params: dict) -> dict:
        try:
            response = requests.get(
                f'{self.base_url}{path}',
                params={'language': 'pt-BR', **params},
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as error:
            raise TmdbServiceError(
                'Tempo esgotado ao consultar a API TMDb. '
                'Verifique sua conexão ou firewall.'
            ) from error
        except requests.ConnectionError as error:
            raise TmdbServiceError(
                'Não foi possível conectar à API TMDb. '
                'Verifique internet, proxy, DNS ou firewall.'
            ) from error
        except requests.RequestException as error:
            status = getattr(error.response, 'status_code', None)
            detail = f' (HTTP {status})' if status else ''
            raise TmdbServiceError(
                f'Não foi possível consultar a API TMDb{detail}.'
            ) from error
        except ValueError as error:
            raise TmdbServiceError('A API TMDb retornou JSON inválido.') from error
        if not isinstance(payload, dict):
            raise TmdbServiceError('A API TMDb retornou uma resposta inválida.')
        return payload
