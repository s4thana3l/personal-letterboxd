# Contexto completo da aplicação de filmes

Este documento foi escrito para permitir que outro agente continue o desenvolvimento
sem perder o histórico, as decisões técnicas, os problemas conhecidos e a lógica de
evolução da aplicação.

> **Regra de trabalho do projeto:** as mudanças devem ser incrementais, explicadas
> antes ou depois de serem aplicadas, mostradas ao usuário e validadas com testes.
> Evite mudanças grandes e silenciosas.

---

## 1. Objetivo do projeto

A aplicação começou como uma busca simples de filmes usando Flask e uma API externa.
O objetivo atual é transformá-la em um diário de cinema pessoal, semelhante a um
Letterboxd privado e compartilhado entre alguns usuários.

Cada usuário deve poder:

- pesquisar filmes;
- pesquisar diretores;
- consultar detalhes, elenco, direção, sinopse, poster e nota pública;
- favoritar filmes;
- marcar filmes como assistidos;
- dar uma nota pessoal de 0 a 5, em intervalos de 0,5;
- escrever, editar e remover reviews pessoais;
- consultar suas páginas de favoritos e filmes assistidos;
- futuramente visualizar perfil, estatísticas e reviews próprias.

A aplicação precisa continuar simples de entender e evoluir com segurança. A
prioridade não é apenas adicionar funcionalidades, mas manter uma base clara para
aprender a lógica de backend, frontend, banco de dados, APIs externas e segurança.

---

## 2. Estado atual real

O estado abaixo representa o código atual, e não necessariamente os checkpoints
mais antigos da sessão.

### Já implementado

- Aplicação Flask funcionando.
- Frontend separado em HTML, CSS e JavaScript.
- Tema visual de cinema em tons ameixa/roxo.
- Loading, estados vazios, erros e poster ausente.
- Sidebar recolhível por hover e clique.
- Foco visual para navegação por teclado.
- Página principal em `/home`.
- Redirecionamento de `/` para `/home`.
- SQLite como fonte oficial dos dados pessoais.
- Autenticação com sessão Flask.
- Senhas armazenadas com hash do Werkzeug.
- Cadastro, login e logout.
- Usuários case-insensitive.
- Senhas case-sensitive.
- Bibliotecas separadas por usuário.
- Favoritos, assistidos, notas e reviews persistidos no SQLite.
- Modal de criação e edição de reviews.
- Limite de 2.000 caracteres para reviews.
- Páginas `/favoritos` e `/assistidos`.
- Camada de serviço para TMDb.
- Busca de filmes por título no TMDb.
- Busca de pessoas no TMDb.
- Descoberta de filmes por diretor no TMDb.
- Detalhes de filmes pelo `tmdbID`.
- Compatibilidade com detalhes antigos pelo `imdbID`.
- Nota pública e quantidade de votos do TMDb.
- Cache local de posters.
- Testes automatizados do backend.
- Interface inicial para escolher busca por título ou diretor.
- Seletor visual de busca por título ou diretor integrado ao tema do site.

### Provedor externo atual

O TMDb é o provedor oficial da aplicação.

O OMDb não deve voltar a ser usado pela aplicação. O legado OMDb (`services/omdb_service.py`,
`setup_ambiente.ps1` e os campos `imdbRating`/`Actors` no frontend) já foi removido na
Etapa 3 de limpeza.

Todas as chamadas ao TMDb usam `language=pt-BR` (títulos, sinopses e gêneros em português),
mas isso faz a API devolver o `poster_path` da versão localizada para o Brasil quando ela
existe, em vez do poster oficial de divulgação. Para o poster que fica salvo/cacheado
(`get_movie_by_tmdb_id`, usado sempre que um filme é favoritado, assistido, avaliado ou
revisado), `TmdbService` faz uma segunda busca com `language=en-US` só para pegar o
`poster_path` que o TMDb escolhe por padrão nesse idioma — que é o pôster oficial, e não uma
arte alternativa/fã-feita (a primeira tentativa foi filtrar por `iso_639_1` "sem idioma" na
lista de imagens, mas isso às vezes trazia arte alternativa sem título nenhum, então foi
trocado por essa segunda busca; ver `_default_poster_path` em `services/tmdb_service.py`). Se
essa segunda busca falhar, o poster de pt-BR obtido na primeira chamada é usado como reserva,
em vez de a busca inteira falhar. A prévia de busca (`/api/search`, antes de salvar o filme)
continua usando o poster localizado, de propósito — evitar N chamadas extras à API só para
uma prévia descartável.

