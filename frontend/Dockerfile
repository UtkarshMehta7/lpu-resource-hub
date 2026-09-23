# Frontend image: build the static bundle, serve it with nginx.
FROM node:22-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Vite bakes VITE_* values in at build time, so the API URL is a build arg.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine AS runtime
# nginx.conf is a template: ${PORT} and ${API_ORIGIN} are substituted at
# container start by nginx's own entrypoint, which processes
# /etc/nginx/templates/*.template. Leaving them unsubstituted served a
# broken CSP that blocked every API call.
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV PORT=80 \
    API_ORIGIN="'self'"
EXPOSE 80
