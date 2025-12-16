FROM python:3.13-slim

# Evitam buffers (logs immediats)
ENV PYTHONUNBUFFERED=1

# Directori de treball
WORKDIR /app

# Copiem uv al /bin
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copiam només els fitxers de dependències (millor cache)
COPY pyproject.toml uv.lock ./

# Instal·lam dependències (entorn del sistema, no venv)
RUN uv sync

# Copiam el codi
COPY main.py .

# Comanda per defecte
CMD ["uv", "run", "python", "main.py"]