### Resultado mais recente dos testes

Depois da correção da rota de diagnóstico do TMDb:

```text
Ran 17 tests
OK
```

O teste corrigido garante que `/api/tmdb-test` devolva HTTP 503 quando o serviço
TMDb não estiver configurado, em vez de gerar um erro HTTP 500.

---

## 3. Histórico da evolução

### 3.1. Aplicação inicial

A primeira versão era uma aplicação Flask pequena para pesquisar filmes em uma API
externa. O frontend e o backend estavam mais acoplados e ainda não havia contas ou
persistência real.

### 3.2. Organização visual

O frontend foi refinado gradualmente:

- CSS foi separado do HTML.
- Foi criado um visual inspirado em cinema.
- Foram adicionados estados de carregamento.
- Foram adicionadas mensagens de ausência de resultados.
- Posters inexistentes passaram a ter um estado visual.
- A sidebar foi criada para a futura coleção pessoal.
- Foram adicionados estados de foco para acessibilidade.

A lógica utilizada foi sempre separar:

1. estrutura da página em templates;
2. aparência em `static/styles.css`;
3. interação em `static/main.js` e `static/collection.js`.

### 3.3. Recursos pessoais

Foram adicionados:

- favoritos;
- assistidos;
- nota pessoal;
- reviews;
- edição de reviews;
- remoção de reviews;
- páginas de coleção.

Inicialmente, esses dados usavam `localStorage`. Isso funcionava somente no
navegador local e não permitia contas independentes.

### 3.4. Migração para SQLite

A aplicação foi migrada para SQLite para permitir:

- persistência real;
- dados separados por usuário;
- acesso por diferentes sessões;
- relacionamento entre usuários e filmes;
- reviews persistentes;
- validações no banco.

O banco fica em:

```text
data/app.sqlite3
```

O usuário temporário `local` foi usado durante a migração do `localStorage`.
Depois que os dados foram migrados, a conta temporária e o botão de migração foram
removidos do fluxo normal.

Ainda existem helpers antigos de migração em `database.py` e testes relacionados.
Eles são legado e devem ser removidos somente depois de uma limpeza planejada.

### 3.5. Autenticação e múltiplas contas

Foi adicionado:

- Flask Session;
- `/login`;
- `/logout`;
- `/register`;
- proteção de páginas pessoais;
- proteção de APIs pessoais;
- hash de senha;
- isolamento por `user_id`.

Foram criadas contas de teste e participantes:

- `teste`;
- `lannie`;
- `karmageddon`;
- `fael`.

A conta `teste` ainda existe. Não removê-la sem solicitação explícita.

Nathan recebeu os dados migrados da versão anterior:

- 5 filmes;
- 3 reviews.

A senha inicial criada para Nathan foi `nathan`. Isso é uma pendência de segurança
e não deve permanecer em um ambiente público.

### 3.6. Troca do OMDb pelo TMDb

O OMDb foi considerado limitado para o objetivo do projeto, principalmente por:

- busca fraca por diretores;
- ausência de um fluxo adequado de descoberta por pessoa;
- menos recursos para filtros e descoberta;
- necessidade de melhorar as informações públicas de avaliação.

O TMDb foi escolhido porque oferece:

- `/search/movie`;
- `/search/person`;
- `/discover/movie`;
- detalhes completos;
- créditos;
- IDs externos;
- nota pública;
- quantidade de votos;
- posters.

A migração foi feita criando uma camada de serviço e normalizando o formato do TMDb
para o formato que o frontend já conhecia.

---

## 4. Arquitetura atual

```text
Navegador
   |
   | HTML/CSS/JavaScript
   v
Flask (app.py)
   |
   +--> Autenticação e sessão
   |
   +--> APIs próprias (/api/...)
   |
   +--> TmdbService
   |       |
   |       +--> API TMDb
   |
   +--> PosterCache
   |
   +--> database.py
           |
           +--> SQLite
```

### 4.1. `app.py`

É o ponto central da aplicação Flask. Responsabilidades:

- criar o objeto Flask;
- carregar configurações;
- inicializar o banco;
- criar o serviço TMDb;
- controlar sessão;
- exigir login onde necessário;
- entregar templates;
- expor APIs;
- traduzir erros para respostas JSON;
- servir posters cacheados.

### 4.2. `config.py`

Centraliza:

- `TMDB_API_KEY`;
- `TMDB_URL`;
- `DATABASE_PATH`;
- `CACHE_DIR`;
- `SECRET_KEY`.

