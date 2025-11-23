# Security

Security considerations and best practices for running Apantli.

## Table of Contents

- [Security Model](#security-model)
- [API Token Authentication](#api-token-authentication)
- [Network Exposure](#network-exposure)
- [API Key Management](#api-key-management)
- [Database Security](#database-security)
- [Production Deployment](#production-deployment)
- [Security Checklist](#security-checklist)
- [Reporting Security Issues](#reporting-security-issues)

## Security Model

**By default, Apantli provides NO authentication or authorization.**

It is designed for:
- ✅ Local development on a single-user machine
- ✅ Trusted network environments
- ✅ Personal use with localhost-only binding

It is NOT designed for:
- ❌ Public internet exposure without additional security
- ❌ Multi-user environments without authentication
- ❌ Untrusted networks

**Optional API Token Authentication**: Apantli includes ultra-basic API token authentication that can be enabled via the `API_TOKEN_REQUIRED` environment variable. This provides a simple barrier against casual access but should not be considered sufficient for production environments handling sensitive data. See [API Token Authentication](#api-token-authentication) for details.

## API Token Authentication

### Enabling API Token Authentication

API token authentication is optional and disabled by default. Enable it by setting the `API_TOKEN_REQUIRED` environment variable:

```bash
# Add to .env
API_TOKEN_REQUIRED=your-secret-token-here
```

Once enabled, all API requests must include a valid Bearer token in the Authorization header.

### Using Authenticated Requests

When API token authentication is enabled, include the Bearer token in request headers:

**Using curl**:

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer your-secret-token-here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4.1-mini",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

**Using Python OpenAI SDK**:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4000/v1",
    api_key="",  # Not used for Apantli, but required by SDK
    default_headers={
        "Authorization": "Bearer your-secret-token-here"
    }
)

response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

**Using curl with environment variable**:

```bash
# Set token as environment variable
export APANTLI_TOKEN="your-secret-token-here"

# Use in requests
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $APANTLI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "Hello!"}]}'
```

### Protected Endpoints

When `API_TOKEN_REQUIRED` is set, the following endpoints require Bearer token authentication:

- `/v1/chat/completions` (POST)
- `/chat/completions` (POST)
- `/models` (GET)

The following endpoints remain unprotected:
- `/health` (GET)
- `/` (Dashboard)
- `/compare` (Playground)

### Important Limitations

API token authentication in Apantli is **ultra-basic** security for convenience:

- ✅ Provides a simple barrier against casual access
- ✅ Works for protecting localhost sharing across trusted networks
- ✅ Easy to enable and use

- ❌ Tokens are sent in plain HTTP headers (use HTTPS if on public networks)
- ❌ No rate limiting built in
- ❌ No user isolation or per-user tracking
- ❌ Single shared token (not per-user)
- ❌ Not suitable for multi-user or production environments

**For production environments**, combine API token authentication with:
- HTTPS/TLS encryption
- Reverse proxy with rate limiting
- Network firewall rules
- VPN or SSH tunneling
- Comprehensive monitoring and logging

See [Production Deployment](#production-deployment) for recommendations.

## Network Exposure

### Default Binding

By default, Apantli binds to `0.0.0.0:4000` (all network interfaces):

```bash
apantli  # Binds to 0.0.0.0:4000
```

**This means anyone on your network can:**
- Send requests to any configured LLM model using your API keys
- Access the web dashboard and view all conversation history
- Read all stored requests and responses
- Query cost and usage statistics

### Localhost-Only Binding (Recommended)

For single-user local development, bind to localhost only:

```bash
apantli --host 127.0.0.1
```

This ensures only processes on your machine can access the server.

### Firewall Protection

If you must bind to `0.0.0.0` (for example, to access from other devices on your local network):

1. **Enable API token authentication** (see [API Token Authentication](#api-token-authentication)):

   ```bash
   # Set API_TOKEN_REQUIRED in .env
   API_TOKEN_REQUIRED=your-secret-token-here
   apantli
   ```

2. **Use a firewall** to restrict access:

   ```bash
   # macOS
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /path/to/python
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --block /path/to/python

   # Linux (ufw)
   sudo ufw deny 4000
   sudo ufw allow from 192.168.1.0/24 to any port 4000  # Allow local network only
   ```

3. **Use SSH tunneling** to access remotely:

   ```bash
   # On remote machine
   ssh -L 4000:localhost:4000 user@your-machine

   # Then access http://localhost:4000 in browser
   ```

4. **Use a reverse proxy** with authentication (see [Production Deployment](#production-deployment))

## API Key Management

### Environment Variables

**DO**:
- ✅ Store API keys in `.env` file (gitignored)
- ✅ Use `os.environ/VAR_NAME` format in `config.yaml`
- ✅ Use separate API keys for development and production
- ✅ Rotate API keys periodically
- ✅ Use provider-specific key scopes (e.g., read-only keys where possible)

**DON'T**:
- ❌ Hardcode API keys in `config.yaml`
- ❌ Commit `.env` to version control
- ❌ Share API keys between environments
- ❌ Use root/admin keys if provider offers scoped keys
- ❌ Log API keys to stdout/stderr

### File Permissions

Protect your `.env` file:

```bash
chmod 600 .env  # Owner read/write only
```

Check permissions:

```bash
ls -la .env
# Should show: -rw------- (600)
```

### API Keys in Database

**Important**: Apantli stores full request JSON (including API keys) in `requests.db` for debugging purposes.

**Implications**:
- The database contains sensitive data
- Anyone with read access can see your API keys
- Backup files must be protected
- Database exports must be treated as sensitive

**Mitigation**:

1. **Protect database file**:

   ```bash
   chmod 600 requests.db
   ```

2. **Use separate API keys** for Apantli (not your main production keys)

3. **Implement data retention** to delete old requests:

   ```bash
   # Delete requests older than 30 days
   sqlite3 requests.db "DELETE FROM requests WHERE timestamp < datetime('now', '-30 days')"
   sqlite3 requests.db "VACUUM"
   ```

4. **Consider API key redaction** (future enhancement):
   - Modify `database.py` to redact keys before storage
   - Or set `request_data = None` to skip JSON storage

## Database Security

### Location and Access

The SQLite database (`requests.db`) contains:
- Full conversation history (all messages)
- API keys (in request JSON)
- Metadata (timestamps, costs, models)
- Error messages and stack traces

**Default location**: Project root directory

**Best practices**:

1. **Restrict file permissions**:

   ```bash
   chmod 600 requests.db
   ```

2. **Use custom location** for sensitive environments:

   ```bash
   # Store in secure directory
   mkdir -p ~/.apantli
   chmod 700 ~/.apantli
   apantli --db ~/.apantli/requests.db
   ```

3. **Encrypt storage volume** (OS-level):
   - macOS: Use FileVault
   - Linux: Use LUKS/dm-crypt
   - Windows: Use BitLocker

### Backup Security

Database backups contain sensitive data:

```bash
# Secure backup
cp requests.db ~/.apantli/requests.db.backup
chmod 600 ~/.apantli/requests.db.backup

# Or encrypt backup
tar czf - requests.db | gpg -c > requests.db.backup.tar.gz.gpg
```

**Never**:
- Store backups in cloud storage without encryption
- Email database files
- Share database files via insecure channels

## Production Deployment

For production or network-exposed deployments, implement additional security layers.

### Reverse Proxy with Authentication

Use nginx or similar to add authentication:

```nginx
# /etc/nginx/sites-available/apantli
server {
    listen 443 ssl;
    server_name apantli.yourdomain.com;

    # SSL configuration
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Basic authentication
    auth_basic "Apantli Access";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:4000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Create password file:

```bash
sudo htpasswd -c /etc/nginx/.htpasswd username
```

### API Key Authentication

For programmatic access, consider implementing API key auth in a fork or wrapper:

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.environ.get("APANTLI_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

# Add to routes
@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request):
    # ...
```

### HTTPS/TLS

Always use HTTPS for network-exposed deployments:

1. **Use a reverse proxy** (nginx, caddy) with TLS termination
2. **Get certificates** from Let's Encrypt or your certificate authority
3. **Enforce HTTPS** (redirect HTTP to HTTPS)

### Docker Deployment

If deploying with Docker:

```dockerfile
# Dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY apantli/ ./apantli/
COPY templates/ ./templates/
COPY config.yaml .

# Non-root user
RUN useradd -m -u 1000 apantli && \
    chown -R apantli:apantli /app

USER apantli

CMD ["python", "-m", "apantli.server", "--host", "0.0.0.0", "--port", "4000"]
```

**Security considerations**:
- Run as non-root user
- Use `.env` file or secrets management
- Mount database volume with proper permissions
- Limit container capabilities

## Security Checklist

### Development

- [ ] `.env` file has mode 600 permissions
- [ ] `.env` is in `.gitignore`
- [ ] Server binds to `127.0.0.1` (localhost only) or API token enabled
- [ ] Database file has mode 600 permissions
- [ ] Using separate API keys (not production keys)

### Production

- [ ] API token authentication enabled OR reverse proxy authentication configured
- [ ] HTTPS/TLS enabled
- [ ] Firewall configured to restrict access
- [ ] Database encrypted at rest (volume encryption)
- [ ] Database location outside web root
- [ ] Regular backups configured (encrypted)
- [ ] Data retention policy implemented
- [ ] Monitoring and alerting configured
- [ ] Security updates applied regularly

### Data Privacy

- [ ] Data retention policy documented
- [ ] Old requests deleted automatically
- [ ] Database backups encrypted
- [ ] API keys rotated periodically
- [ ] Access logs reviewed regularly

## Known Security Limitations

### No Built-in Rate Limiting

Apantli does not implement rate limiting. Anyone with access can make unlimited requests.

**Mitigation**: See [Production Deployment](#production-deployment) for options.

### API Keys Stored in Database

Full request JSON (including API keys) is stored in the database for debugging.

**Mitigation**:
- Use separate API keys for Apantli
- Protect database file with 600 permissions
- Implement data retention to delete old requests
- Consider forking and modifying to redact keys

### SQLite Limitations

SQLite uses file-level locking and provides no network access control.

**Mitigation**:
- Protect file with permissions (600)
- Use encrypted filesystem
- Consider Postgres for multi-user deployments

### XSS in Dashboard

The dashboard displays user-supplied content (request/response JSON). While `escapeHtml()` is used, complex JSON may contain edge cases.

**Mitigation**:
- Dashboard is meant for trusted users only
- Always bind to localhost for personal use
- Use authentication if exposing to network
- Enable API token authentication for network sharing

### API Token - Basic Security Only

The API token authentication is ultra-basic and suitable only for protecting against casual access on trusted networks.

**Limitations**:
- Tokens sent in plain HTTP headers (use HTTPS on public networks)
- Single shared token (no per-user isolation)
- No automatic token rotation
- No token expiration or revocation mechanism

**Mitigation**:
- Use only on trusted networks or with HTTPS
- Combine with reverse proxy for production use
- Rotate tokens regularly
- Use strong, random tokens (32+ characters)
- Implement proper access control in production

## Reporting Security Issues

If you discover a security vulnerability in Apantli:

1. **DO NOT** open a public GitHub issue
2. **DO** report via email to the project maintainer
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and work with you to address the issue.

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

---

**Remember**: Apantli is designed for local, single-user use. API token authentication provides ultra-basic security suitable for trusted networks only. If you need multi-user support, public network exposure, or production deployment, implement proper authentication, authorization, encryption, and rate limiting before deployment.
