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

  // # w Monta cada filme salvo como um card reutilizável nos cinco estilos.
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
          <span class="collection-card-type">${collectionType === 'favoritos' ? 'Favorito' : 'Assistido'}</span>
          <h2>${escapeHtml(movie.Title || 'Filme sem título')}</h2>
          <p>${escapeHtml(movie.Year || 'Ano não informado')}</p>
          <span class="collection-card-rating">${personalRating ? `Sua nota: <span class="rating-display">${renderRatingStars(personalRating)}</span>` : 'Sem nota pessoal'}</span>
          ${reviewHtml}
          <a href="/home?movie=${encodeURIComponent(movie.imdbID)}" class="collection-card-link">Ver detalhes →</a>
        </div>
      </article>
    `;
  }

  // # w Renderiza o estado vazio quando a coleção ainda não possui filmes.
  function renderEmptyState() {
    const isFavorite = collectionType === 'favoritos';
    content.innerHTML = `
      <div class="collection-empty-page">
        <span class="empty-state-icon">${isFavorite ? '☆' : '◷'}</span>
        <h2>${isFavorite ? 'Sua lista de favoritos está vazia' : 'Você ainda não marcou filmes como assistidos'}</h2>
        <p>${isFavorite
          ? 'Pesquise um filme e favorite aqueles que você quer guardar.'
          : 'Quando terminar um filme, marque-o como assistido para encontrá-lo aqui.'}</p>
        <a href="/home" class="collection-primary-link">Descobrir filmes</a>
      </div>
    `;
  }

  // # w Renderiza os filmes salvos na página própria da coleção.
  async function renderCollection() {
    const statusName = collectionType === 'favoritos' ? 'favorite' : 'watched';
    const response = await fetch('/api/library');
    if (!response.ok) {
      content.innerHTML = '<p class="error-state">Não foi possível carregar sua coleção.</p>';
      return;
    }
    const library = await response.json();
    const movies = Object.values(library)
      .filter((movie) => Boolean(movie[statusName]))
      .sort((first, second) => String(first.Title || '').localeCompare(String(second.Title || '')));

    title.textContent = collectionType === 'favoritos' ? 'Meus favoritos' : 'Filmes assistidos';
    description.textContent = collectionType === 'favoritos'
      ? 'Os filmes que ganharam um lugar especial na sua coleção.'
      : 'Tudo o que você já registrou como assistido.';
    count.textContent = `${movies.length} ${movies.length === 1 ? 'filme' : 'filmes'}`;

    if (movies.length === 0) {
      renderEmptyState();
      return;
    }

    content.innerHTML = movies.map(renderMovie).join('');
  }

  // # w Abre ou fecha a navegação lateral compartilhada.
  function toggleSidebar() {
    const isOpen = sidebar.classList.toggle('sidebar-open');
    sidebarToggle.setAttribute('aria-expanded', String(isOpen));
  }

  sidebarToggle.addEventListener('click', toggleSidebar);
  renderCollection();
})();
