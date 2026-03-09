FROM nginx:alpine
COPY viewer/   /usr/share/nginx/html/
COPY metadata/ /usr/share/nginx/html/metadata/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
