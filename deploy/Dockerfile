FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV CARDS_DB=/data/serving.db CARDS_USAGE_DB=/data/usage.db
EXPOSE 8080
CMD ["python", "-m", "card_agreements_mcp", "--http"]