O token TMDb é obrigatório no import do módulo. Se não existir, a aplicação falha
cedo com uma mensagem explícita.

Atualmente a `SECRET_KEY` ainda possui um fallback previsível para desenvolvimento.
Isso deverá ser corrigido antes de expor a aplicação publicamente.

### 4.3. `services/movie_provider.py` (removido)

Existia um `Protocol` com o contrato comum de um provedor de filmes, pensado para o
restante da aplicação não conhecer detalhes específicos de uma API externa. Como só
o TMDb é usado (o OMDb foi removido na Etapa 3) e o contrato já estava desatualizado
(nem declarava `get_movie_by_tmdb_id`, usado o tempo todo), o módulo foi removido.
`app.py` usa `services/tmdb_service.py` diretamente, sem abstração intermediária.

### 4.4. `services/tmdb_service.py`

Responsável por:

- validar consultas;
- validar IMDb IDs antigos;
- enviar autenticação Bearer;
- configurar idioma `pt-BR`;
- aplicar timeout;
- tratar erros HTTP;
- converter respostas TMDb;
- montar URLs de posters;
- pesquisar filmes;
- pesquisar pessoas;
- descobrir filmes por diretor;
- buscar detalhes por TMDb ID;
- localizar filmes antigos pelo IMDb ID;
- extrair diretores;
- extrair nota pública e votos.

O serviço nunca deve expor o token em mensagens, logs ou respostas HTTP.

### 4.5. `database.py`

Responsável por:

- abrir conexões SQLite;
- ativar foreign keys;
- criar o schema;
- criar usuários;
- autenticar usuários;
- salvar filmes;
- carregar biblioteca;
- salvar estado pessoal;
- salvar reviews;
- manter relações entre usuários e filmes.

O arquivo ainda contém funções antigas de migração e transferência. Elas devem ser
tratadas como legado até uma remoção futura.

### 4.6. Frontend

#### `templates/index.html`

Página principal da busca. Contém:

- cabeçalho;
- seletor de tipo de busca;
- input de busca;
- botão;
- painel de sugestões;
- área de poster;
- área de detalhes;
- sidebar da coleção.

#### `static/main.js`

Responsável por:

- debounce da busca;
- busca por título;
- busca por diretor;
- seleção de pessoa;
- descoberta de filmes do diretor;
- carregamento de detalhes;
- rendering do poster;
- favoritos;
- assistidos;
- notas;
- reviews;
- loading e mensagens de erro.

O seletor `#searchType` decide o modo de busca:

- `Título` chama `GET /api/search?q=...`;
- `Diretor` chama `GET /api/directors?q=...`.

No modo diretor, o usuário seleciona uma pessoa e depois escolhe um filme
retornado por `GET /api/directors/<person_id>/movies`.

#### `templates/collection.html` e `static/collection.js`

Renderizam favoritos e assistidos carregados da API `/api/library`.

Os links antigos da coleção usam IMDb ID e dependem da rota de compatibilidade.

#### `static/styles.css`

Contém o tema visual, layout, responsividade, estados de loading, cards, modal,
sidebar e estrelas.

O seletor `#searchType` foi estilizado no padrão visual do site:

- fundo escuro;
- bordas arredondadas;
- cores ameixa e roxo;
- foco com borda e brilho roxo;
- comportamento responsivo em telas menores.

A opção escolhida foi o **seletor integrado**:

```text
[Título ▼] [Digite o nome do filme...] [Buscar]
```

Também foram consideradas cinco opções de design:

1. seletor integrado, opção aplicada;
2. abas de busca;
3. botão segmentado;
4. seletor com ícones;
5. seletor acima do campo de busca.

---

## 5. Fluxo principal da aplicação

### 5.1. Inicialização

1. O PowerShell define `TMDB_API_KEY`.
2. `app.py` importa `config.py`.
3. `config.py` valida o token.
4. O Flask é criado.
5. O `TmdbService` é criado.
6. O cache de posters é criado.
7. O SQLite é inicializado.
8. A aplicação começa a aceitar requisições.

### 5.2. Login

1. O usuário acessa `/login`.
2. Envia username e senha.
3. `authenticate_user()` consulta o banco.
4. O username é comparado sem diferenciar maiúsculas/minúsculas.
5. A senha é validada contra o hash.
6. A sessão é limpa e recebe `user_id` e `username`.
7. O usuário é redirecionado para `/home`.

