# CSRF 403 Errors on Safari iOS - Issue Resolution

## Issue Summary
Customer reported 403 CSRF errors when attempting to log in from iPad using Safari 18.7.3.

## Root Cause
Safari's Intelligent Tracking Prevention (ITP) can be overly aggressive with cookie handling, especially when:
- SameSite cookie attributes are not explicitly defined
- Forms POST to the same domain (can appear as "cross-site" to Safari)
- User leaves page open before submitting

While Django defaults to `SameSite='Lax'` since version 3.1, Safari on iOS has known edge cases and bugs with cookie handling that benefit from explicit configuration.

## Log Evidence
```json
{
  "httpRequest": {
    "requestMethod": "POST",
    "requestUrl": "https://www.skylinesoaring.org/login/",
    "status": 403,
    "userAgent": "Mozilla/5.0 (iPad; CPU OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7.3 Mobile/15E148 Safari/604.1",
    "remoteIp": "205.220.129.47"
  },
  "timestamp": "2026-02-03T19:37:28.622413Z"
}
```

## Solution (IaC-First)

### 1. Django Settings (`manage2soar/settings.py`)
Added explicit SameSite cookie configuration with environment variable support:

```python
# Production mode
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# Development mode
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
```

### 2. Kubernetes Secrets Template (`infrastructure/ansible/roles/gke-deploy/templates/k8s-secrets.yml.j2`)
Added environment variables to deployment configuration:

```jinja
# COOKIE SECURITY SETTINGS
SESSION_COOKIE_SAMESITE: "{{ gke_session_cookie_samesite | default('Lax') }}"
CSRF_COOKIE_SAMESITE: "{{ gke_csrf_cookie_samesite | default('Lax') }}"
```

### 3. Configuration Options
Operators can now override in Ansible inventory if needed:

```yaml
gke_session_cookie_samesite: "Lax"  # or "Strict" or "None"
gke_csrf_cookie_samesite: "Lax"     # or "Strict" or "None"
```

## SameSite Values Explained

- **Lax** (Recommended): Cookies sent with same-site requests and top-level navigation (links, form GETs)
  - Best balance of security and usability
  - Works with most legitimate use cases
  - Default for this deployment

- **Strict**: Cookies only sent with same-site requests
  - More secure but can break legitimate functionality
  - User must be on same domain for cookies to be sent
  - May cause issues with redirects from external sites

- **None**: Cookies sent with all requests (cross-site included)
  - Requires `Secure` flag (HTTPS only)
  - Only needed for cross-domain scenarios (embedded iframes, etc.)
  - Least secure option

## Deployment
Changes take effect on next deployment:
```bash
cd infrastructure/ansible
ansible-playbook playbooks/gke-deploy.yml -e "gke_club_prefix=ssc"
```

## Testing Recommendations
1. Test login flow on Safari iOS (iPad and iPhone)
2. Test form submissions after leaving page open for extended period
3. Verify cookies are set correctly in browser dev tools
4. Test with Safari privacy settings at various levels

## Additional Resources
- Django CSRF Documentation: https://docs.djangoproject.com/en/5.2/ref/csrf/
- Safari ITP Details: https://webkit.org/blog/category/privacy/
- SameSite Cookie Spec: https://datatracker.ietf.org/doc/html/draft-ietf-httpbis-rfc6265bis

## Date Resolved
February 3, 2026
