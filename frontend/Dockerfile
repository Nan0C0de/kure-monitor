# Build stage
FROM node:18-alpine as build

WORKDIR /app
COPY package*.json ./
RUN npm install --only=production

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy build files
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]