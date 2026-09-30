(() => {
  // # w Seleciona os elementos principais da página de coleção.
  const page = document.body;
  const content = document.getElementById('collection-content');
  const title = document.getElementById('collection-title');
  const description = document.getElementById('collection-description');
  const count = document.getElementById('collection-count');
  const sidebar = document.getElementById('sidebar-preview');
  const sidebarToggle = document.querySelector('.sidebar-toggle');
  const collectionType = page.dataset.collectionType;
  const genreFilter = document.getElementById('filterGenre');
  const yearFilter = document.getElementById('filterYear');
  const ratingFilter = document.getElementById('filterRating');
  const pagination = document.getElementById('collection-pagination');

  // # w Quantos cards aparecem por página antes de precisar clicar em "carregar mais".
  const PAGE_SIZE = 12;

  // # w Todos os filmes da coleção (já filtrados por tipo), antes dos filtros do usuário.
  let allMovies = [];
  // # w Quantos itens filtrados já estão visíveis na tela.
  let visibleCount = PAGE_SIZE;

  // # w Protege os dados exibidos na página antes de inseri-los no HTML.
  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // # w Renderiza a nota pessoal com suporte visual para meia estrela.
  function renderRatingStars(rating) {
    const safeRating = Math.min(5, Math.max(0, Number(rating) || 0));
    return [1, 2, 3, 4, 5].map((star) => {
      const fill = safeRating >= star ? 100 : safeRating >= star - 0.5 ? 50 : 0;
      return `<span class="rating-star-shape" style="--star-fill: ${fill}%">★</span>`;
    }).join('');
  }

  // # w Rótulo, ícone e textos de cada tipo de coleção, num só lugar.
  const COLLECTION_META = {
    favoritos: {
      label: 'Favorito',
      icon: '☆',
      title: 'Meus favoritos',
      description: 'Os filmes que ganharam um lugar especial na sua coleção.',
      emptyTitle: 'Sua lista de favoritos está vazia',
      emptyText: 'Pesquise um filme e favorite aqueles que você quer guardar.',
    },
    assistidos: {
      label: 'Assistido',
      icon: '◷',
      title: 'Filmes assistidos',
      description: 'Tudo o que você já registrou como assistido.',
      emptyTitle: 'Você ainda não marcou filmes como assistidos',
      emptyText: 'Quando terminar um filme, marque-o como assistido para encontrá-lo aqui.',
    },
    reviews: {
      label: 'Review',
      icon: '✎',
      title: 'Minhas reviews',
      description: 'Suas críticas e opiniões sobre os filmes que você avaliou.',
      emptyTitle: 'Você ainda não escreveu nenhuma review',
      emptyText: 'Abra os detalhes de um filme e escreva o que você achou dele.',
    },
  };

  // # w Monta cada filme salvo como um card reutilizável nos três estilos.
  function renderMovie(movie) {
    const poster = movie._poster || movie.Poster;
    const posterHtml = poster && poster !== 'N/A'
      ? `<img src="${escapeHtml(poster)}" alt="Poster de ${escapeHtml(movie.Title)}" />`
      : '<span class="collection-card-placeholder">☆</span>';

    const personalRating = Math.min(5, Math.max(0, Number(movie.rating) || 0));
    const reviewHtml = movie.review
      ? `<blockquote class="collection-card-review">“${escapeHtml(movie.review)}”</blockquote>`
      : '';

    return `
      <article class="collection-card">
        <div class="collection-card-poster">${posterHtml}</div>
        <div class="collection-card-body">
          <span class="collection-card-type">${COLLECTION_META[collectionType].label}</span>
          <h2>${escapeHtml(movie.Title || 'Filme sem título')}</h2>
          <p>${escapeHtml(movie.Year || 'Ano não informado')}</p>
          <span class="collection-card-rating">${personalRating ? `Sua nota: <span class="rating-display">${renderRatingStars(personalRating)}</span>` : 'Sem nota pessoal'}</span>
          ${reviewHtml}
          <a href="/home?movie=${encodeURIComponent(movie.tmdbID)}" class="collection-card-link">Ver detalhes →</a>
        </div>
      </article>
    `;
  }

  // # w Renderiza o estado vazio quando a coleção ainda não possui filmes.
  function renderEmptyState() {
    const meta = COLLECTION_META[collectionType];
    content.innerHTML = `
      <div class="collection-empty-page">
        <span class="empty-state-icon">${meta.icon}</span>
        <h2>${meta.emptyTitle}</h2>
        <p>${meta.emptyText}</p>
        <a href="/home" class="collection-primary-link">Descobrir filmes</a>
      </div>
    `;
  }

  // # w Extrai gêneros únicos a partir do campo "Comedy, Horror" salvo no banco.
  function collectGenres(movies) {
    const genres = new Set();
    movies.forEach((movie) => {
      String(movie.Genre || '').split(',').forEach((genre) => {
        const trimmed = genre.trim();
        if (trimmed) genres.add(trimmed);
      });
    });
    return [...genres].sort((first, second) => first.localeCompare(second));
  }

  // # w Preenche os selects de filtro só uma vez, com base no que existe na coleção.
  function populateFilterOptions(movies) {
    if (genreFilter.dataset.filled) return;
    genreFilter.dataset.filled = 'true';

    collectGenres(movies).forEach((genre) => {
      const option = document.createElement('option');
      option.value = genre;
      option.textContent = genre;
      genreFilter.appendChild(option);
    });

    const years = [...new Set(movies.map((movie) => movie.Year).filter(Boolean))]
      .sort((first, second) => String(second).localeCompare(String(first)));
    years.forEach((year) => {
      const option = document.createElement('option');
      option.value = year;
      option.textContent = year;
      yearFilter.appendChild(option);
    });
  }

  // # w Aplica os filtros escolhidos pelo usuário sobre a lista já filtrada pelo tipo de coleção.
  function applyFilters(movies) {
    const genre = genreFilter.value;
    const year = yearFilter.value;
    const minRating = Number(ratingFilter.value) || 0;
    return movies.filter((movie) => {
      if (genre && !String(movie.Genre || '').split(',').map((g) => g.trim()).includes(genre)) return false;
      if (year && String(movie.Year || '') !== year) return false;
      if (minRating && Number(movie.public_rating || 0) < minRating) return false;
      return true;
    });
  }

  // # w Renderiza a fatia atual dos filmes filtrados e o botão de carregar mais, se sobrar algum.
  function renderPage() {
    const filtered = applyFilters(allMovies);

    count.textContent = filtered.length === allMovies.length
      ? `${filtered.length} ${filtered.length === 1 ? 'filme' : 'filmes'}`
      : `${filtered.length} de ${allMovies.length} filmes`;

    if (filtered.length === 0) {
      pagination.innerHTML = '';
      if (allMovies.length === 0) {
        renderEmptyState();
      } else {
        content.innerHTML = `<p class="error-state">Nenhum filme encontrado com esses filtros.</p>`;
      }
      return;
    }

    const visible = filtered.slice(0, visibleCount);
    content.innerHTML = visible.map(renderMovie).join('');

    if (visible.length < filtered.length) {
      pagination.innerHTML = `<button type="button" class="collection-load-more" id="loadMoreButton">Carregar mais (${filtered.length - visible.length} restantes)</button>`;
      document.getElementById('loadMoreButton').addEventListener('click', () => {
        visibleCount += PAGE_SIZE;
        renderPage();
      });
    } else {
      pagination.innerHTML = '';
    }
  }

  // # w Renderiza os filmes salvos na página própria da coleção.
  async function renderCollection() {
    const meta = COLLECTION_META[collectionType];
    const response = await fetch('/api/library');
    if (!response.ok) {
      content.innerHTML = '<p class="error-state">Não foi possível carregar sua coleção.</p>';
      return;
    }
    const library = await response.json();
    if (collectionType === 'reviews') {
      allMovies = Object.values(library)
        .filter((movie) => Boolean(movie.review))
        .sort((first, second) => String(second.review_updated_at || '').localeCompare(String(first.review_updated_at || '')));
    } else {
      const statusName = collectionType === 'favoritos' ? 'favorite' : 'watched';
      allMovies = Object.values(library)
        .filter((movie) => Boolean(movie[statusName]))
        .sort((first, second) => String(first.Title || '').localeCompare(String(second.Title || '')));
    }

    title.textContent = meta.title;
    description.textContent = meta.description;
    populateFilterOptions(allMovies);
    renderPage();
  }

  // # w Volta pra primeira página sempre que o usuário muda um filtro.
  function handleFilterChange() {
    visibleCount = PAGE_SIZE;
    renderPage();
  }

  // # w Abre ou fecha a navegação lateral compartilhada.
  function toggleSidebar() {
    const isOpen = sidebar.classList.toggle('sidebar-open');
    sidebarToggle.setAttribute('aria-expanded', String(isOpen));
  }

  sidebarToggle.addEventListener('click', toggleSidebar);
  genreFilter.addEventListener('change', handleFilterChange);
  yearFilter.addEventListener('change', handleFilterChange);
  ratingFilter.addEventListener('change', handleFilterChange);
  renderCollection();
})();
