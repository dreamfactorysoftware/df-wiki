---
sidebar_position: 5
title: Rate Limiting
id: rate-limiting
keywords:
  - rate limiting
  - API limits
  - throttling
  - HTTP 429
  - API security
---

# Rate Limiting

DreamFactory provides a comprehensive rate limiting system that allows administrators to control API usage at multiple levels. Rate limits can be applied per instance, per user, per role, per service, or per endpoint, giving you fine-grained control over how your APIs are consumed. This is essential for preventing abuse, ensuring fair resource allocation, and maintaining platform stability.

## Why Rate Limiting Matters

Without rate limiting, a single client or user can monopolize server resources by making an excessive number of API requests. This can degrade performance for all users, increase infrastructure costs, and potentially lead to service outages. DreamFactory's rate limiting feature helps you:

- Protect backend services from being overwhelmed by too many requests
- Enforce usage tiers and quotas for different user groups
- Prevent API abuse and denial-of-service scenarios
- Monitor and plan capacity based on actual usage patterns

## Limit Types and Hierarchy

DreamFactory supports a hierarchy of limit types. When multiple limits are combined, broader limits can override more granular ones. For example, if an instance-wide limit is set to 500 requests per minute, a service-specific limit of 1,000 requests per minute would never be reached because the instance limit triggers first.

| Limit Type | Description |
|---|---|
| Instance | Rate limits across the entire DreamFactory instance, cumulative for all users and services |
| User | Limits applied to a specific user across all services |
| Each User | Every user receives an independent counter with the same rate limit |
| Role | Rate limits applied based on a user's assigned role |
| Service | Limits targeting a specific API service |
| Service by User | Limits for a specific user on a specific service |
| Service by Each User | Independent per-user counters on a specific service |
| Endpoint | Limits targeting a specific API endpoint |
| Endpoint by User | Limits for a specific user on a specific endpoint |
| Endpoint by Each User | Independent per-user counters on a specific endpoint |

### Limit Periods

Each limit is configured with a reset period that determines when the counter resets automatically. Available periods include:

- **Minute** — resets every 60 seconds
- **Hour** — resets every 60 minutes
- **Day** — resets every 24 hours
- **7-day** — resets weekly
- **30-day** — resets monthly

## Configuring Rate Limits

### Via the Admin Console

To create a rate limit in the DreamFactory Admin Console:

1. Navigate to **Config > Limits** in the left sidebar
2. Click **Create** to add a new limit
3. Select the **Limit Type** from the dropdown (Instance, User, Service, etc.)
4. Set the **Rate** (maximum number of requests allowed)
5. Choose the **Period** (minute, hour, day, 7-day, or 30-day)
6. Optionally restrict to a specific **HTTP Verb** (GET, POST, PUT, PATCH, DELETE)
7. Provide a descriptive **Name** for the limit
8. Click **Save**

### Via the API

Limits can also be managed programmatically through the DreamFactory REST API:

```bash
# Create an instance-wide limit of 1000 requests per hour
curl -X POST "https://your-instance.com/api/v2/system/limit" \
  -H "X-DreamFactory-API-Key: YOUR_API_KEY" \
  -H "X-DreamFactory-Session-Token: YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resource": [{
      "type": "instance",
      "name": "Global Hourly Limit",
      "rate": 1000,
      "period": "hour",
      "is_active": true
    }]
  }'
```

Key API endpoints for limit management:

- `GET /api/v2/system/limit` — List all configured limits
- `POST /api/v2/system/limit` — Create a new limit
- `PUT /api/v2/system/limit/{id}` — Update an existing limit
- `DELETE /api/v2/system/limit/{id}` — Remove a limit
- `GET /api/v2/system/limit_cache` — View current counter values
- `DELETE /api/v2/system/limit_cache/{id}` — Reset a specific limit counter

## What Happens When Limits Are Exceeded

When a client exceeds a configured rate limit, DreamFactory responds with an **HTTP 429 Too Many Requests** status code. The response includes information about the limit that was reached. Clients should implement backoff logic and retry after the limit period resets.

## Monitoring Usage

The **Limits** section of the Admin Console displays current usage statistics for all active limits, including the current hit count and remaining requests in the current period. You can also programmatically query limit usage via the `system/limit_cache` endpoint.

## Endpoint Limits and Wildcards

Endpoint limits allow granular control over specific API paths. For example, you can limit requests to `_table/contacts` on a database service without affecting other tables. Adding a wildcard `*` character creates a limit that matches the endpoint and all sub-paths (e.g., `_table/contacts*` would also match `_table/contacts/5`).

## Limit Cache and Storage

By default, DreamFactory uses a file-based cache for rate limit counters, separate from the main application cache. This ensures that clearing the DreamFactory cache does not reset rate limit counters. For high-traffic environments, Redis can be configured as the limit cache backend. See the `.env-dist` file for limit cache configuration options.