### 5.3. Busca por título

1. O usuário escolhe `Título`.
2. `main.js` envia `/api/search?q=...`.
3. `app.py` valida a consulta pelo `TmdbService`.
4. O serviço chama `/search/movie` no TMDb.
5. O resultado é normalizado.
6. O frontend mostra título, ano e tipo.
7. Ao clicar, o frontend usa o `tmdbID`.
8. A aplicação chama `/api/movie/tmdb/<tmdb_id>`.
9. O detalhe é normalizado, o poster é cacheado e o card é renderizado.

### 5.4. Busca por diretor

1. O usuário escolhe `Diretor`.
2. `main.js` envia `/api/directors?q=...`.
3. O backend chama `/search/person`.
4. O frontend mostra candidatos.
5. O usuário escolhe uma pessoa.
6. O frontend envia `/api/directors/<person_id>/movies`.
7. O backend chama `/discover/movie` com `with_crew`.
8. Os filmes aparecem como sugestões.
9. O clique abre `/api/movie/tmdb/<tmdb_id>`.

### 5.5. Favorito, assistido e nota

1. O detalhe é carregado.
2. O frontend identifica o filme pelo `imdbID`.
3. O estado atual vem de `/api/library`.
4. O usuário altera favorito, assistido ou nota.
5. O frontend envia `PUT /api/library/<imdb_id>`.
6. O backend salva o filme e o vínculo com o usuário.
7. A resposta atualiza o cache local do frontend.

### 5.6. Review

1. O usuário abre o modal.
2. Escreve até 2.000 caracteres.
3. O frontend envia `PUT /api/reviews/<imdb_id>`.
4. O backend cria ou atualiza a review.
5. Se o texto estiver vazio, a review é removida.
6. A interface atualiza o card.

---

## 6. Rotas atuais

### Páginas

| Rota | Função | Login |
|---|---|---|
| `/` | Redireciona para `/home` | Não |
| `/home` | Página principal | Sim |
| `/login` | Login | Não |
| `/register` | Cadastro | Não |
| `/logout` | Encerra sessão | Não |
| `/favoritos` | Coleção de favoritos | Sim |
| `/assistidos` | Coleção de assistidos | Sim |

### APIs de catálogo

| Rota | Função |
|---|---|
| `GET /api/search?q=...` | Busca filmes por título |
| `GET /api/movie/tmdb/<tmdb_id>` | Detalhes novos pelo TMDb ID |
| `GET /api/movie/<imdb_id>` | Compatibilidade com filmes antigos |
| `GET /api/directors?q=...` | Busca pessoas para diretores |
| `GET /api/directors/<person_id>/movies` | Filmes de um diretor |
| `GET /api/tmdb-test?q=...` | Diagnóstico autenticado do TMDb |

### APIs pessoais

| Rota | Função |
|---|---|
| `GET /api/library` | Biblioteca do usuário atual |
| `PUT /api/library/<imdb_id>` | Salva favorito, assistido e nota |
| `PUT /api/reviews/<imdb_id>` | Cria, altera ou remove review |

As APIs pessoais dependem da sessão e devem sempre usar o `user_id` da sessão, nunca
um usuário enviado pelo frontend.

---

## 7. Banco de dados atual

### `users`

Armazena:

- `id`;
- `username`;
- `display_name`;
- `password_hash`;
- `created_at`.

### `movies`

Armazena o catálogo conhecido pela aplicação:

- `imdb_id` como chave primária atual;
- título;
- ano;
- tipo;
- poster original;
- caminho do poster em cache;
- gênero;
- data de criação.

### `user_movies`

É a relação entre usuário e filme:

- `user_id`;
- `imdb_id`;
- `favorite`;
- `watched`;
- `rating`;
- datas de criação e atualização.

A chave primária é `(user_id, imdb_id)`.

### `reviews`

Armazena:

- `id`;
- `user_id`;
- `imdb_id`;
- corpo;
- datas de criação e atualização.

Existe uma única review por usuário e filme.

---

## 8. Problema central pendente: identificadores

Este é o ponto técnico mais importante antes de continuar adicionando recursos.

O TMDb usa `tmdbID`, mas o banco atual usa `imdb_id` como chave principal.

Isso cria o seguinte risco:

1. O TMDb retorna um filme válido.
2. O filme possui `tmdbID`.
3. O filme não possui IMDb ID externo.
4. O frontend tenta salvar usando `movie.imdbID`.
5. A URL de persistência fica inválida ou não consegue criar o registro.

