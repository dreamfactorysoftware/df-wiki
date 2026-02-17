---
sidebar_position: 5
title: API Creation and Management
keywords:
  - API creation
  - service management
  - DreamFactory services
  - API types
  - admin console
---

# API Creation and Management

DreamFactory uses a service-oriented architecture where every API connection is represented as a **service**. A service encapsulates the configuration, authentication, and endpoint definitions needed to interact with an external data source or system. Once created, each service is automatically assigned a namespace (e.g., `/api/v2/mysql`, `/api/v2/s3files`) through which all of its endpoints are accessible via DreamFactory's unified REST interface.

## Overview of DreamFactory's Architecture

At its core, DreamFactory acts as a middleware layer between your application clients and your backend data sources. When you create a service, DreamFactory:

1. Establishes a managed connection to the target system
2. Auto-generates a full set of REST endpoints (for supported service types)
3. Applies role-based access controls, rate limiting, and logging
4. Produces live, interactive API documentation via the API Docs tab

This means you can expose a MySQL database, an S3 file store, and a Salesforce instance through a single, consistently secured API gateway without writing any integration code.

## Creating a New API Service

To create a new service via the Admin Console:

1. Navigate to **Services** in the left sidebar
2. Click the **Create** button (top-right)
3. In the **Service Type** dropdown, select the type of service you want to create (e.g., Database > MySQL, File > AWS S3, Remote Service > HTTP)
4. Fill in the **Info** tab:
   - **Name**: A short, URL-safe identifier used in API paths (e.g., `mysql-prod`)
   - **Label**: A human-readable display name (e.g., "Production MySQL Database")
   - **Description**: Optional notes about the service purpose
5. Switch to the **Config** tab and provide connection-specific settings (host, port, credentials, etc.)
6. Click **Save** to create the service

Once saved, the service endpoints are immediately available at `/api/v2/{service-name}/`.

```bash
# Example: query a table through a newly created MySQL service
curl -X GET "https://your-instance.com/api/v2/mysql-prod/_table/customers?limit=10" \
  -H "X-DreamFactory-API-Key: YOUR_API_KEY" \
  -H "X-DreamFactory-Session-Token: YOUR_SESSION_TOKEN"
```

## Service Types

DreamFactory supports a wide range of service types, organized into the following categories:

### Database Services
Connect to relational and NoSQL databases. DreamFactory auto-generates CRUD endpoints for every table, view, and stored procedure. Supported databases include MySQL, PostgreSQL, Microsoft SQL Server, Oracle, MongoDB, Cassandra, and many more.

### Remote API Services
Proxy and manage access to third-party HTTP and SOAP APIs. DreamFactory handles authentication headers, URL rewriting, and can apply role-based access to specific remote endpoints.

- **HTTP Service** — Connect to any RESTful API
- **SOAP Service** — Connect to WSDL-defined SOAP services

### File Storage Services
Manage files stored in local or cloud storage through a unified file API:

- Local file storage
- AWS S3
- Azure Blob Storage
- Google Cloud Storage
- SFTP

### Scripted Services
Create custom API endpoints backed by server-side scripts. Supported scripting languages include PHP, Python, and Node.js. Scripted services are ideal for custom business logic, data transformation, and workflow orchestration.

### Email Services
Send email through SMTP, Mailgun, SparkPost, or Amazon SES via a simple REST API call.

### Source Control Services
Interact with GitHub, GitLab, and Bitbucket repositories through DreamFactory's unified API.

## Service Namespacing and Versioning

Every service receives a unique namespace based on its **Name** field. All endpoints for the service are scoped under `/api/v2/{service-name}/`. This namespace isolation ensures there are no endpoint collisions between services, even when multiple services connect to the same type of backend.

DreamFactory's API versioning is handled at the platform level (`/api/v2/`), so all services inherit the current API version automatically.

## Managing Existing Services

From the **Services** list in the Admin Console, you can:

- **Edit** a service's configuration, credentials, or metadata
- **Deactivate** a service without deleting it (toggle the Active flag)
- **Delete** a service permanently (removes all associated role assignments and cached data)

Service configuration changes take effect immediately — no restart is required.

## Related Pages

For detailed guides on specific service types, see:

- [Database Connections](/docs/api-generation-and-connections/database) — Connecting to SQL and NoSQL databases
- [Remote HTTP and SOAP Connectors](/docs/api-generation-and-connections/remote-http-soap) — Proxying external APIs
- [File Storage Services](/docs/api-generation-and-connections/file-storage) — Managing cloud and local file systems
- [Scripted APIs](/docs/Scripting/scripted-apis) — Building custom endpoints with server-side scripts
- [Email Services](/docs/api-generation-and-connections/email) — Sending email via REST
