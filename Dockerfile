# korean-tax-mcp — stdio MCP 서버 (조회 도구는 키 없이 동작)
FROM python:3.12-slim
RUN pip install --no-cache-dir korean-tax-mcp
ENTRYPOINT ["korean-tax-mcp"]