### Decisão recomendada

Adicionar `tmdb_id` ao modelo do banco e tornar o identificador externo explícito.
Uma migração cuidadosa pode manter os filmes antigos por IMDb e adicionar suporte a
filmes novos apenas pelo TMDb.

Antes de alterar o schema, o próximo agente deve:

1. mapear todas as referências a `imdbID`;
2. definir uma chave canônica;
3. criar migração SQLite;
4. manter compatibilidade com os 5 filmes existentes de Nathan;
5. atualizar as APIs pessoais;
6. atualizar `main.js`;
7. atualizar `collection.js`;
8. adicionar testes para filmes sem IMDb ID.

Não resolver isso usando um valor falso de IMDb ID. O identificador precisa continuar
semanticamente correto.

---

## 9. Forma recomendada de pensar antes de alterar

### 9.1. Separar descoberta de persistência

A API externa serve para descobrir e enriquecer filmes. O banco serve para guardar o
catálogo mínimo e as escolhas pessoais.

Não misture:

- erro do TMDb;
- erro do banco;
- erro de sessão;
- erro de renderização.

Cada camada deve ter uma responsabilidade clara.

### 9.2. Seguir o fluxo completo

Para qualquer nova funcionalidade, rastrear:

```text
interface
  -> fetch
  -> rota Flask
  -> serviço
  -> banco ou API externa
  -> resposta
  -> estado visual
```

Uma alteração só está completa quando todas as partes desse fluxo foram revisadas.

### 9.3. Pensar em contratos de dados

O frontend depende de nomes estáveis, como:

- `Title`;
- `Year`;
- `Poster`;
- `Genre`;
- `Plot`;
- `Director`;
- `public_rating`;
- `vote_count`;
- `tmdbID`;
- `imdbID`.

Se um campo mudar, atualizar o produtor, o consumidor e os testes na mesma etapa.

### 9.4. Tratar erros explicitamente

Erros externos devem informar:

- status HTTP quando disponível;
- mensagem compreensível;
- código interno estável.

Nunca:

- esconder erro com resposta de sucesso;
- engolir exceção ampla;
- retornar dados fictícios;
- revelar token;
- depender silenciosamente de processo Flask antigo.

### 9.5. Mudar uma camada por vez

Ordem recomendada:

1. contrato e modelo;
2. serviço;
3. rota;
4. frontend;
5. testes;
6. teste manual no navegador.

Isso reduz o risco de não saber qual camada causou a falha.

---

## 10. Próximas etapas recomendadas

### Etapa 1 — Resolver identificadores (concluída)

Prioridade máxima.

- adicionar `tmdb_id` ao schema;
- manter `imdb_id` opcional para filmes sem correspondência;
- definir identificador de biblioteca;
- preservar registros existentes;
- criar testes de filme sem IMDb.

### Etapa 2 — Validar fluxos reais com o token (concluída)

Com o Flask iniciado no terminal correto:

- buscar um título;
- abrir detalhes;
- buscar um diretor;
- abrir um filme do diretor;
- favoritar;
- marcar como assistido;
- atribuir nota;
- criar e remover review;
- recarregar a página;
- confirmar persistência.

### Etapa 3 — Limpeza do legado OMDb (concluída)

Somente depois de confirmar que o TMDb cobre os fluxos:

- remover `services/omdb_service.py`; ✅
- remover imports antigos; ✅ (nada importava o módulo)
- remover configuração OMDb restante; ✅ (nenhuma restava em `config.py`)
- remover testes específicos do OMDb; ✅ (nenhum existia na suíte)
- revisar `setup_ambiente.ps1`; ✅ (removido, substituído por `setup_tmdb.ps1`)
- atualizar documentação antiga. ✅

### Etapa 4 — Limpeza da migração antiga (concluída)

Depois de confirmar que ninguém precisa mais dela:

- remover `migrate_local_library`; ✅ (já não existia no código)
- remover `transfer_library_user`; ✅ (já não existia no código)
- remover testes correspondentes; ✅ (nenhum restava na suíte)
- preservar o banco atual. ✅

### Etapa 5 — Segurança

Adiada a pedido do usuário (não é prioridade no momento); dividida em subetapas
independentes para retomar mais tarde, em qualquer ordem.

#### Etapa 5.1 — Configuração de ambiente

- exigir `FLASK_SECRET_KEY` em ambientes não locais;
- configurar cookies seguros em produção.

#### Etapa 5.2 — Contas e senhas

