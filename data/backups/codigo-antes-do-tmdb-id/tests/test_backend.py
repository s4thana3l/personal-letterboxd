import importlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from database import (
    SCHEMA_VERSION,
    authenticate_user,
    create_user,
    get_movie,
    init_database,
    save_movie,
)
from services.tmdb_service import TmdbService


class BackendTests(unittest.TestCase):
    # w Verifica se a configuração central lê o token do TMDb.
    def test_config_reads_environment(self):
        original = os.environ.get('TMDB_API_KEY')
        os.environ['TMDB_API_KEY'] = 'test-key'
        try:
            import config
            importlib.reload(config)
            self.assertEqual(config.TMDB_API_KEY, 'test-key')
        finally:
            if original is None:
                os.environ.pop('TMDB_API_KEY', None)
            else:
                os.environ['TMDB_API_KEY'] = original

    # Verifica que a rota de busca retorna sucesso em JSON quando a busca funciona.
    def test_search_route_success(self):
        client = app.app.test_client()
        with patch.object(app.movie_provider, 'search', return_value=[{'Title': 'Batman'}]):
            response = client.get('/api/search?q=batman')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), [{'Title': 'Batman'}])

    # Verifica que consultas muito curtas retornam erro explícito.
    def test_search_route_invalid_query(self):
        client = app.app.test_client()
        response = client.get('/api/search?q=a')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error'], 'invalid_query')

    # Verifica que filmes inexistentes retornam resposta consistente.
    def test_movie_route_not_found(self):
        client = app.app.test_client()
        with patch.object(app.movie_provider, 'get_movie', return_value=None):
            response = client.get('/api/movie/tt0000000')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.get_json()['error'], 'movie_not_found')

    # Verifica que o detalhe do filme continua com poster anexado ao JSON final.
    def test_movie_route_success_and_poster_attachment(self):
        client = app.app.test_client()
        movie = {'Title': 'Batman', 'Poster': 'https://example.com/poster.jpg'}
        with patch.object(app.movie_provider, 'get_movie_by_tmdb_id', return_value=movie):
            with patch.object(app.poster_cache, 'attach_to_movie', return_value={**movie, '_poster': '/cache/test.jpg'}):
                response = client.get('/api/movie/tmdb/1234567')
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual(payload['Title'], 'Batman')
                self.assertEqual(payload['_poster'], '/cache/test.jpg')

    # w Verifica que o adaptador prepara a nota pública para qualquer frontend futuro.
    def test_tmdb_movie_normalization(self):
        movie = app.movie_provider._normalize_movie({
            'id': 765,
            'title': 'Evil Dead II',
            'release_date': '1987-03-13',
            'vote_average': 7.7,
            'vote_count': 3200,
            'external_ids': {'imdb_id': 'tt0092991'},
            'credits': {'crew': []},
        }, None)
        self.assertEqual(movie['provider'], 'tmdb')
        self.assertEqual(movie['public_rating'], 7.7)
        self.assertEqual(movie['vote_count'], 3200)

    # w Verifica a normalização de busca do TMDb sem depender da internet.
    def test_tmdb_search_normalization(self):
        service = TmdbService('test-key', 'https://api.themoviedb.org/3')
        with patch.object(service, '_request', return_value={
            'results': [{
                'id': 765,
                'title': 'Evil Dead II',
                'release_date': '1987-03-13',
                'poster_path': '/evil.jpg',
                'vote_average': 7.7,
                'vote_count': 3200,
            }],
        }):
            result = service.search('Evil Dead II')
        self.assertEqual(result[0]['tmdbID'], 765)
        self.assertEqual(result[0]['public_rating'], 7.7)
        self.assertEqual(result[0]['vote_count'], 3200)

    # w Verifica que o ID do TMDb é localizado a partir de um IMDb ID antigo.
    def test_tmdb_find_id(self):
        service = TmdbService('test-key', 'https://api.themoviedb.org/3')
        with patch.object(service, '_request', return_value={'movie_results': [{'id': 765}]}):
            self.assertEqual(service.find_tmdb_id('tt0092991'), 765)
        with patch.object(service, '_request', return_value={'movie_results': []}):
            self.assertIsNone(service.find_tmdb_id('tt0092991'))
        with self.assertRaises(ValueError):
            service.find_tmdb_id('invalido')

    # w Verifica que o diagnóstico informa quando o token TMDb ainda não foi configurado.
    def test_tmdb_test_route_without_key(self):
        client = app.app.test_client()
        with client.session_transaction() as active_session:
            active_session['user_id'] = 1
        with patch.object(app, 'tmdb_service', None):
            response = client.get('/api/tmdb-test?q=Sam+Raimi')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['error'], 'tmdb_not_configured')

    # w Verifica que falhas HTTP do provedor ficam identificáveis sem revelar o token.
    def test_tmdb_http_error_has_status(self):
        service = TmdbService('test-key', 'https://api.themoviedb.org/3')
        response = type('Response', (), {'status_code': 401})()
        error = __import__('requests').HTTPError(response=response)
        with patch('services.tmdb_service.requests.get', side_effect=error):
            with self.assertRaisesRegex(Exception, 'HTTP 401'):
                service.search('Sam Raimi')

    # w Verifica que falhas de rede explicam o próximo diagnóstico sem revelar segredos.
    def test_tmdb_connection_error_is_explicit(self):
        service = TmdbService('test-key', 'https://api.themoviedb.org/3')
        error = __import__('requests').ConnectionError('connection refused')
        with patch('services.tmdb_service.requests.get', side_effect=error):
            with self.assertRaisesRegex(Exception, 'internet, proxy, DNS ou firewall'):
                service.search('Sam Raimi')

    # w Verifica que um token realista é enviado sem desativar a validação HTTPS.
    def test_tmdb_request_keeps_tls_verification_enabled(self):
        service = TmdbService('real-test-token', 'https://api.themoviedb.org/3')
        response = type('Response', (), {
            'raise_for_status': lambda self: None,
            'json': lambda self: {'results': []},
        })()
        with patch('services.tmdb_service.requests.get', return_value=response) as request:
            service.search('Batman')
        self.assertNotIn('verify', request.call_args.kwargs)
    # Verifica que as páginas pessoais possuem URLs próprias.
    def test_collection_pages(self):
        client = app.app.test_client()
        with client.session_transaction() as active_session:
            active_session['user_id'] = 1
        self.assertEqual(client.get('/').status_code, 302)
        self.assertEqual(client.get('/').location, '/home')
        self.assertEqual(client.get('/home').status_code, 200)
        self.assertEqual(client.get('/favoritos').status_code, 200)
        self.assertEqual(client.get('/assistidos').status_code, 200)
        self.assertEqual(client.get('/reviews').status_code, 404)

    # w Verifica login, comparação case-insensitive do usuário e senha case-sensitive.
    def test_login(self):
        client = app.app.test_client()
        response = client.post('/login', data={'username': 'nAtHaN', 'password': 'nathan'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/home')
        wrong_password = client.post('/login', data={'username': 'Nathan', 'password': 'Nathan'})
        self.assertEqual(wrong_password.status_code, 401)

    # w Verifica cadastro, login automático e rejeição de usuário duplicado.
    def test_register(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                client = app.app.test_client()
                response = client.post('/register', data={
                    'username': 'ParceiroUm',
                    'password': 'segredo',
                    'password_confirmation': 'segredo',
                })
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, '/home')
                duplicate = client.post('/register', data={
                    'username': 'parceiroum',
                    'password': 'outro',
                    'password_confirmation': 'outro',
                })
                self.assertEqual(duplicate.status_code, 400)
                self.assertIsNotNone(authenticate_user(database_path, 'PARCEIROUM', 'segredo'))

    # w Verifica que a primeira versão do schema cria as relações necessárias.
    def test_database_schema(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            connection = sqlite3.connect(database_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()
            self.assertTrue({'users', 'movies', 'user_movies', 'reviews'} <= tables)

    # w Verifica que um banco novo usa tmdb_id como chave e que iniciar de novo não apaga dados.
    def test_init_database_creates_tmdb_schema(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            connection = sqlite3.connect(database_path)
            try:
                columns = {row[1]: row[5] for row in connection.execute('PRAGMA table_info(movies)')}
                self.assertEqual(columns['tmdb_id'], 1)
                self.assertEqual(columns['imdb_id'], 0)
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)

                connection.execute("INSERT INTO movies (tmdb_id, title) VALUES (765, 'Evil Dead II')")
                connection.commit()
            finally:
                connection.close()

            init_database(database_path)
            connection = sqlite3.connect(database_path)
            try:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM movies').fetchone()[0], 1)
            finally:
                connection.close()

    # w Verifica que filmes podem ser salvos e atualizados no SQLite.
    def test_database_movie_repository(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            movie = {
                'imdbID': 'tt0092991',
                'Title': 'Evil Dead II',
                'Year': '1987',
                'Type': 'movie',
                'Poster': 'https://example.com/evil-dead-2.jpg',
                '_poster': '/cache/tt0092991.jpg',
                'Genre': 'Comedy, Horror',
            }

            save_movie(database_path, movie)
            save_movie(database_path, {**movie, 'Title': 'Evil Dead II atualizado'})

            stored_movie = get_movie(database_path, movie['imdbID'])
            self.assertEqual(stored_movie['Title'], 'Evil Dead II atualizado')
            self.assertEqual(stored_movie['_poster'], '/cache/tt0092991.jpg')


if __name__ == '__main__':
    unittest.main()
