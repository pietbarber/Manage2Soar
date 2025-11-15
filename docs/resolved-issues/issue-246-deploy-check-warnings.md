# Issue #246 Resolution: Deploy Check Warnings Fixed

## Problem
Running `python manage.py check --deploy` showed multiple security warnings that needed to be resolved for production deployment.

## Original Warnings
```
WARNINGS:
?: (security.W004) SECURE_HSTS_SECONDS not set
?: (security.W008) SECURE_SSL_REDIRECT not set to True  
?: (security.W012) SESSION_COOKIE_SECURE not set to True
?: (security.W016) CSRF_COOKIE_SECURE not set to True
?: (security.W018) DEBUG set to True in deployment
?: (urls.W005) URL namespace 'cms' isn't unique
```

## Resolution

### ✅ URL Namespace Warning (W005)
**ALREADY FIXED** - The CMS URL namespace collision was resolved as part of the homepage/CMS URL restructuring work in PR #267.

### ✅ Security Warnings (W004, W008, W012, W016, W018)
Added configurable security settings to `manage2soar/settings.py` that can be controlled via environment variables:

```python
# HTTP Strict Transport Security (HSTS)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))

# Force HTTPS redirect
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False").lower() in ("true", "1", "yes")

# Secure cookies - only sent over HTTPS
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "yes")
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "False").lower() in ("true", "1", "yes")
```

## Production Configuration

### Required Environment Variables
Set these in your production `.env` file:

```bash
# Disable debug mode
DJANGO_DEBUG=False

# Enable HTTPS security
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True  
CSRF_COOKIE_SECURE=True

# Enable HSTS (start with small value, increase after testing)
SECURE_HSTS_SECONDS=31536000  # 1 year for production
```

### Testing the Fix
```bash
# Development (warnings expected)
python manage.py check --deploy

# Production simulation (no warnings)
DJANGO_DEBUG=False SECURE_SSL_REDIRECT=True SESSION_COOKIE_SECURE=True CSRF_COOKIE_SECURE=True SECURE_HSTS_SECONDS=3600 python manage.py check --deploy
```

## Development vs Production Behavior

### Development Environment
- Default values are insecure for ease of development
- Warnings will still appear (this is intentional)
- HTTP works fine for local development

### Production Environment  
- Security settings enforced via environment variables
- All warnings resolved when properly configured
- HTTPS required for secure operation

## Security Considerations

### ⚠️ HSTS Warning
- `SECURE_HSTS_SECONDS` cannot be easily reversed once set
- Start with a small value (3600 = 1 hour) for testing
- Only increase to production values (31536000 = 1 year) after confirming HTTPS works correctly

### 🔒 HTTPS Requirements
- All secure cookie settings require HTTPS to function properly
- Ensure your reverse proxy/load balancer properly handles SSL termination
- Test thoroughly before enabling in production

## Files Modified
- `manage2soar/settings.py` - Added configurable security settings
- `.env.production.sample` - Production environment template

## Verification
- ✅ Development: Warnings present (expected behavior)
- ✅ Production: No warnings when environment variables set correctly
- ✅ Settings are configurable and environment-aware
- ✅ Backward compatible with existing deployments

## Related Issues
- Resolves Issue #246 completely
- Built upon CMS URL fixes from PR #267
