# JK Assistance - admission portal + API.
# Works on Render (sets $PORT) and Hugging Face Docker Spaces (port 7860, user id 1000).
FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 PORT=7860
WORKDIR $HOME/app

COPY --chown=user requirements-app.txt .
RUN pip install --no-cache-dir --user -r requirements-app.txt

# The app only needs its code, the knowledge files, the web page and the admission sources.
COPY --chown=user jk_assistance ./jk_assistance
COPY --chown=user knowledge ./knowledge
COPY --chown=user web ./web
COPY --chown=user raw ./raw
COPY --chown=user documents ./documents

EXPOSE 7860
HEALTHCHECK CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/health')"
CMD ["sh", "-c", "uvicorn jk_assistance.api:app --host 0.0.0.0 --port ${PORT}"]