- remover senha inicial fixa de Nathan;
- criar fluxo de troca de senha;
- decidir se o cadastro deve continuar aberto.

#### Etapa 5.3 — Redirecionamento pós-login

- corrigir validação de `next`;
- bloquear redirecionamentos iniciados por `//`.

#### Etapa 5.4 — Proteção contra abuso

- avaliar limite de tentativas de login;
- considerar proteção CSRF para operações de alteração.

### Etapa 6 — Produto (concluída)

Dividida em subetapas independentes para ir uma de cada vez, em qualquer ordem. Todas as
subetapas foram concluídas ou decididas como não aplicáveis (6.5).

#### Etapa 6.6 — Painel-resumo na /home (concluída, adicionada depois)

Pedido do usuário após fechar as subetapas 6.1-6.5: "precisamos de uma tela tipo dashboard,
uma tela de atividades ou algo parecido". Em vez de uma página nova, o resumo foi encaixado
abaixo do painel de busca na própria `/home` (decisão do usuário — a busca continua sendo o
primeiro coisa da página), com dois blocos lado a lado:

- seus números (assistidos, favoritos, reviews, nota média), reaproveitando
  `get_user_statistics`; ✅
- "Atividade recente" (todos da casa, não só o usuário logado), com o nome de quem fez cada
  ação — nova função `get_household_activity` em `database.py`, no mesmo formato de
  `get_user_activity` mas sem filtrar por `user_id` e trazendo `display_name`. ✅

"Casa" é definida por `config.HOUSEHOLD_USERNAMES` (Nathan, lannie, karmageddon) — contas
como fael, Tega e alien podem usar o app normalmente, mas ficam fora dessa comparação/dessa
atividade recente, porque a Etapa 6.4/6.6 é sobre os três parceiros, não sobre todo mundo com
conta. `get_household_statistics` e `get_household_activity` agora recebem essa lista de
usernames como parâmetro, em vez de olhar para a tabela `users` inteira.

#### Etapa 6.1 — Perfil e conta (concluída)

- tela de perfil; ✅ (`/perfil`, template `profile.html` — reestruturada depois na Etapa 6.7)
- alteração de senha; ✅ (`/perfil/senha`; também resolve o item equivalente da Etapa 5.2)
- exclusão da própria conta. ✅ (`/perfil/excluir`, exige senha atual)

#### Etapa 6.7 — Perfil = identidade + estatísticas; ações viraram /perfil/conta (concluída, adicionada depois)

Pedido do usuário: "a /perfil não precisa ter essas ações" (referindo-se aos formulários de
nome/senha/exclusão). `/perfil` deixou de ser uma tela de ações e virou a tela de identidade —
absorveu o conteúdo que estava em `/estatisticas` (que foi removida): dados da conta (nome,
username, data de criação) + estatísticas pessoais e da casa, com um link "Gerenciar conta →".

- `/perfil` agora renderiza `profile.html` com `profile`, `stats` (`get_user_statistics`) e
  `household` (`get_household_statistics`); ✅
- nova rota `/perfil/conta` (`account.html`) recebeu os três formulários que antes ficavam em
  `/perfil` (nome, senha, exclusão); as rotas `POST /perfil/nome`, `/perfil/senha` e
  `/perfil/excluir` continuam com os mesmos endpoints, só passaram a renderizar `account.html`
  em vez de `profile.html` nos casos de erro/sucesso; ✅
- rota `/estatisticas` e template `statistics.html` removidos — o link "◌ Estatísticas" saiu
  da sidebar de todas as páginas (o acesso agora é só via "☺ Perfil"). ✅

#### Etapa 6.2 — Reviews e atividade (concluída)

- página de reviews; ✅ (`/reviews`, reaproveita `collection.html`/`collection.js` com um terceiro tipo de coleção)
- histórico de atividade. ✅ (`/atividade`, `activity.html`, junta `user_movies` e `reviews` por `updated_at`; um evento por linha do banco, já que não existe log por ação)

#### Etapa 6.3 — Descoberta e organização (concluída)

- filtros por gênero, ano e nota pública; ✅ (client-side em `collection.js`, a partir dos dados já carregados de `/api/library`; nota pública salva em `movies.public_rating`, coluna nova adicionada por migração aditiva no schema versão 3)
- paginação. ✅ (botão "Carregar mais" incremental, 12 filmes por página)

#### Etapa 6.4 — Estatísticas pessoais (concluída)

