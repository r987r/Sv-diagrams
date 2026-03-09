FROM nginx:alpine

LABEL maintainer="r987r" \
      description="SV Diagrams – 3D SystemVerilog/UVM viewer"

# Copy static viewer (index.html, main.js, style.css, vendor/)
COPY viewer/   /usr/share/nginx/html/

# Copy pre-generated diagram metadata
COPY metadata/ /usr/share/nginx/html/metadata/

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
  CMD wget -qO- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
