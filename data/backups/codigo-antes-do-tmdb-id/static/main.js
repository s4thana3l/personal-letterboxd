(() => {
  // # Seleciona os elementos principais da interface.
  const q = document.getElementById('q');
  const searchType = document.getElementById('searchType');
  const btn = document.getElementById('btnSearch');
  const suggestions = document.getElementById('suggestions');
  const poster = document.getElementById('poster');
  const info = document.getElementById('info');
  const sidebarPreview = document.getElementById('sidebar-preview');
  const sidebarToggle = document.querySelector('.sidebar-toggle');
  let libraryCache = {};

  // # w Guarda o temporizador do debounce para evitar buscas excessivas.
  let timer = null;

  // # w Mantém a lateral aberta quando o usuário decide fixá-la pelo clique.
  function toggleSidebar() {
    const isOpen = sidebarPreview.classList.toggle('sidebar-open');
    sidebarToggle.setAttribute('aria-expanded', String(isOpen));
    sidebarToggle.setAttribute(
      'aria-label',
      isOpen ? 'Fechar menu da coleção' : 'Abrir menu da coleção'
    );
  }

  // # w Controla o botão de busca quando a aplicação está carregando.
  function setButtonLoading(isLoading) {
    btn.disabled = isLoading;
    btn.textContent = isLoading ? 'Buscando...' : 'Buscar';
  }

  // # w Cria um loader com três bolinhas para dar feedback visual ao usuário.
  function renderLoader(target, label) {
    target.innerHTML = `
      <div class="loading-shell">
        <div class="dots-loader" aria-label="${label}">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <div class="loading-label">${label}</div>
      </div>
    `;
  }

  // # w Mostra um estado visual consistente para cada situação sem resultado.
  function renderState(target, icon, title, message, className = 'empty-state') {
    target.innerHTML = `
      <div class="${className}">
        <span class="empty-state-icon" aria-hidden="true">${escapeHtml(icon)}</span>
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(message)}</span>
      </div>
    `;
  }

  // # w Escapa valores vindos da API para evitar quebra visual e ataques simples.
  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // # w Usa a biblioteca carregada do SQLite para a sessão atual.
  function getLibrary() {
    return libraryCache;
  }

  // # w Carrega o estado pessoal uma vez antes de exibir o filme.
  async function loadLibrary() {
    const response = await fetch('/api/library');
    if (!response.ok) {
      throw new Error('Não foi possível carregar a biblioteca.');
    }
    libraryCache = await response.json();
  }

  // # w Envia o estado atual do filme para o vínculo do usuário autenticado.
  async function saveMovieState(movie, savedMovie) {
    const response = await fetch(`/api/library/${encodeURIComponent(movie.imdbID)}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        movie,
        favorite: Boolean(savedMovie.favorite),
        watched: Boolean(savedMovie.watched),
        rating: savedMovie.rating ?? null
      })
    });
    if (!response.ok) {
      throw new Error('Não foi possível salvar o filme.');
    }
    const saved = await response.json();
    libraryCache[movie.imdbID] = saved;
    return saved;
  }

  // # w Salva ou remove a review pessoal do filme no mesmo registro da coleção.
  async function saveMovieReview(movie, review) {
    const library = getLibrary();
    const movieId = movie.imdbID;
    const currentMovie = library[movieId] || {
      imdbID: movieId,
      Title: movie.Title,
      Year: movie.Year,
      Poster: movie.Poster,
      _poster: movie._poster,
      favorite: false,
      watched: false
    };

    const response = await fetch(`/api/reviews/${encodeURIComponent(movieId)}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({movie, review})
    });
    if (!response.ok) {
      throw new Error('Não foi possível salvar a review.');
    }
    if (review.trim()) {
      currentMovie.review = review.trim();
    } else {
      delete currentMovie.review;
    }
    library[movieId] = currentMovie;
    renderMovieCard(movie);
  }

  // # w Renderiza a review pessoal em um modal definitivo.
  function renderReviewEditor(movie) {
    const savedReview = getLibrary()[movie.imdbID]?.review || '';
    return `
      <div class="review-modal-option">
        <button class="review-open-button" type="button">✎ ${savedReview ? 'Editar review' : 'Escrever review'}</button>
        <dialog class="review-dialog">
          <form method="dialog" class="review-editor review-editor-modal">
            <div class="review-editor-heading">
              <div>
                <span class="review-kicker">Review pessoal</span>
                <h3>${savedReview ? 'Editar sua review' : 'Escreva sua review'}</h3>
              </div>
              <button class="review-close-button" type="button" aria-label="Fechar review">×</button>
            </div>
            <textarea class="review-input" maxlength="2000" placeholder="O que você achou deste filme?">${escapeHtml(savedReview)}</textarea>
            <div class="review-editor-actions">
              ${savedReview ? '<button class="review-delete-button" type="button">Remover review</button>' : ''}
              <button class="review-save-button" value="save" type="submit">Salvar review</button>
            </div>
          </form>
        </dialog>
      </div>
    `;
  }

  // # w Alterna favorito ou assistido e atualiza o card imediatamente.
  async function toggleMovieStatus(movie, statusName) {
    const library = getLibrary();
    const movieId = movie.imdbID;
    const currentMovie = library[movieId] || {
      imdbID: movieId,
      Title: movie.Title,
      Year: movie.Year,
      Poster: movie.Poster,
      _poster: movie._poster,
      favorite: false,
      watched: false
    };

    currentMovie[statusName] = !currentMovie[statusName];
    await saveMovieState(movie, currentMovie);
    renderMovieCard(movie);
    poster.innerHTML = movie._poster
      ? `<img src="${escapeHtml(movie._poster)}" alt="Poster do filme" />`
      : '';
    if (!movie._poster) {
      renderState(poster, '◉', 'Poster não disponível', 'Mas os detalhes do filme estão aqui.');
    }
    renderPosterRating(movie);
  }

  // # w Salva ou remove a nota pessoal de 0 a 5 estrelas.
  async function setMovieRating(movie, rating) {
    const library = getLibrary();
    const movieId = movie.imdbID;
    const currentMovie = library[movieId] || {
      imdbID: movieId,
      Title: movie.Title,
      Year: movie.Year,
      Poster: movie.Poster,
      _poster: movie._poster,
      favorite: false,
      watched: false
    };

    if (rating === 0) {
      delete currentMovie.rating;
    } else {
      currentMovie.rating = rating;
    }

    await saveMovieState(movie, currentMovie);
    renderMovieCard(movie);
    renderPosterRating(movie);
  }

  // # w Renderiza cinco estrelas com preenchimento inteiro ou pela metade.
  function renderRatingStars(rating, className = '') {
    const safeRating = Math.min(5, Math.max(0, Number(rating) || 0));
    return `<span class="rating-display ${className}" aria-hidden="true">${
      [1, 2, 3, 4, 5].map((star) => {
        const fill = safeRating >= star ? 100 : safeRating >= star - 0.5 ? 50 : 0;
        return `<span class="rating-star-shape" style="--star-fill: ${fill}%">★</span>`;
      }).join('')
    }</span>`;
  }

  // # w Cria a avaliação grande abaixo do poster com passos de meia estrela.
  function renderPosterRating(movie) {
    const savedMovie = getLibrary()[movie.imdbID] || {};
    const personalRating = Math.min(5, Math.max(0, Number(savedMovie.rating) || 0));
    const currentRating = poster.querySelector('.poster-rating');
    if (currentRating) {
      currentRating.remove();
    }

    poster.insertAdjacentHTML('beforeend', `
      <div class="poster-rating">
        <div class="poster-rating-heading">
          <strong>Sua avaliação</strong>
          <span class="poster-rating-value">${personalRating ? `${personalRating}/5` : 'Ainda não avaliado'}</span>
        </div>
        <div class="poster-rating-stars" role="group" aria-label="Escolha sua nota de 0 a 5 estrelas">
          ${[0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5].map((rating) => `
            <button class="poster-rating-hit" data-rating="${rating}" type="button" aria-label="Dar ${rating} estrelas"></button>
          `).join('')}
          <span class="poster-rating-display">${renderRatingStars(personalRating)}</span>
        </div>
        ${personalRating ? '<button class="rating-clear poster-rating-clear" data-rating="0" type="button">Limpar nota</button>' : ''}
      </div>
    `);

    const display = poster.querySelector('.poster-rating-display');
    const value = poster.querySelector('.poster-rating-value');
    const clearButton = poster.querySelector('.poster-rating-clear');
    const restoreRating = () => {
      display.innerHTML = renderRatingStars(personalRating);
      value.textContent = personalRating ? `${personalRating}/5` : 'Ainda não avaliado';
    };

    poster.querySelectorAll('.poster-rating-hit').forEach((button) => {
      button.addEventListener('mouseenter', () => {
        const rating = Number(button.dataset.rating);
        display.innerHTML = renderRatingStars(rating);
        value.textContent = `${rating}/5`;
      });
      button.addEventListener('mouseleave', restoreRating);
      button.addEventListener('click', () => setMovieRating(movie, Number(button.dataset.rating)));
    });
    if (clearButton) {
      clearButton.addEventListener('click', () => setMovieRating(movie, 0));
    }
  }

  // # w Formata o conteúdo do filme em um layout mais amigável e profissional.
  function renderMovieCard(movie) {
    const savedMovie = getLibrary()[movie.imdbID] || {};
    const isFavorite = Boolean(savedMovie.favorite);
    const isWatched = Boolean(savedMovie.watched);
    const personalRating = Math.min(5, Math.max(0, Number(savedMovie.rating) || 0));
    const metaItems = [
      ['Ano', movie.Year],
      ['Tipo', movie.Type],
      ['Gênero', movie.Genre],
      ['Duração', movie.Runtime],
      ['Diretor', movie.Director],
      ['IMDb', movie.imdbID]
    ];

    const metaHtml = metaItems
      .filter(([, value]) => value && String(value).trim())
      .map(([label, value]) => `
        <div class="movie-detail-item">
          <span class="movie-detail-label">${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `)
      .join('');

    const ratingHtml = movie.imdbRating
      ? `<span class="movie-score"><small>IMDb</small><strong>⭐ ${escapeHtml(movie.imdbRating)}</strong><em>/10</em></span>`
      : '<span class="movie-score movie-score-muted"><small>IMDb</small><strong>Sem nota</strong></span>';

    info.innerHTML = `
      <article class="movie-card">
        <header class="movie-header">
          <div>
            <p class="movie-tag">${escapeHtml(movie.Type || 'Filme')}</p>
            <h2>${escapeHtml(movie.Title || 'Título não informado')}</h2>
            <p class="movie-subtitle">${escapeHtml(movie.Year || 'Ano não informado')}</p>
          </div>
          ${ratingHtml}
        </header>

        <div class="movie-actions" aria-label="Ações pessoais do filme">
          <button class="movie-action ${isFavorite ? 'is-active' : ''}" data-status="favorite" type="button">
            ${isFavorite ? '★ Favoritado' : '☆ Favoritar'}
          </button>
          <button class="movie-action ${isWatched ? 'is-active' : ''}" data-status="watched" type="button">
            ${isWatched ? '✓ Assistido' : '○ Marcar como assistido'}
          </button>
        </div>

        <section class="movie-meta">
          ${metaHtml}
        </section>

        <section class="movie-summary">
          <h3>Sinopse</h3>
          <p>${escapeHtml(movie.Plot || 'Sinopse não disponível no momento.')}</p>
        </section>

        <section class="movie-cast">
          <h3>Elenco</h3>
          <p>${escapeHtml(movie.Actors || 'Informações do elenco não disponíveis.')}</p>
        </section>
        ${renderReviewEditor(movie)}
      </article>
    `;

    // # w Conecta os botões depois que o card é recriado no DOM.
    info.querySelectorAll('.movie-action').forEach((button) => {
      button.addEventListener('click', () => {
        toggleMovieStatus(movie, button.dataset.status);
      });
    });

    const reviewInput = info.querySelector('.review-input');
    const saveReviewButton = info.querySelector('.review-save-button');
    const deleteReviewButton = info.querySelector('.review-delete-button');
    if (saveReviewButton) {
      saveReviewButton.addEventListener('click', (event) => {
        event.preventDefault();
        saveMovieReview(movie, reviewInput.value);
      });
    }
    if (deleteReviewButton) {
      deleteReviewButton.addEventListener('click', () => saveMovieReview(movie, ''));
    }

    const dialog = info.querySelector('.review-dialog');
    const openReviewButton = info.querySelector('.review-open-button');
    const closeReviewButton = info.querySelector('.review-close-button');
    if (dialog && openReviewButton) {
      openReviewButton.addEventListener('click', () => dialog.showModal());
      closeReviewButton.addEventListener('click', () => dialog.close());
      dialog.addEventListener('close', () => {
        if (dialog.returnValue === 'save') {
          saveMovieReview(movie, reviewInput.value);
        }
      });
    }
  }

  // # w Exibe mensagens amigáveis no painel de sugestões.
  function setSuggestionsMessage(message) {
    suggestions.innerHTML = '';
    suggestions.classList.add('state-message');
    renderState(suggestions, '⌕', 'Nada por aqui ainda', message, 'search-state');
  }

  // # w Remove a mensagem de estado para voltar ao layout normal.
  function clearSuggestionsMessage() {
    suggestions.classList.remove('state-message');
  }

  // # w Espera um pouco antes de disparar a busca durante a digitação.
  function debounceSearch() {
    clearTimeout(timer);
    timer = setTimeout(doSearch, 350);
  }

  // # w Busca filmes na API e mostra sugestões ao usuário.
  async function doSearch() {
    const val = q.value.trim();
    suggestions.innerHTML = '';
    clearSuggestionsMessage();
    if (!val) {
      suggestions.classList.remove('has-search');
      setSuggestionsMessage('Digite o nome de um filme ou série para começar.');
      return;
    }

    suggestions.classList.add('has-search');
    setButtonLoading(true);
    renderLoader(suggestions, 'Buscando filmes incríveis para você...');

    try {
      const endpoint = searchType.value === 'director'
        ? `/api/directors?q=${encodeURIComponent(val)}`
        : `/api/search?q=${encodeURIComponent(val)}`;
      const resp = await fetch(endpoint);
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        const message = payload.message || 'Não foi possível buscar agora. Tente novamente.';
        setSuggestionsMessage(message);
        return;
      }

      const items = await resp.json();
      suggestions.innerHTML = '';
      clearSuggestionsMessage();

      if (!items || items.length === 0) {
        setSuggestionsMessage(`Não encontrei resultados para "${val}". Tente outra busca.`);
        return;
      }

      for (const it of items) {
        const d = document.createElement('div');
        d.className = 'sugg';
        if (searchType.value === 'director') {
          d.textContent = `${it.name} [${it.known_for_department || 'Pessoa'}]`;
          d.addEventListener('click', () => loadDirectorMovies(it.tmdbID, it.name));
        } else {
          d.textContent = `${it.Title} (${it.Year}) [${it.Type}]`;
          d.dataset.tmdb = it.tmdbID;
          d.addEventListener('click', () => loadMovie(it.tmdbID));
        }
        suggestions.appendChild(d);
      }
    } catch (e) {
      setSuggestionsMessage('Não foi possível buscar no momento. Tente novamente em instantes.');
    } finally {
      setButtonLoading(false);
    }

  }

  // # w Busca os filmes dirigidos pela pessoa escolhida.
  async function loadDirectorMovies(personId, directorName) {
    renderLoader(suggestions, `Buscando filmes de ${directorName}...`);
    try {
      const response = await fetch(`/api/directors/${encodeURIComponent(personId)}/movies`);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setSuggestionsMessage(payload.message || 'Não foi possível buscar esse diretor.');
        return;
      }
      const movies = await response.json();
      suggestions.innerHTML = '';
      if (!movies.length) {
        setSuggestionsMessage(`Nenhum filme encontrado para ${directorName}.`);
        return;
      }
      movies.forEach((movie) => {
        const item = document.createElement('div');
        item.className = 'sugg';
        item.textContent = `${movie.Title} (${movie.Year})`;
        item.addEventListener('click', () => loadMovie(movie.tmdbID));
        suggestions.appendChild(item);
      });
    } catch (error) {
      setSuggestionsMessage('Não foi possível buscar os filmes desse diretor.');
    }
  }

  // # w Carrega os detalhes completos de um filme escolhido.
  async function loadMovie(tmdbId) {
    renderLoader(poster, 'Carregando pôster...');
    renderLoader(info, 'Carregando detalhes do filme...');

    try {
      const resp = await fetch(`/api/movie/tmdb/${encodeURIComponent(tmdbId)}`);
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        const message = payload.message || 'Não foi possível carregar os detalhes agora.';
        renderState(info, '!', 'Não conseguimos carregar', message, 'error-state');
        renderState(poster, '!', 'Poster indisponível', 'Tente escolher outro resultado.');
        poster.classList.remove('loading-state');
        info.classList.remove('loading-state');
        return;
      }

      const d = await resp.json();
      renderMovieCard(d);

      if (d._poster) {
        poster.innerHTML = `<img src="${escapeHtml(d._poster)}" alt="Poster do filme" />`;
        renderPosterRating(d);
        poster.classList.remove('loading-state');
      } else {
        renderState(poster, '◉', 'Poster não disponível', 'Mas os detalhes do filme estão aqui.');
        renderPosterRating(d);
        poster.classList.remove('loading-state');
      }
    } catch (e) {
      renderState(info, '!', 'Algo deu errado', 'Não foi possível carregar os detalhes deste filme.');
      renderState(poster, '!', 'Poster indisponível', 'Tente novamente em instantes.');
      poster.classList.remove('loading-state');
      info.classList.remove('loading-state');
    }
  }

  // # w Escuta a digitação do usuário e o clique no botão de busca.
  q.addEventListener('input', debounceSearch);
  btn.addEventListener('click', doSearch);
  q.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      clearTimeout(timer);
      doSearch();
    }
  });
  sidebarToggle.addEventListener('click', toggleSidebar);

  // # w Reabre automaticamente um filme selecionado a partir de uma página de coleção.
  const movieFromCollection = new URLSearchParams(window.location.search).get('movie');
  loadLibrary()
    .then(() => movieFromCollection ? loadMovie(movieFromCollection) : undefined)
    .catch(() => renderState(info, '!', 'Biblioteca indisponível', 'Atualize a página e tente novamente.', 'error-state'));
})();
