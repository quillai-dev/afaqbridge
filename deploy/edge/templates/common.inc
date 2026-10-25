# Shared by every server block. Rendered text only; no secrets.
server_tokens off;
ignore_invalid_headers on;          # drops headers with underscores / malformed names (like the previous Traefik setup)
resolver 127.0.0.11 valid=10s ipv6=off;   # Docker's embedded DNS: service names resolve lazily, so a restarting upstream never stops the edge from starting

map $http_upgrade $connection_upgrade { default upgrade; "" close; }
limit_req_zone $binary_remote_addr zone=login:10m rate=${EDGE_LOGIN_RATE};
limit_req_status 429;

# Health endpoint for the container healthcheck (never proxied)
server {
    listen 127.0.0.1:8081;
    location = /healthz { access_log off; return 200 "ok\n"; }
}
