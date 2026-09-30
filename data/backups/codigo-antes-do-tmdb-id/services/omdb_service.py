import re

import requests


# Representa uma falha ao consultar ou interpretar a API OMDb.
class OmdbServiceError(Exception):
    pass


class OmdbService:
    def __init__(self, api_key: str, base_url: str, timeout: int = 8):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    # Valida e padroniza a string usada na busca do usuário.
    def validate_query(self, query: str) -> str:
        cleaned = (query or '').strip()
        if not cleaned:
            raise ValueError('A busca não pode ficar vazia.')
        if len(cleaned) < 2:
            raise ValueError('Digite pelo menos 2 caracteres para buscar.')
        if len(cleaned) > 100:
            raise ValueError('A busca excedeu o limite de 100 caracteres.')
        return cleaned

    # Valida o identificador IMDb antes de consultar os detalhes do filme.
    def validate_imdb_id(self, imdb_id: str) -> str:
        cleaned = (imdb_id or '').strip()
        if not cleaned:
            raise ValueError('ID do filme não informado.')
        if not re.fullmatch(r'tt\d{7,8}', cleaned):
            raise ValueError('ID do filme inválido.')
        return cleaned

    # Busca títulos na API OMDb usando o texto informado pelo usuário.
    def search(self, query: str) -> list[dict]:
        response = self._request({'s': query}, self.timeout)
        if response.get('Response', 'False') != 'True':
            return []
        return response.get('Search', [])

    # Busca todos os detalhes de um filme pelo identificador IMDb.
    def get_movie(self, imdb_id: str) -> dict | None:
        response = self._request(
            {'i': imdb_id, 'plot': 'full'},
            self.timeout + 2,
        )
        if response.get('Response', 'False') != 'True':
            return None
        return self._normalize_movie(response)

    # w Converte campos específicos do OMDb para nomes que outros provedores poderão reutilizar.
    def _normalize_movie(self, movie: dict) -> dict:
        normalized = {
            **movie,
            'provider': 'omdb',
            'public_rating': self._parse_rating(movie.get('imdbRating')),
            'vote_count': self._parse_integer(movie.get('imdbVotes')),
        }
        return normalized

    # w Converte uma nota externa inválida em ausência de nota, sem inventar valores.
    @staticmethod
    def _parse_rating(value: object) -> float | None:
        try:
            rating = float(value)
        except (TypeError, ValueError):
            return None
        return rating if 0 <= rating <= 10 else None

    # w Converte a quantidade de votos formatada pelo OMDb para um número simples.
    @staticmethod
    def _parse_integer(value: object) -> int | None:
        if not isinstance(value, str):
            return None
        digits = value.replace(',', '').strip()
        return int(digits) if digits.isdigit() else None

    # Faz uma requisição autenticada e transforma falhas técnicas em erro do serviço.
    def _request(self, params: dict, timeout: int) -> dict:
        params_with_key = {'apikey': self.api_key, **params}
        try:
            response = requests.get(
                self.base_url,
                params=params_with_key,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            raise OmdbServiceError('Não foi possível consultar a API OMDb.') from error
