---
sidebar_position: 3
title: PHP and Laravel
id: php-and-laravel
keywords:
  - PHP optimization
  - Laravel
  - OPcache
  - performance tuning
  - PHP-FPM
---

# PHP and Laravel Optimization

DreamFactory is built on PHP and the Laravel framework. Properly configuring the PHP runtime and leveraging Laravel's built-in optimization features can significantly improve API response times and overall throughput. This guide covers the key settings and techniques for getting the best performance from your DreamFactory installation.

## PHP Version Requirements

DreamFactory 7.4.x requires **PHP 8.1 or higher**. Each new PHP release includes performance improvements in the Zend engine, so running the latest stable PHP version (currently PHP 8.2 or 8.3) is recommended for optimal performance.

## OPcache Configuration

OPcache is a PHP bytecode caching extension that eliminates the need to parse and compile PHP scripts on every request. It is included with PHP by default and should always be enabled in production.

Add or verify the following settings in your `php.ini` or a dedicated OPcache configuration file:

```ini
[opcache]
opcache.enable=1
opcache.memory_consumption=256
opcache.max_accelerated_files=20000
opcache.validate_timestamps=0
opcache.interned_strings_buffer=16
opcache.fast_shutdown=1
```

:::tip
Setting `opcache.validate_timestamps=0` provides the best performance because PHP will not check whether files have changed on disk. However, you must restart PHP-FPM (or the web server) after deploying code changes to clear the OPcache.
:::

## JIT Compilation

PHP 8.1+ includes a Just-In-Time (JIT) compiler that can further improve performance for CPU-intensive operations. To enable JIT for DreamFactory workloads:

```ini
opcache.jit=1255
opcache.jit_buffer_size=128M
```

The `1255` value enables tracing JIT mode, which is the recommended setting for web applications. Benchmark your specific workload to confirm JIT provides a measurable benefit — for I/O-bound workloads (e.g., database queries), the improvement may be modest.

## Laravel Optimization Commands

Laravel provides several Artisan commands that cache configuration, routes, and views to eliminate file system reads on every request. Run these commands after every deployment:

```bash
# Cache the merged configuration files
php artisan config:cache

# Cache the route definitions
php artisan route:cache

# Compile and cache all Blade view templates
php artisan view:cache
```

These three commands can reduce first-request latency by 50-100ms by avoiding redundant file parsing.

To clear these caches (e.g., during development):

```bash
php artisan config:clear
php artisan route:clear
php artisan view:clear
```

## Environment Configuration

Several `.env` file settings directly affect performance:

```bash
# CRITICAL: Disable debug mode in production
APP_DEBUG=false

# Set the environment to production
APP_ENV=production

# Use Redis or Memcached for caching instead of file-based
CACHE_DRIVER=redis

# Use Redis for session storage in load-balanced environments
SESSION_DRIVER=redis
```

:::warning
Never run with `APP_DEBUG=true` in production. Debug mode enables detailed error traces and significantly increases response times due to extra logging and stack trace generation.
:::

## Queue Worker Configuration

DreamFactory can offload time-consuming operations (such as broadcast events and script execution) to background queue workers. Configure the queue driver in your `.env`:

```bash
QUEUE_CONNECTION=redis
```

Then start a queue worker process:

```bash
php artisan queue:work redis --sleep=3 --tries=3 --max-time=3600
```

In production, use a process supervisor like **systemd** or **Supervisor** to keep the queue worker running:

```ini
[program:dreamfactory-worker]
process_name=%(program_name)s_%(process_num)02d
command=php /opt/dreamfactory/artisan queue:work redis --sleep=3 --tries=3 --max-time=3600
autostart=true
autorestart=true
numprocs=2
user=www-data
redirect_stderr=true
stdout_logfile=/var/log/dreamfactory-worker.log
```

## Memory and Execution Time

For API endpoints that process large payloads (bulk inserts, file uploads, complex queries), you may need to adjust PHP's memory and time limits:

```ini
; In php.ini or php-fpm pool config
memory_limit=512M
max_execution_time=120
post_max_size=100M
upload_max_filesize=100M
```

Adjust these values based on your actual workload requirements. For most DreamFactory installations, 256-512MB of memory is sufficient.

## Composer Autoloader Optimization

Laravel uses Composer's autoloader to resolve class locations. Optimizing the autoloader creates a class map that speeds up class loading:

```bash
composer install --optimize-autoloader --no-dev
```

The `--no-dev` flag excludes development dependencies, reducing the number of files PHP needs to manage.
