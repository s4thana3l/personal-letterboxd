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
    change_user_password,
    create_user,
    delete_user_account,
    get_household_activity,
    get_household_statistics,
    get_movie,
    get_user_activity,
    get_user_library,
    get_user_statistics,
    get_user_profile,
    init_database,
    save_movie,
    save_user_movie_state,
    save_user_review,
    update_display_name,
)
from services.tmdb_service import TmdbService, TmdbServiceError


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

    # w Verifica que a secret key é gerada e salva na primeira vez, e reaproveitada depois
    # w (sessões não podem cair a cada reinício), e que FLASK_SECRET_KEY sempre tem prioridade.
    def test_get_secret_key_persists_and_respects_env_override(self):
        import config
        with tempfile.TemporaryDirectory() as temporary_directory:
            secret_key_path = Path(temporary_directory) / 'secret_key.txt'
            self.assertFalse(secret_key_path.exists())

            first = config.get_secret_key(secret_key_path)
            self.assertTrue(secret_key_path.exists())
            self.assertEqual(len(first), 64)

            second = config.get_secret_key(secret_key_path)
            self.assertEqual(first, second)

            original = os.environ.get('FLASK_SECRET_KEY')
            os.environ['FLASK_SECRET_KEY'] = 'chave-explicita'
            try:
                self.assertEqual(config.get_secret_key(secret_key_path), 'chave-explicita')
            finally:
                if original is None:
                    os.environ.pop('FLASK_SECRET_KEY', None)
                else:
                    os.environ['FLASK_SECRET_KEY'] = original

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

    # w Verifica que a rota busca o filme no TMDb pelo tmdb_id, ignorando qualquer dado enviado pelo cliente.
    def test_library_route_saves_state_using_tmdb_metadata(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                user = create_user(database_path, 'ParceiroCinco', 'segredo')
                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']
                movie = {'tmdbID': 765, 'imdbID': 'tt0092991', 'Title': 'Evil Dead II'}
                with patch.object(app.movie_provider, 'get_movie_by_tmdb_id', return_value=movie):
                    with patch.object(app.poster_cache, 'attach_to_movie', return_value=movie):
                        response = client.put(
                            '/api/library/765',
                            json={'favorite': True, 'watched': False, 'rating': 5, 'movie': {'Title': 'Filme forjado'}},
                        )
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual(payload['Title'], 'Evil Dead II')
                self.assertEqual(payload['favorite'], True)

    # w Verifica que a rota devolve 404 quando o tmdb_id não existe no TMDb.
    def test_library_route_movie_not_found(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                user = create_user(database_path, 'ParceiroSeis', 'segredo')
                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']
                with patch.object(app.movie_provider, 'get_movie_by_tmdb_id', return_value=None):
                    response = client.put('/api/library/999999', json={'favorite': True})
                self.assertEqual(response.status_code, 404)

    # w Verifica que a rota de review também busca o filme no TMDb e permite limpar a review.
    def test_review_route_saves_and_clears_review(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                user = create_user(database_path, 'ParceiroSete', 'segredo')
                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']
                movie = {'tmdbID': 765, 'imdbID': 'tt0092991', 'Title': 'Evil Dead II'}
                with patch.object(app.movie_provider, 'get_movie_by_tmdb_id', return_value=movie):
                    with patch.object(app.poster_cache, 'attach_to_movie', return_value=movie):
                        response = client.put('/api/reviews/765', json={'review': 'Ótimo filme.'})
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.get_json()['review'], 'Ótimo filme.')

                        cleared = client.put('/api/reviews/765', json={'review': ''})
                        self.assertEqual(cleared.status_code, 200)
                        self.assertEqual(cleared.get_json()['review'], '')

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

    # w Verifica que o poster salvo é o padrão em en-US (o pôster oficial de divulgação), não o de
    # w pt-BR nem uma arte alternativa/fã-feita, e que a segunda busca usa language=en-US.
    def test_get_movie_by_tmdb_id_uses_en_us_poster(self):
        service = TmdbService('test-key', 'https://api.themoviedb.org/3')
        responses = {
            'pt-BR': {
                'id': 765,
                'title': 'Uma Noite Alucinante 2',
                'release_date': '1987-03-13',
                'poster_path': '/poster-arte-alternativa.jpg',
                'credits': {'crew': []},
                'external_ids': {'imdb_id': 'tt0092991'},
            },
            'en-US': {'poster_path': '/poster-oficial.jpg'},
        }
        with patch.object(service, '_request', side_effect=lambda path, params: responses[params.get('language', 'pt-BR')]):
            movie = service.get_movie_by_tmdb_id(765)
        self.assertEqual(movie['Poster'], 'https://image.tmdb.org/t/p/w500/poster-oficial.jpg')

    # w Verifica que, se a segunda busca (en-US) falhar, o poster de pt-BR já obtido não se perde.
    def test_get_movie_by_tmdb_id_falls_back_when_en_us_lookup_fails(self):
        service = TmdbService('test-key', 'https://api.themoviedb.org/3')

        def fake_request(path, params):
            if params.get('language') == 'en-US':
                raise TmdbServiceError('falhou')
            return {
                'id': 765,
                'title': 'Evil Dead II',
                'release_date': '1987-03-13',
                'poster_path': '/poster-pt-br.jpg',
                'credits': {'crew': []},
            }

        with patch.object(service, '_request', side_effect=fake_request):
            movie = service.get_movie_by_tmdb_id(765)
        self.assertEqual(movie['Poster'], 'https://image.tmdb.org/t/p/w500/poster-pt-br.jpg')

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
        self.assertEqual(client.get('/reviews').status_code, 200)
        self.assertEqual(client.get('/generos-invalidos').status_code, 404)

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

    # w Verifica que um banco sem public_rating (schema 2) ganha a coluna sem perder dados.
    def test_init_database_adds_public_rating_column(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            connection = sqlite3.connect(database_path)
            try:
                for statement in (
                    "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, "
                    "display_name TEXT NOT NULL, password_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                    "CREATE TABLE movies (tmdb_id INTEGER PRIMARY KEY, imdb_id TEXT UNIQUE, title TEXT NOT NULL, "
                    "year TEXT, media_type TEXT, poster_url TEXT, cached_poster_path TEXT, genre TEXT, "
                    "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                    "CREATE TABLE user_movies (user_id INTEGER NOT NULL, tmdb_id INTEGER NOT NULL, "
                    "favorite INTEGER NOT NULL DEFAULT 0, watched INTEGER NOT NULL DEFAULT 0, rating REAL, "
                    "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "PRIMARY KEY (user_id, tmdb_id))",
                    "CREATE TABLE reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                    "tmdb_id INTEGER NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE (user_id, tmdb_id))",
                    "INSERT INTO movies (tmdb_id, title) VALUES (765, 'Evil Dead II')",
                ):
                    connection.execute(statement)
                connection.execute('PRAGMA user_version = 2')
                connection.commit()
            finally:
                connection.close()

            init_database(database_path)
            connection = sqlite3.connect(database_path)
            try:
                columns = {row[1] for row in connection.execute('PRAGMA table_info(movies)')}
                self.assertIn('public_rating', columns)
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM movies').fetchone()[0], 1)
            finally:
                connection.close()

    # w Verifica que filmes podem ser salvos e atualizados no SQLite pelo tmdb_id.
    def test_database_movie_repository(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            movie = {
                'tmdbID': 765,
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

            stored_movie = get_movie(database_path, movie['tmdbID'])
            self.assertEqual(stored_movie['Title'], 'Evil Dead II atualizado')
            self.assertEqual(stored_movie['_poster'], '/cache/tt0092991.jpg')
            self.assertEqual(stored_movie['imdbID'], 'tt0092991')

    # w Verifica que um filme do TMDb sem IMDb ID é salvo e que um IMDb ID conhecido não se perde.
    def test_save_movie_without_imdb_id(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)

            save_movie(database_path, {'tmdbID': 999, 'imdbID': None, 'Title': 'Filme Sem IMDb'})
            stored_movie = get_movie(database_path, 999)
            self.assertEqual(stored_movie['Title'], 'Filme Sem IMDb')
            self.assertIsNone(stored_movie['imdbID'])

    # w Verifica que a nota pública é salva e que um valor já conhecido não se perde numa
    # w atualização que venha sem essa informação (mesma regra usada para o imdb_id).
    def test_save_movie_keeps_known_public_rating(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)

            save_movie(database_path, {'tmdbID': 765, 'Title': 'Evil Dead II', 'public_rating': 7.8})
            self.assertEqual(get_movie(database_path, 765)['public_rating'], 7.8)

            save_movie(database_path, {'tmdbID': 765, 'Title': 'Evil Dead II', 'public_rating': None})
            self.assertEqual(get_movie(database_path, 765)['public_rating'], 7.8)

            save_movie(database_path, {'tmdbID': 765, 'Title': 'Evil Dead II', 'public_rating': 8.1})
            self.assertEqual(get_movie(database_path, 765)['public_rating'], 8.1)

            save_movie(database_path, {'tmdbID': 765, 'imdbID': 'tt0092991', 'Title': 'Evil Dead II'})
            save_movie(database_path, {'tmdbID': 765, 'imdbID': None, 'Title': 'Evil Dead II'})
            self.assertEqual(get_movie(database_path, 765)['imdbID'], 'tt0092991')

    # w Verifica que filmes sem tmdbID numérico ou sem título são recusados.
    def test_save_movie_requires_tmdb_id_and_title(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            invalid_movies = (
                {'Title': 'Sem ID'},
                {'tmdbID': 'abc', 'Title': 'ID em texto'},
                {'tmdbID': True, 'Title': 'ID booleano'},
                {'tmdbID': 765},
            )
            for movie in invalid_movies:
                with self.subTest(movie=movie):
                    with self.assertRaises(ValueError):
                        save_movie(database_path, movie)
            self.assertIsNone(get_movie(database_path, 765))

    # w Verifica favoritar/assistir/avaliar pelo tmdb_id, inclusive filme sem IMDb ID.
    def test_save_user_movie_state_and_get_user_library(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user = create_user(database_path, 'ParceiroDois', 'segredo')
            movie = {'tmdbID': 999, 'imdbID': None, 'Title': 'Filme Sem IMDb'}

            result = save_user_movie_state(database_path, user['id'], movie, favorite=True, watched=False, rating=4.5)
            self.assertEqual(result['favorite'], True)
            self.assertEqual(result['watched'], False)
            self.assertEqual(result['rating'], 4.5)
            self.assertIsNone(result['imdbID'])

            library = get_user_library(database_path, user['id'])
            self.assertIn(999, library)
            self.assertEqual(library[999]['Title'], 'Filme Sem IMDb')

    # w Verifica que a nota fora do passo de 0,5 é recusada.
    def test_save_user_movie_state_rejects_invalid_rating(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user = create_user(database_path, 'ParceiroTres', 'segredo')
            movie = {'tmdbID': 765, 'imdbID': 'tt0092991', 'Title': 'Evil Dead II'}
            with self.assertRaises(ValueError):
                save_user_movie_state(database_path, user['id'], movie, favorite=False, watched=True, rating=3.3)

    # w Verifica criação, atualização e remoção de review pelo tmdb_id.
    def test_save_user_review(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user = create_user(database_path, 'ParceiroQuatro', 'segredo')
            movie = {'tmdbID': 765, 'imdbID': 'tt0092991', 'Title': 'Evil Dead II'}

            save_user_review(database_path, user['id'], movie, 'Ótimo filme.')
            library = get_user_library(database_path, user['id'])
            self.assertEqual(library[765]['review'], 'Ótimo filme.')

            save_user_review(database_path, user['id'], movie, '')
            library = get_user_library(database_path, user['id'])
            self.assertNotIn(765, library)

    # w Verifica que o histórico junta user_movies e reviews, ordenado do mais recente ao mais antigo.
    def test_get_user_activity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user = create_user(database_path, 'ParceiroQuinze', 'segredo')
            movie_a = {'tmdbID': 111, 'imdbID': None, 'Title': 'Filme A'}
            movie_b = {'tmdbID': 222, 'imdbID': None, 'Title': 'Filme B'}

            save_user_movie_state(database_path, user['id'], movie_a, favorite=True, watched=True, rating=4.0)
            save_user_review(database_path, user['id'], movie_b, 'Muito bom.')

            activity = get_user_activity(database_path, user['id'])
            self.assertEqual(len(activity), 2)
            self.assertEqual({item['type'] for item in activity}, {'movie_state', 'review'})
            movie_state_item = next(item for item in activity if item['type'] == 'movie_state')
            self.assertEqual(movie_state_item['tmdbID'], 111)
            self.assertTrue(movie_state_item['favorite'])
            self.assertTrue(movie_state_item['watched'])
            review_item = next(item for item in activity if item['type'] == 'review')
            self.assertEqual(review_item['review'], 'Muito bom.')

            # w Um filme só assistido/favoritado sem nenhum estado marcado não deve virar evento vazio.
            movie_c = {'tmdbID': 333, 'imdbID': None, 'Title': 'Filme C'}
            save_user_movie_state(database_path, user['id'], movie_c, favorite=False, watched=False, rating=None)
            activity_after = get_user_activity(database_path, user['id'])
            self.assertEqual(len(activity_after), 2)

    # w Verifica contagens, média de notas, gênero/década preferidos e melhor/pior filme do usuário.
    def test_get_user_statistics(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user = create_user(database_path, 'ParceiroDezesseis', 'segredo')

            movie_a = {'tmdbID': 111, 'imdbID': None, 'Title': 'Filme A', 'Year': '1987', 'Genre': 'Terror, Comédia'}
            movie_b = {'tmdbID': 222, 'imdbID': None, 'Title': 'Filme B', 'Year': '1985', 'Genre': 'Terror'}
            movie_c = {'tmdbID': 333, 'imdbID': None, 'Title': 'Filme C', 'Year': '2020', 'Genre': 'Drama'}

            save_user_movie_state(database_path, user['id'], movie_a, favorite=True, watched=True, rating=5.0)
            save_user_movie_state(database_path, user['id'], movie_b, favorite=False, watched=True, rating=2.0)
            save_user_movie_state(database_path, user['id'], movie_c, favorite=False, watched=False, rating=None)
            save_user_review(database_path, user['id'], movie_a, 'Ótimo.')

            stats = get_user_statistics(database_path, user['id'])
            self.assertEqual(stats['watched_count'], 2)
            self.assertEqual(stats['favorite_count'], 1)
            self.assertEqual(stats['review_count'], 1)
            self.assertEqual(stats['average_rating'], 3.5)
            self.assertEqual(stats['top_genre'], {'name': 'Terror', 'count': 2})
            self.assertEqual(stats['top_decade'], {'name': '1980s', 'count': 2})
            self.assertEqual(stats['best_movie'], {'Title': 'Filme A', 'rating': 5.0})
            self.assertEqual(stats['worst_movie'], {'Title': 'Filme B', 'rating': 2.0})

    # w Verifica ranking entre usuários, filmes em comum e maior divergência de nota, e que uma
    # w conta fora da lista de usernames da casa não entra na comparação.
    def test_get_household_statistics(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user_one = create_user(database_path, 'ParceiroDezessete', 'segredo')
            user_two = create_user(database_path, 'ParceiroDezoito', 'segredo')
            outsider = create_user(database_path, 'Visitante', 'segredo')
            shared_movie = {'tmdbID': 444, 'imdbID': None, 'Title': 'Filme Compartilhado'}
            solo_movie = {'tmdbID': 555, 'imdbID': None, 'Title': 'Filme Solo'}

            save_user_movie_state(database_path, user_one['id'], shared_movie, favorite=True, watched=True, rating=5.0)
            save_user_movie_state(database_path, user_two['id'], shared_movie, favorite=False, watched=True, rating=1.0)
            save_user_movie_state(database_path, user_one['id'], solo_movie, favorite=False, watched=True, rating=None)
            save_user_movie_state(database_path, outsider['id'], shared_movie, favorite=True, watched=True, rating=3.0)

            stats = get_household_statistics(database_path, ('ParceiroDezessete', 'ParceiroDezoito'))
            self.assertEqual(len(stats['users']), 2)
            self.assertNotIn('Visitante', {row['display_name'] for row in stats['per_user_counts']})

            counts_by_user = {row['display_name']: row for row in stats['per_user_counts']}
            self.assertEqual(counts_by_user['ParceiroDezessete']['watched_count'], 2)
            self.assertEqual(counts_by_user['ParceiroDezoito']['watched_count'], 1)

            self.assertEqual(len(stats['shared_movies']), 1)
            self.assertEqual(stats['shared_movies'][0]['Title'], 'Filme Compartilhado')
            self.assertEqual(stats['shared_movies'][0]['watcher_count'], 2)

            self.assertEqual(len(stats['divergent_ratings']), 1)
            self.assertEqual(stats['divergent_ratings'][0]['Title'], 'Filme Compartilhado')
            self.assertEqual(stats['divergent_ratings'][0]['difference'], 4.0)

    # w Verifica que o histórico da casa traz eventos só de quem está na lista de usernames,
    # w cada um com o nome de quem fez, e ignora quem está fora dessa lista.
    def test_get_household_activity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user_one = create_user(database_path, 'ParceiroVinte', 'segredo')
            user_two = create_user(database_path, 'ParceiroVinteUm', 'segredo')
            outsider = create_user(database_path, 'Visitante', 'segredo')
            movie_a = {'tmdbID': 111, 'imdbID': None, 'Title': 'Filme A'}
            movie_b = {'tmdbID': 222, 'imdbID': None, 'Title': 'Filme B'}
            movie_c = {'tmdbID': 333, 'imdbID': None, 'Title': 'Filme C'}

            save_user_movie_state(database_path, user_one['id'], movie_a, favorite=True, watched=True, rating=4.0)
            save_user_review(database_path, user_two['id'], movie_b, 'Muito bom.')
            save_user_movie_state(database_path, outsider['id'], movie_c, favorite=True, watched=True, rating=2.0)

            activity = get_household_activity(database_path, ('ParceiroVinte', 'ParceiroVinteUm'))
            self.assertEqual(len(activity), 2)
            names = {item['display_name'] for item in activity}
            self.assertEqual(names, {'ParceiroVinte', 'ParceiroVinteUm'})

            movie_state_item = next(item for item in activity if item['type'] == 'movie_state')
            self.assertEqual(movie_state_item['display_name'], 'ParceiroVinte')
            review_item = next(item for item in activity if item['type'] == 'review')
            self.assertEqual(review_item['display_name'], 'ParceiroVinteUm')

    # w Verifica leitura do perfil e atualização do nome de exibição, com validação de tamanho.
    def test_profile_read_and_update_display_name(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user = create_user(database_path, 'ParceiroOito', 'segredo')

            profile = get_user_profile(database_path, user['id'])
            self.assertEqual(profile['username'], 'ParceiroOito')
            self.assertEqual(profile['display_name'], 'ParceiroOito')

            update_display_name(database_path, user['id'], 'Novo Nome')
            profile = get_user_profile(database_path, user['id'])
            self.assertEqual(profile['display_name'], 'Novo Nome')

            with self.assertRaises(ValueError):
                update_display_name(database_path, user['id'], 'A')

    # w Verifica que a senha só troca com a senha atual correta.
    def test_change_user_password(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user = create_user(database_path, 'ParceiroNove', 'segredo')

            with self.assertRaises(ValueError):
                change_user_password(database_path, user['id'], 'senha-errada', 'novasenha')

            change_user_password(database_path, user['id'], 'segredo', 'novasenha')
            self.assertIsNotNone(authenticate_user(database_path, 'ParceiroNove', 'novasenha'))
            self.assertIsNone(authenticate_user(database_path, 'ParceiroNove', 'segredo'))

    # w Verifica que a conta só é apagada com a senha correta e que os dados relacionados somem junto.
    def test_delete_user_account_requires_password_and_cascades(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            user = create_user(database_path, 'ParceiroDez', 'segredo')
            movie = {'tmdbID': 765, 'imdbID': 'tt0092991', 'Title': 'Evil Dead II'}
            save_user_movie_state(database_path, user['id'], movie, True, False, None)

            with self.assertRaises(ValueError):
                delete_user_account(database_path, user['id'], 'senha-errada')

            delete_user_account(database_path, user['id'], 'segredo')
            self.assertIsNone(authenticate_user(database_path, 'ParceiroDez', 'segredo'))
            connection = sqlite3.connect(database_path)
            try:
                self.assertEqual(
                    connection.execute('SELECT COUNT(*) FROM user_movies WHERE user_id = ?', (user['id'],)).fetchone()[0],
                    0,
                )
            finally:
                connection.close()

    # w Verifica que /perfil/conta exige login e mostra os formulários de gerenciamento da conta.
    def test_account_route(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                self.assertEqual(app.app.test_client().get('/perfil/conta').status_code, 302)

                user = create_user(database_path, 'ParceiroDez', 'segredo')
                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']

                response = client.get('/perfil/conta')
                self.assertEqual(response.status_code, 200)
                page = response.get_data(as_text=True)
                self.assertIn('Alterar senha', page)
                self.assertIn('Excluir conta', page)

    # w Verifica a rota de perfil e a atualização do nome de exibição via formulário.
    def test_profile_route_and_display_name_update(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                self.assertEqual(app.app.test_client().get('/perfil').status_code, 302)

                user = create_user(database_path, 'ParceiroOnze', 'segredo')
                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']

                response = client.get('/perfil')
                self.assertEqual(response.status_code, 200)

                response = client.post('/perfil/nome', data={'display_name': 'Onze Renomeado'})
                self.assertEqual(response.status_code, 200)
                self.assertIn('Onze Renomeado', response.get_data(as_text=True))

    # w Verifica a troca de senha via formulário, incluindo os casos de rejeição.
    def test_profile_password_route(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                user = create_user(database_path, 'ParceiroDoze', 'segredo')
                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']

                mismatched = client.post('/perfil/senha', data={
                    'current_password': 'segredo',
                    'new_password': 'nova1',
                    'new_password_confirmation': 'nova2',
                })
                self.assertIn('precisam ser iguais', mismatched.get_data(as_text=True))

                wrong_current = client.post('/perfil/senha', data={
                    'current_password': 'errada',
                    'new_password': 'nova1',
                    'new_password_confirmation': 'nova1',
                })
                self.assertIn('Senha atual incorreta', wrong_current.get_data(as_text=True))

                success = client.post('/perfil/senha', data={
                    'current_password': 'segredo',
                    'new_password': 'nova1',
                    'new_password_confirmation': 'nova1',
                })
                self.assertEqual(success.status_code, 200)
                self.assertIsNotNone(authenticate_user(database_path, 'ParceiroDoze', 'nova1'))

    # w Verifica que a exclusão de conta apaga o usuário e encerra a sessão.
    def test_profile_delete_route(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                user = create_user(database_path, 'ParceiroTreze', 'segredo')
                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']

                wrong_password = client.post('/perfil/excluir', data={'password': 'errada'})
                self.assertIn('Senha incorreta', wrong_password.get_data(as_text=True))

                response = client.post('/perfil/excluir', data={'password': 'segredo'})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, '/login')
                self.assertIsNone(authenticate_user(database_path, 'ParceiroTreze', 'segredo'))
                self.assertEqual(client.get('/perfil').status_code, 302)

    # w Verifica que a página de atividade exige login e mostra o histórico do usuário.
    def test_activity_route(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path):
                user = create_user(database_path, 'ParceiroQuatorze', 'segredo')
                movie = {'tmdbID': 444, 'imdbID': None, 'Title': 'Filme Atividade'}
                save_user_movie_state(database_path, user['id'], movie, favorite=True, watched=False, rating=None)

                anonymous_client = app.app.test_client()
                self.assertEqual(anonymous_client.get('/atividade').status_code, 302)

                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']
                response = client.get('/atividade')
                self.assertEqual(response.status_code, 200)
                self.assertIn('Filme Atividade', response.get_data(as_text=True))

    # w Verifica que a página de perfil exige login e mostra a identidade e as estatísticas
    # w (individuais e da casa) juntas, já que as ações de conta saíram para /perfil/conta.
    def test_statistics_route(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path), \
                    patch.object(app, 'HOUSEHOLD_USERNAMES', ('ParceiroDezenove',)):
                user = create_user(database_path, 'ParceiroDezenove', 'segredo')
                movie = {'tmdbID': 777, 'imdbID': None, 'Title': 'Filme Estatística', 'Genre': 'Terror'}
                save_user_movie_state(database_path, user['id'], movie, favorite=True, watched=True, rating=4.0)

                anonymous_client = app.app.test_client()
                self.assertEqual(anonymous_client.get('/perfil').status_code, 302)

                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user['id']
                response = client.get('/perfil')
                self.assertEqual(response.status_code, 200)
                page = response.get_data(as_text=True)
                self.assertIn('Filme Estatística', page)
                self.assertIn('ParceiroDezenove', page)
                self.assertIn('/perfil/conta', page)

    # w Verifica que o painel-resumo da /home mostra os números de quem logou e a atividade da casa.
    def test_home_dashboard_panel(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / 'test.sqlite3'
            init_database(database_path)
            with patch.object(app, 'DATABASE_PATH', database_path), \
                    patch.object(app, 'HOUSEHOLD_USERNAMES', ('ParceiroVinteDois', 'ParceiroVinteTres')):
                user_one = create_user(database_path, 'ParceiroVinteDois', 'segredo')
                user_two = create_user(database_path, 'ParceiroVinteTres', 'segredo')
                movie = {'tmdbID': 888, 'imdbID': None, 'Title': 'Filme Painel', 'Genre': 'Terror'}
                save_user_movie_state(database_path, user_one['id'], movie, favorite=True, watched=True, rating=4.0)
                save_user_review(database_path, user_two['id'], movie, 'Excelente.')

                client = app.app.test_client()
                with client.session_transaction() as active_session:
                    active_session['user_id'] = user_one['id']
                response = client.get('/home')
                self.assertEqual(response.status_code, 200)
                page = response.get_data(as_text=True)
                self.assertIn('Filme Painel', page)
                self.assertIn('ParceiroVinteDois', page)
                self.assertIn('ParceiroVinteTres', page)


if __name__ == '__main__':
    unittest.main()
