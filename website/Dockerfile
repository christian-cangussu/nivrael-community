FROM nginx:alpine

ENV PORT=80

RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY miniapp /usr/share/nginx/html/miniapp

EXPOSE ${PORT}

CMD ["nginx", "-g", "daemon off;"]
