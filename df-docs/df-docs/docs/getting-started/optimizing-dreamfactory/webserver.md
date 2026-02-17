---
sidebar_position: 2
title: Web Server
id: web-server
keywords:
  - NGINX
  - Apache
  - PHP-FPM
  - web server optimization
  - reverse proxy
---

# Web Server Optimization

The web server is a critical component of your DreamFactory deployment. Proper configuration of NGINX or Apache, combined with PHP-FPM tuning, can dramatically improve API throughput and response latency. This guide covers the essential settings for production DreamFactory environments.

## NGINX Configuration

NGINX is the recommended web server for DreamFactory due to its efficient event-driven architecture and superior performance under high concurrency. Below is a production-ready NGINX configuration for DreamFactory:

```nginx
server {
    listen 80;
    server_name api.example.com;
    root /opt/dreamfactory/public;
    index index.php;

    # Gzip compression for API responses
    gzip on;
    gzip_types application/json text/plain text/css application/javascript;
    gzip_min_length 256;
    gzip_comp_level 5;

    # Increase client body size for file uploads
    client_max_body_size 100M;

    # Keepalive connections
    keepalive_timeout 65;
    keepalive_requests 1000;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    location ~ \.php$ {
        fastcgi_pass unix:/run/php/php8.2-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;

        # Buffer and timeout settings for large API responses
        fastcgi_buffer_size 32k;
        fastcgi_buffers 16 32k;
        fastcgi_read_timeout 300;
    }

    # Deny access to hidden files
    location ~ /\. {
        deny all;
    }
}
```

### Key NGINX Tuning Parameters

In the main `nginx.conf` file, adjust the following global settings:

```nginx
worker_processes auto;           # Match the number of CPU cores
worker_connections 4096;         # Max simultaneous connections per worker
multi_accept on;                 # Accept multiple connections at once
```

Enable gzip compression to reduce bandwidth usage for JSON API responses. This is especially important for endpoints returning large datasets.

## Apache Configuration

If you are using Apache instead of NGINX, ensure the following modules are enabled:

```bash
sudo a2enmod rewrite deflate headers ssl
sudo systemctl restart apache2
```

A minimal Apache virtual host configuration for DreamFactory:

```apache
<VirtualHost *:80>
    ServerName api.example.com
    DocumentRoot /opt/dreamfactory/public

    <Directory /opt/dreamfactory/public>
        AllowOverride All
        Require all granted
        Options -Indexes +FollowSymLinks
    </Directory>

    # Enable compression
    <IfModule mod_deflate.c>
        AddOutputFilterByType DEFLATE application/json text/html text/plain text/css application/javascript
    </IfModule>
</VirtualHost>
```

:::warning
`AllowOverride All` is required for DreamFactory's `.htaccess` routing rules. Without it, all API routes will return 404 errors.
:::

## PHP-FPM Pool Tuning

PHP-FPM (FastCGI Process Manager) manages the pool of PHP worker processes that handle API requests. Proper pool sizing is critical for handling concurrent API traffic.

Edit your PHP-FPM pool configuration (typically at `/etc/php/8.2/fpm/pool.d/www.conf`):

```ini
[www]
; Use static process management for predictable performance
pm = static
pm.max_children = 50

; Or use dynamic management for variable workloads
; pm = dynamic
; pm.max_children = 50
; pm.start_servers = 10
; pm.min_spare_servers = 5
; pm.max_spare_servers = 20

; Recycle workers after handling N requests (prevents memory leaks)
pm.max_requests = 1000

; Slow request logging for debugging
request_slowlog_timeout = 10s
slowlog = /var/log/php-fpm-slow.log
```

### Calculating pm.max_children

The formula for determining the maximum number of PHP-FPM workers:

```
pm.max_children = Available RAM / Average PHP process memory
```

For example, on a server with 4GB of RAM dedicated to PHP-FPM and an average PHP process size of 50MB:

```
pm.max_children = 4096MB / 50MB = ~80
```

Reserve memory for the operating system, database, and web server. A conservative rule is to allocate 60-70% of total RAM to PHP-FPM.

## SSL/TLS Configuration

Always serve DreamFactory APIs over HTTPS in production. A recommended NGINX SSL configuration:

```nginx
server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/ssl/certs/api.example.com.pem;
    ssl_certificate_key /etc/ssl/private/api.example.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # HSTS header
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # ... rest of server block
}
```

## Reverse Proxy Considerations

When running DreamFactory behind a load balancer or reverse proxy (e.g., AWS ALB, Cloudflare, HAProxy), configure the following in your `.env` file:

```bash
# Trust proxy headers for correct client IP detection
TRUST_PROXIES=*

# If the proxy terminates SSL
HTTPS_FORCE=true
```

Ensure the proxy forwards the `X-Forwarded-For`, `X-Forwarded-Proto`, and `Host` headers so DreamFactory can correctly identify client IPs and generate proper URLs in API responses.
