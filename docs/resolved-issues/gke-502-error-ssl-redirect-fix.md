# GKE 502 Error: SSL Redirect and Health Check Fix

**Date:** November 18, 2025  
**Issue:** GKE ingress returning 502 Bad Gateway errors  
**Root Cause:** Django SSL redirect breaking load balancer health checks  
**Status:** ✅ RESOLVED  

## Problem Summary

After making changes to HSTS and SSL settings, the GKE deployment started returning 502 Bad Gateway errors. The ingress had an IP address (35.186.234.56) but all HTTP requests failed.

## Investigation Timeline

### Initial Symptoms
- GKE ingress showing IP address: `35.186.234.56`
- HTTP requests to ingress returning `502 Bad Gateway`
- Pods running healthy (2/2 READY)
- Service endpoints showing correct pod IPs

### Discovery Process

1. **Service Name Mismatch**: Initially found service name inconsistency ("django" vs "django-app") - fixed by updating k8s-deployment.yaml
2. **Ingress Cache Issues**: Deleted and recreated ingress to clear Network Endpoint Group (NEG) conflicts
3. **Pod Health Check**: Direct pod testing revealed the real issue:
   ```bash
   curl http://pod-ip:8000/
   # Result: 301 Moved Permanently -> https://pod-ip:8000/
   ```

### Root Cause Identification

Django's `SECURE_SSL_REDIRECT=True` setting was forcing all HTTP requests to redirect to HTTPS, including GKE's internal health checks. This caused:

- GKE health checks expected HTTP 200 responses
- Django returned HTTP 301 redirects instead  
- Load balancer marked all backends as UNHEALTHY
- Ingress returned 502 Bad Gateway for all requests

## Solution Implementation

### 1. Health Check Endpoint
Created `/health/` endpoint using custom middleware:
```python
# utils/middleware.py
class HealthCheckMiddleware:
    def __call__(self, request):
        if request.path == '/health/':
            return HttpResponse("OK", content_type="text/plain")
        return self.get_response(request)
```

### 2. SSL Redirect Configuration  
Disabled Django's SSL redirect since Google Load Balancer handles SSL termination:
```bash
kubectl patch secret manage2soar-env -p '{"data":{"SECURE_SSL_REDIRECT":"RmFsc2U="}}'
```

### 3. Backend Health Check Configuration
Applied BackendConfig to use custom health check path:
```yaml
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: django-app-config
spec:
  healthCheck:
    type: HTTP
    requestPath: /health/
    port: 8000
```

### 4. Service Annotation
Added backend config to service:
```yaml
metadata:
  annotations:
    cloud.google.com/backend-config: '{"default": "django-app-config"}'
```

## Architecture Pattern

**Correct SSL Termination Flow:**
```
Internet → Google Load Balancer (HTTPS) → GKE Ingress → Service (HTTP) → Pods (HTTP:8000)
```

**Key Insights:**
- Google Cloud Load Balancer handles SSL certificates and HTTPS termination
- Django should serve plain HTTP (port 8000) without SSL redirects
- Health checks must return HTTP 200, not redirects
- GKE manages SSL certificates via managed-cert resources

## Validation Steps

Post-fix verification confirmed resolution:
```bash
# HTTP access through ingress
curl -I http://35.186.234.56/
# Result: HTTP/1.1 200 OK, Via: 1.1 google

# HTTPS access through domain  
curl -I https://m2s.skylinesoaring.org/
# Result: HTTP/2 200 OK

# Health check endpoint
curl http://pod-ip:8000/health/
# Result: HTTP/1.1 200 OK, Body: "OK"
```

## Files Modified

- `utils/middleware.py` - Health check middleware
- `manage2soar/settings.py` - Added health check middleware to MIDDLEWARE list
- `backend-config.yaml` - GKE health check configuration  
- `k8s-deployment.yaml` - Service backend config annotation
- Kubernetes secret: `SECURE_SSL_REDIRECT=False`

## Lessons Learned

1. **SSL Termination Best Practice**: Let Google Load Balancer handle SSL, serve plain HTTP from Django
2. **Health Check Requirements**: GKE health checks need HTTP 200 responses, not redirects
3. **Debugging Approach**: Test pod endpoints directly to isolate application vs infrastructure issues
4. **Configuration Consistency**: Ensure service names match between deployment and ingress configs
5. **Cache Invalidation**: Sometimes ingress recreation is needed to clear stale NEG state

## Prevention

- Monitor `kubectl describe ingress` backend health status
- Set up alerts on 502 errors from load balancer
- Document SSL termination architecture clearly
- Test health check endpoints during SSL configuration changes

## Related Documentation

- [GKE Ingress Health Checks](https://cloud.google.com/kubernetes-engine/docs/concepts/ingress)
- [Django Security Settings](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-ssl-redirect)
- [Google Cloud Load Balancer SSL Termination](https://cloud.google.com/load-balancing/docs/ssl-certificates)
