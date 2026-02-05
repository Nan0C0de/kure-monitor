# Build stage
FROM node:18-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Runtime stage - minimal nginx image
FROM nginx:1.27-alpine

RUN addgroup -g 1001 -S kure && \
    adduser -S -D -H -u 1001 -h /var/cache/nginx -s /sbin/nologin -G kure kure

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN chown -R kure:kure /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /usr/share/nginx/html && \
    touch /var/run/nginx.pid && chown kure:kure /var/run/nginx.pid

USER kure
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
