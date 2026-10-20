FROM node:24-slim AS kyc-build
WORKDIR /kyc
COPY kyc-dashboard/package*.json ./
RUN npm ci
COPY kyc-dashboard/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY aml_poc ./aml_poc
COPY data ./data
COPY .streamlit ./.streamlit
COPY --from=kyc-build /kyc/dist ./kyc-dashboard/dist
RUN pip install --no-cache-dir --no-deps .
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8001 8501
CMD ["python", "-m", "uvicorn", "aml_poc.api:app", "--host", "0.0.0.0", "--port", "8001"]
