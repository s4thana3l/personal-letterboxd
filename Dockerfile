FROM python:3.11-slim

WORKDIR /app

# w Instala dependências do sistema para requests/truststore
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# w Copia e instala Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# w Copia toda a aplicação
COPY . .

# w Cria diretórios para dados persistentes
RUN mkdir -p /app/data /app/cache/posters

# w Expõe porta 8080 (padrão do Fly.io)
EXPOSE 8080

# w Roda a aplicação com gunicorn (production WSGI server)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "app:app"]
