from functools import wraps
from flask import Flask, jsonify, redirect, request, send_from_directory, render_template, session, url_for
import requests
from pathlib import Path
from config import DATABASE_PATH, CACHE_DIR, HOST, PORT, HOUSEHOLD_USERNAMES, SECRET_KEY, TMDB_API_KEY, TMDB_URL
from database import (
    authenticate_user,
    change_user_password,
    create_user,
    delete_user_account,
    ensure_user_password,
    get_household_activity,
    get_household_statistics,
    get_user_activity,
    get_user_library,
    get_user_profile,
    get_user_statistics,
    init_database,
    save_user_movie_state,
    save_user_review,
    update_display_name,
)
from services.poster_cache import PosterCache
from services.tmdb_service import TmdbService, TmdbServiceError

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = SECRET_KEY
movie_provider = TmdbService(TMDB_API_KEY, TMDB_URL)
tmdb_service = movie_provider
poster_cache = PosterCache(CACHE_DIR)

# Cria a pasta de posters na inicialização caso ela ainda não exista.
CACHE_DIR.mkdir(parents=True, exist_ok=True)
init_database(DATABASE_PATH)
ensure_user_password(DATABASE_PATH, 'Nathan', 'nathan')


# Centraliza o formato das respostas de erro para o frontend.
def error_response(code: int, error_code: str, message: str):
    return jsonify({
        'error': error_code,
        'message': message,
    }), code


# w Redireciona visitantes não autenticados para o login.
def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.full_path))
        return view(*args, **kwargs)
    return wrapped_view


# w Recupera o ID da sessão e impede acesso a dados de outro usuário.
def current_user_id():
    return session['user_id']


# Mantém a URL antiga funcionando e centraliza a descoberta em /home.
@app.route('/')
def index():
    query_string = request.query_string.decode('utf-8')
    return redirect(f'/home{"?" + query_string if query_string else ""}')


# w Entrega a página principal com um resumo (seus números + atividade da casa) e a busca.
@app.route('/home')
@login_required
def home():
    return render_template(
        'index.html',
        stats=get_user_statistics(DATABASE_PATH, current_user_id()),
        household_activity=get_household_activity(DATABASE_PATH, HOUSEHOLD_USERNAMES, limit=6),
    )


# w Exibe e processa o login da aplicação privada.
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = authenticate_user(
            DATABASE_PATH,
            request.form.get('username', ''),
            request.form.get('password', ''),
        )
        if not user:
            return render_template('login.html', error='Usuário ou senha inválidos.'), 401
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        next_url = request.form.get('next') or url_for('home')
        if not next_url.startswith('/'):
            next_url = url_for('home')
        return redirect(next_url)
    return render_template('login.html', next=request.args.get('next', ''))


# w Cria uma conta e inicia a sessão imediatamente após o cadastro.
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        password_confirmation = request.form.get('password_confirmation', '')
        if password != password_confirmation:
            return render_template(
                'register.html',
                error='As senhas precisam ser iguais.',
                username=username,
            ), 400
        try:
            user = create_user(DATABASE_PATH, username, password)
        except ValueError as error:
            return render_template(
                'register.html',
                error=str(error),
                username=username,
            ), 400
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect(url_for('home'))
    return render_template('register.html')


# w Encerra a sessão atual e retorna ao formulário de login.
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# w Exibe a identidade do usuário e suas estatísticas (pessoais e da casa); as ações de conta
# w (trocar nome/senha, excluir) ficam em /perfil/conta, a pedido do usuário.
@app.route('/perfil')
@login_required
def profile():
    return render_template(
        'profile.html',
        profile=get_user_profile(DATABASE_PATH, current_user_id()),
        stats=get_user_statistics(DATABASE_PATH, current_user_id()),
        household=get_household_statistics(DATABASE_PATH, HOUSEHOLD_USERNAMES),
    )


# w Exibe os formulários de gerenciamento da conta autenticada.
@app.route('/perfil/conta')
@login_required
def account():
    return render_template('account.html', profile=get_user_profile(DATABASE_PATH, current_user_id()))


