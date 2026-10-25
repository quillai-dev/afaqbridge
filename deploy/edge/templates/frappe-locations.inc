client_max_body_size ${EDGE_CLIENT_MAX_BODY_SIZE};
set $frontend http://${FRONTEND_UPSTREAM};

location = /api/method/login {
    limit_req zone=login burst=20 nodelay;
    include /etc/nginx/afaqbridge/proxy.inc;
    proxy_read_timeout ${EDGE_READ_TIMEOUT}s;
    proxy_send_timeout ${EDGE_READ_TIMEOUT}s;
    proxy_pass $frontend;
}
location /socket.io {
    include /etc/nginx/afaqbridge/proxy.inc;
    proxy_read_timeout ${EDGE_WS_TIMEOUT}s;
    proxy_send_timeout ${EDGE_WS_TIMEOUT}s;
    proxy_buffering off;
    proxy_pass $frontend;
}
location / {
    include /etc/nginx/afaqbridge/proxy.inc;
    proxy_read_timeout ${EDGE_READ_TIMEOUT}s;
    proxy_send_timeout ${EDGE_READ_TIMEOUT}s;
    proxy_pass $frontend;
}
