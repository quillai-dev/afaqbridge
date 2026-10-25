# Forwarding headers. X-Forwarded-For is OVERWRITTEN (not appended) so clients cannot spoof their address.
proxy_http_version 1.1;
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $http_host;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_redirect off;
proxy_connect_timeout 10s;
# Upstream's frontend adds HSTS with includeSubDomains;preload on every response. Preloading is an irreversible,
# domain-wide decision, so the edge drops it and sends its own plain HSTS header (TLS server blocks only).
proxy_hide_header Strict-Transport-Security;
