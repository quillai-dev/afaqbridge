client_max_body_size ${EDGE_DOCUSEAL_MAX_BODY_SIZE};
set $docuseal http://${DOCUSEAL_UPSTREAM};
location / {
    include /etc/nginx/afaqbridge/proxy.inc;
    proxy_read_timeout ${EDGE_READ_TIMEOUT}s;
    proxy_send_timeout ${EDGE_READ_TIMEOUT}s;
    proxy_pass $docuseal;
}