# w Atualiza o nome de exibição do usuário autenticado.
@app.route('/perfil/nome', methods=['POST'])
@login_required
def profile_display_name():
    try:
        update_display_name(DATABASE_PATH, current_user_id(), request.form.get('display_name', ''))
        success = 'Nome de exibição atualizado.'
        error = None
    except ValueError as err:
        success = None
        error = str(err)
    return render_template(
        'account.html',
        profile=get_user_profile(DATABASE_PATH, current_user_id()),
        name_error=error,
        name_success=success,
    )


# w Só troca a senha depois de confirmar a senha atual e a repetição da nova senha.
@app.route('/perfil/senha', methods=['POST'])
@login_required
def profile_password():
    new_password = request.form.get('new_password', '')
    new_password_confirmation = request.form.get('new_password_confirmation', '')
    error = None
    success = None
    if new_password != new_password_confirmation:
        error = 'As senhas precisam ser iguais.'
    else:
        try:
            change_user_password(
                DATABASE_PATH,
                current_user_id(),
                request.form.get('current_password', ''),
                new_password,
            )
            success = 'Senha atualizada.'
        except ValueError as err:
            error = str(err)
    return render_template(
        'account.html',
        profile=get_user_profile(DATABASE_PATH, current_user_id()),
        password_error=error,
        password_success=success,
    )


# w Exige a senha atual antes de apagar a conta e encerra a sessão em seguida.
@app.route('/perfil/excluir', methods=['POST'])
@login_required
def profile_delete():
    try:
        delete_user_account(DATABASE_PATH, current_user_id(), request.form.get('password', ''))
    except ValueError as err:
        return render_template(
            'account.html',
            profile=get_user_profile(DATABASE_PATH, current_user_id()),
            delete_error=str(err),
        )
    session.clear()
    return redirect(url_for('login'))


# Entrega as páginas pessoais de favoritos, assistidos e reviews.
@app.route('/<collection_type>')
@login_required
def collection_page(collection_type):
    if collection_type not in {'favoritos', 'assistidos', 'reviews'}:
        empty_stats = {'watched_count': 0, 'favorite_count': 0, 'review_count': 0, 'average_rating': None}
        return render_template('index.html', stats=empty_stats, household_activity=[]), 404
    return render_template('collection.html', collection_type=collection_type)


# w Mostra o histórico de mudanças (favorito, assistido, nota, review) mais recentes primeiro.
@app.route('/atividade')
@login_required
def activity():
    return render_template('activity.html', activity=get_user_activity(DATABASE_PATH, current_user_id()))


# Faz buscas por título e retorna uma lista de resultados.
@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        q = movie_provider.validate_query(q)
        return jsonify(movie_provider.search(q))
    except ValueError as error:
        return error_response(400, 'invalid_query', str(error))
    except TmdbServiceError as error:
        return error_response(502, 'external_service_error', str(error))

# Busca os detalhes de um filme e faz o cache do poster.
@app.route('/api/movie/tmdb/<int:tmdb_id>')
def api_movie_by_tmdb_id(tmdb_id):
    try:
        movie = movie_provider.get_movie_by_tmdb_id(tmdb_id)
    except TmdbServiceError as error:
        return error_response(502, 'external_service_error', str(error))
    if movie is None:
        return error_response(404, 'movie_not_found', 'Filme não encontrado.')
    return jsonify(poster_cache.attach_to_movie(movie, str(tmdb_id)))


# w Mantém os links das coleções existentes compatíveis com os IMDb IDs antigos.
@app.route('/api/movie/<imdb_id>')
def api_movie(imdb_id):
    try:
        imdb_id = movie_provider.validate_imdb_id(imdb_id)
        movie = movie_provider.get_movie(imdb_id)
    except ValueError as error:
        return error_response(400, 'invalid_imdb_id', str(error))
    except TmdbServiceError as error:
        return error_response(502, 'external_service_error', str(error))
    if movie is None:
        return error_response(404, 'movie_not_found', 'Filme não encontrado.')
    return jsonify(poster_cache.attach_to_movie(movie, imdb_id))