- estatísticas pessoais. ✅ (`/estatisticas`, `statistics.html`: assistidos, favoritos, reviews,
  nota média, gênero/década favoritos, melhor/pior avaliado — `get_user_statistics` em
  `database.py`)
- comparação entre os participantes da casa, incluída a pedido do usuário ao definir o escopo
  desta etapa. ✅ (ranking de quem assistiu mais, filmes em comum e maior divergência de nota
  entre os três — `get_household_statistics` em `database.py`)

#### Etapa 6.5 — Privacidade de perfis (não se aplica)

- perfis privados ou compartilhados entre participantes. Decisão do usuário: os três
  participantes (Nathan, lannie e karmageddon) já confiam uns nos outros e preferem ver a
  atividade um do outro — foi inclusive por isso que pediram a comparação entre os três na
  Etapa 6.4. Construir privacidade por item ou por perfil ficaria sem uso real, então a etapa
  foi encerrada sem implementação. Se o cenário mudar (ex.: mais pessoas entrarem no app), essa
  decisão pode ser revisitada.

### Etapa 7 — Acesso remoto via VPN

Contexto: lannie e karmageddon (parceiros do usuário) já têm conta no app, mas moram
em casas diferentes e hoje só conseguem acessar se estiverem na mesma máquina/rede
onde o Flask roda (`127.0.0.1`). Decisão registrada em conversa: usar uma VPN pessoal
(ex.: Tailscale) em vez de hospedagem na nuvem, porque topam que o app só fique
disponível quando o PC do Nathan estiver ligado — evita o custo e a superfície de
ataque extra de expor a aplicação à internet pública.

#### Etapa 7.1 — Configurar VPN pessoal

- instalar uma VPN mesh (ex.: Tailscale) no PC do Nathan e nos dispositivos de lannie
  e karmageddon;
- confirmar que os três conseguem se enxergar na rede virtual.

#### Etapa 7.2 — Preparar a aplicação para a rede (concluída)

- trocar o `host` do Flask de `127.0.0.1` para `0.0.0.0` (ou parametrizar via env var); ✅
  (`config.HOST`, lido de `FLASK_HOST`, padrão `0.0.0.0`; pode voltar a `127.0.0.1` via env
  var se algum dia quiserem travar o acesso só à própria máquina)
- gerar e configurar um `FLASK_SECRET_KEY` real, substituindo o valor padrão
  `'local-development-secret'` usado hoje; ✅ (`config.get_secret_key`: usa `FLASK_SECRET_KEY`
  se definida, senão gera uma chave aleatória de 32 bytes na primeira execução e guarda em
  `data/secret_key.txt` — arquivo git-ignorado — para não derrubar sessões a cada reinício)
- revisar `setup_tmdb.ps1` para esse novo modo de uso. ✅ (mostra o IP do Tailscale, se
  instalado, para compartilhar com quem vai acessar remotamente)

Pendente: nada neste momento. `debug=True` continua ativo em `app.py` (decisão de manter,
não mexida aqui) — o depurador do Werkzeug expõe um console interativo em caso de erro não
tratado; como a rede agora inclui outros dispositivos (mesmo que só os da VPN, Etapa 7.1),
vale reavaliar isso quando a Etapa 5 (Segurança) for retomada.

#### Etapa 7.3 — Validar o acesso das contas existentes

- confirmar login de lannie e karmageddon pela VPN, em dispositivos diferentes do PC
  do Nathan;
- redefinir a senha de qualquer uma das contas, se necessário.

---

## 11. Validação local

### Preparar e iniciar

```powershell
cd C:\Users\Nathan.Araujo\Downloads\code\apifilmes_web_project
.\setup_tmdb.ps1
```

O script:

1. entra na pasta do projeto;
2. cria `.venv` se necessário;
3. instala `requirements.txt`;
4. solicita o token TMDb sem exibi-lo;
5. define `TMDB_API_KEY` apenas na sessão atual;
6. inicia `app.py`.

### Executar testes

```powershell
cd C:\Users\Nathan.Araujo\Downloads\code\apifilmes_web_project
$env:TMDB_API_KEY='test-key'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes usam mocks para não depender da internet.

### Verificar sintaxe Python

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py config.py database.py services\tmdb_service.py
```

### Testar manualmente

Com autenticação ativa:

```text
/api/search?q=Inception
/api/directors?q=Christopher%20Nolan
/api/directors/525/movies
/api/movie/tmdb/27205
/api/movie/tt0092991
/api/library
/api/tmdb-test?q=Sam%20Raimi
```

