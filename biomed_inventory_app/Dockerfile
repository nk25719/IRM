FROM node:20-alpine AS pm-frontend-build

WORKDIR /pm-frontend
COPY pm-frontend/package*.json ./
RUN npm ci
COPY pm-frontend/ ./
RUN npm run build

FROM python:3.11

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=pm-frontend-build /pm-frontend/dist/ /app/app/static/pm/

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