# w Testa o provedor TMDb sem alterar a busca oficial do aplicativo.
@app.route('/api/tmdb-test')
@login_required
def api_tmdb_test():
    if tmdb_service is None:
        return error_response(503, 'tmdb_not_configured', 'TMDB_API_KEY não configurada.')
    query = request.args.get('q', '').strip()
    try:
        query = tmdb_service.validate_query(query)
        movies = tmdb_service.search(query)
        people = tmdb_service.search_people(query)
        return jsonify({
            'query': query,
            'movies': movies,
            'people': people,
        })
    except ValueError as error:
        return error_response(400, 'invalid_query', str(error))
    except TmdbServiceError as error:
        return error_response(502, 'external_service_error', str(error))


# w Busca diretores e retorna seus filmes para a futura busca especializada.
@app.route('/api/directors')
@login_required
def api_directors():
    try:
        query = tmdb_service.validate_query(request.args.get('q', ''))
        return jsonify(tmdb_service.search_people(query))
    except ValueError as error:
        return error_response(400, 'invalid_query', str(error))
    except TmdbServiceError as error:
        return error_response(502, 'external_service_error', str(error))


# w Retorna filmes dirigidos pela pessoa selecionada no TMDb.
@app.route('/api/directors/<int:person_id>/movies')
@login_required
def api_director_movies(person_id):
    try:
        return jsonify(tmdb_service.discover_by_director(person_id))
    except TmdbServiceError as error:
        return error_response(502, 'external_service_error', str(error))


# w Retorna a biblioteca SQLite do usuário autenticado.
@app.route('/api/library')
@login_required
def api_library():
    return jsonify(get_user_library(DATABASE_PATH, current_user_id()))


# w Busca o filme no TMDb pelo tmdb_id da URL; nunca confia em metadados vindos do cliente.
def _fetch_movie_for_state_change(tmdb_id):
    try:
        movie = movie_provider.get_movie_by_tmdb_id(tmdb_id)
    except TmdbServiceError as error:
        return None, error_response(502, 'external_service_error', str(error))
    if movie is None:
        return None, error_response(404, 'movie_not_found', 'Filme não encontrado.')
    return poster_cache.attach_to_movie(movie, str(tmdb_id)), None


# w Salva favorito, assistido e nota no vínculo do filme com o usuário.
@app.route('/api/library/<int:tmdb_id>', methods=['PUT'])
@login_required
def api_library_movie(tmdb_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(400, 'invalid_payload', 'Envie um corpo JSON.')
    movie, error = _fetch_movie_for_state_change(tmdb_id)
    if error is not None:
        return error
    try:
        saved = save_user_movie_state(
            DATABASE_PATH,
            current_user_id(),
            movie,
            bool(payload.get('favorite')),
            bool(payload.get('watched')),
            payload.get('rating'),
        )
        return jsonify(saved)
    except (TypeError, ValueError) as error:
        return error_response(400, 'invalid_movie_state', str(error))


# w Salva ou remove a review sem alterar a biblioteca de outro usuário.
@app.route('/api/reviews/<int:tmdb_id>', methods=['PUT'])
@login_required
def api_review(tmdb_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(400, 'invalid_payload', 'Envie um corpo JSON.')
    review = payload.get('review', '')
    if review is None:
        review = ''
    if not isinstance(review, str):
        return error_response(400, 'invalid_review', 'A review precisa ser texto.')
    movie, error = _fetch_movie_for_state_change(tmdb_id)
    if error is not None:
        return error
    try:
        save_user_review(DATABASE_PATH, current_user_id(), movie, review)
        return jsonify({'review': review.strip()})
    except ValueError as error:
        return error_response(400, 'invalid_review', str(error))


# Entrega um poster armazenado localmente.
@app.route('/cache/<path:filename>')
def cached_file(filename):
    safe = Path(filename).name
    return send_from_directory(str(CACHE_DIR), safe)


# w debug=False evita expor o debugger interativo do Werkzeug (execução remota de código) agora
# w que a aplicação fica acessível pela VPN, não só em 127.0.0.1.
if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=False)