Não colocar tokens reais em arquivos, commits, logs ou mensagens.

---

## 12. Problemas conhecidos

### Segurança

- `SECRET_KEY` tem fallback previsível.
- Nathan é criado com senha inicial fixa.
- O cadastro é aberto.
- O parâmetro `next` precisa de validação mais rigorosa.
- Cookies de produção ainda precisam ser endurecidos.
- Operações `PUT` ainda devem ser avaliadas para proteção CSRF.

### Dados

- O banco usa IMDb como chave obrigatória.
- Filmes TMDb sem IMDb podem falhar ao serem salvos.
- `tmdb_id` ainda não está no schema.

### Legado

- `services/omdb_service.py` foi removido (Etapa 3 concluída).
- `migrate_local_library` e `transfer_library_user` (migração antiga de biblioteca
  local para multiusuário) já não existem no código nem na suíte de testes
  (Etapa 4 concluída); os únicos helpers de migração hoje são os de `migrations.py`,
  usados para converter o schema antigo (`imdb_id`) para `tmdb_id`.
- Checkpoints antigos podem mencionar OMDb como provedor oficial; não seguir essa
  informação sem conferir o código atual.

### Operação

- Variáveis definidas em um terminal não aparecem automaticamente em outro.
- Processos Flask antigos podem ocupar a porta 5000.
- Um processo antigo na porta 5000 já causou a abertura de uma versão desatualizada
  da aplicação; o setup agora interrompe com uma mensagem clara se a porta estiver
  ocupada.
- Em Windows com proxy ou certificado corporativo, o `requests` pode rejeitar o
  certificado HTTPS mesmo quando o navegador e o PowerShell funcionam. O serviço
  usa `truststore` para consultar os certificados confiáveis do Windows sem
  desativar a validação TLS.
- Sempre confirmar o PID específico do processo antes de reiniciar o servidor.
- Não usar comandos destrutivos amplos para “limpar” o projeto.

---

## 13. Convenções de implementação

- Usar caminhos Windows nos comandos do ambiente.
- Usar caminhos com `/` somente em links Markdown nas respostas.
- Manter comentários explicativos quando ajudarem o aprendizado.
- Comentários novos em Python e JavaScript devem seguir o padrão solicitado:
  `# w`.
- Evitar comentários óbvios.
- Preferir funções pequenas e responsabilidades separadas.
- Reutilizar helpers existentes.
- Não usar `as any` ou casts desnecessários.
- Não esconder falhas com defaults silenciosos.
- Não reverter mudanças que não foram feitas na tarefa atual.
- Não criar arquivos de planejamento separados sem solicitação.
- Testar alterações relacionadas no mesmo ciclo.

---

## 14. Checklist para o próximo agente

Antes de editar:

- [ ] Ler este documento.
- [ ] Conferir o estado real do código.
- [ ] Não assumir que checkpoints antigos estão atualizados.
- [ ] Identificar se a mudança envolve frontend, backend, banco e testes.
- [ ] Verificar se existe algum processo Flask antigo.

Durante a edição:

- [ ] Fazer uma mudança coerente por etapa.
- [ ] Preservar os filmes e reviews existentes.
- [ ] Não expor o token TMDb.
- [ ] Adicionar ou atualizar testes.
- [ ] Usar comentários novos com `# w`.

Depois da edição:

- [ ] Executar a suíte de testes.
- [ ] Validar sintaxe.
- [ ] Testar a rota alterada.
- [ ] Testar o fluxo no navegador quando a mudança for visual.
- [ ] Explicar o que mudou, por quê e qual é o próximo passo.

---

## 15. Resumo executivo

A aplicação já deixou de ser uma busca simples e se tornou uma aplicação Flask com:

- contas;
- sessões;
- SQLite;
- bibliotecas individuais;
- favoritos;
- assistidos;
- notas;
- reviews;
- cache de posters;
- TMDb como provedor oficial;
- busca por título;
- busca por diretor.

O próximo grande trabalho não é adicionar mais uma tela. É corrigir o modelo de
identificadores para que o TMDb seja realmente a fonte principal sem quebrar os
filmes antigos armazenados por IMDb.

Depois disso, a ordem segura é:

```text
identificadores
  -> validação real
  -> remoção do legado OMDb
  -> limpeza da migração antiga
  -> segurança
  -> perfil, reviews e estatísticas
```

Essa ordem reduz regressões e mantém a aplicação compreensível para quem está
aprendendo como cada camada funciona.
