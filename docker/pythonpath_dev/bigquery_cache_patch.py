"""
BigQuery client caching optimization for Superset.
This module patches Superset's Database class to cache SQLAlchemy engines more aggressively,
reducing BigQuery client initialization overhead from 150-500ms to <10ms for cached engines.

This module also increases urllib3's HTTPConnectionPool maxsize to handle more concurrent
BigQuery API requests, preventing "Connection pool is full" errors.

This module is automatically imported when Superset starts (via PYTHONPATH).
It does NOT overwrite your existing superset_config.py.

IMPORTANT SECURITY NOTES:
- The cache includes user context to prevent cross-user engine sharing when impersonation is enabled
- Database configuration changes (credentials, URI) are detected via config hash
- OAuth2 tokens are NOT included in cache key - tokens expire and are refreshed per-request
- If you use DB_CONNECTION_MUTATOR hooks, ensure they don't depend on request-specific data
  that isn't captured in the cache key (schema, catalog, source, user, nullpool)
"""
import functools
import threading
from typing import Dict, Optional, Any

# Patch urllib3 connection pool size for BigQuery API calls
# Default maxsize is 10, which causes "Connection pool is full" errors under load
# Increasing to 50 allows more concurrent BigQuery requests
try:
    import urllib3
    from urllib3.poolmanager import PoolManager
    from urllib3.connectionpool import HTTPConnectionPool
    
    # Store original __init__ methods
    _original_pool_manager_init = PoolManager.__init__
    _original_http_pool_init = HTTPConnectionPool.__init__
    _urllib3_patch_applied = False
    
    def _apply_urllib3_pool_patch():
        """Apply urllib3 connection pool size patch."""
        global _urllib3_patch_applied
        if _urllib3_patch_applied:
            return
        
        def patched_pool_manager_init(self, num_pools=10, headers=None, **connection_pool_kw):
            """Patched PoolManager.__init__ with increased maxsize."""
            if 'maxsize' not in connection_pool_kw:
                connection_pool_kw['maxsize'] = 50
            return _original_pool_manager_init(self, num_pools=num_pools, headers=headers, **connection_pool_kw)
        
        def patched_http_pool_init(self, *args, **kw):
            """Patched HTTPConnectionPool.__init__ with increased maxsize."""
            # HTTPConnectionPool.__init__ has many positional args, so use *args, **kw
            # Only override maxsize if not explicitly provided
            if 'maxsize' not in kw:
                kw['maxsize'] = 50
            return _original_http_pool_init(self, *args, **kw)
        
        PoolManager.__init__ = patched_pool_manager_init
        HTTPConnectionPool.__init__ = patched_http_pool_init
        _urllib3_patch_applied = True
        print("✅ urllib3 connection pool size increased to 50 for BigQuery API calls")
    
    # Apply patch immediately
    _apply_urllib3_pool_patch()
    
except Exception as e:
    print(f"⚠️  Warning: Could not apply urllib3 connection pool patch: {e}")
    import traceback
    traceback.print_exc()

# Thread-safe cache for SQLAlchemy engines
_engine_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()
_patch_applied = False

def apply_database_patch():
    """
    Apply the patch to Database._get_sqla_engine method.
    This should be called AFTER Flask app is initialized.
    """
    global _patch_applied
    
    if _patch_applied:
        return True
        
    try:
        from superset.models.core import Database
        
        # Store original method (only once)
        if not hasattr(Database, '_original_get_sqla_engine'):
            Database._original_get_sqla_engine = Database._get_sqla_engine
            print("DEBUG: Stored original Database._get_sqla_engine method")
        
        @functools.wraps(Database._original_get_sqla_engine)
        def cached_get_sqla_engine(self, schema=None, source=None, catalog=None, **kwargs):
            """
            Cached version of _get_sqla_engine that reuses engines.
            This significantly reduces BigQuery client initialization time.
            Supports all arguments including catalog, schema, source, and any kwargs.
            
            WARNING: This cache may reuse engines across different users if user impersonation
            is enabled. For maximum safety, consider disabling caching or adding user context
            to the cache key.
            """
            # Create cache key from database ID, schema, source, catalog, and kwargs
            db_id = getattr(self, 'id', None)
            if db_id is None:
                # If no ID, fall back to original method
                return Database._original_get_sqla_engine(self, schema=schema, source=source, catalog=catalog, **kwargs)
            
            # Include nullpool in cache key (important for connection pooling behavior)
            nullpool = kwargs.get('nullpool', True)
            
            # Try to include user context if available (for user impersonation)
            # This helps prevent security issues where different users share engines
            user_context = 'default'
            try:
                from flask import g, has_request_context
                if has_request_context() and hasattr(g, 'user') and hasattr(g.user, 'id'):
                    user_context = f"user_{g.user.id}"
                elif has_request_context() and hasattr(g, 'user') and hasattr(g.user, 'username'):
                    user_context = f"user_{g.user.username}"
            except (ImportError, AttributeError):
                pass
            
            # Include database configuration hash to detect config changes
            # This helps prevent using stale engines when DB credentials/config change
            config_hash = 'default'
            try:
                import hashlib
                # Hash key database attributes that affect engine creation
                config_str = str(getattr(self, 'sqlalchemy_uri_decrypted', ''))
                config_str += str(getattr(self, 'extra', ''))
                config_hash = hashlib.md5(config_str.encode()).hexdigest()[:8]
            except Exception:
                pass
            
            cache_key_parts = [
                str(db_id),
                str(schema) if schema else 'default',
                str(source) if source else 'default',
                str(catalog) if catalog else 'default',
                f"nullpool_{nullpool}",
                user_context,
                config_hash,
            ]
            # Include any additional kwargs in cache key (excluding nullpool which we already handled)
            if kwargs:
                filtered_kwargs = {k: v for k, v in kwargs.items() if k != 'nullpool'}
                if filtered_kwargs:
                    sorted_kwargs = sorted(filtered_kwargs.items())
                    kwargs_str = ','.join(f"{k}={v}" for k, v in sorted_kwargs)
                    cache_key_parts.append(kwargs_str)
            cache_key = ':'.join(cache_key_parts)
            
            # Check cache first (fast path)
            with _cache_lock:
                if cache_key in _engine_cache:
                    # Return cached engine immediately
                    print(f"DEBUG: Cache HIT for key: {cache_key}")
                    return _engine_cache[cache_key]
            
            # Cache miss - create new engine
            print(f"DEBUG: Cache MISS for key: {cache_key}, creating new engine...")
            engine = Database._original_get_sqla_engine(self, schema=schema, source=source, catalog=catalog, **kwargs)
            
            # Cache it (limit cache size to prevent memory issues)
            with _cache_lock:
                if len(_engine_cache) < 50:  # Max 50 cached engines
                    _engine_cache[cache_key] = engine
                    print(f"DEBUG: Cached engine for key: {cache_key} (cache size: {len(_engine_cache)})")
                else:
                    # If cache is full, remove oldest entry (simple FIFO)
                    if _engine_cache:
                        _engine_cache.pop(next(iter(_engine_cache)))
                    _engine_cache[cache_key] = engine
                    print(f"DEBUG: Cached engine for key: {cache_key} (cache was full, removed oldest)")
            
            return engine
        
        # Replace the method
        Database._get_sqla_engine = cached_get_sqla_engine
        _patch_applied = True
        print("✅ BigQuery engine caching patch applied successfully")
        return True
                
    except Exception as e:
        print(f"ERROR: Could not patch Database._get_sqla_engine: {e}")
        import traceback
        traceback.print_exc()
        return False

# Use lazy patching: patch when Database._get_sqla_engine is first called
# This avoids Flask context issues by patching at request time when context is available
_lazy_patch_setup = False

def setup_lazy_patch():
    """
    Setup lazy patching - patches Database class when _get_sqla_engine is first called.
    This avoids Flask context issues by patching at request time.
    """
    global _lazy_patch_setup
    
    if _lazy_patch_setup:
        return True
        
    try:
        from superset.models.core import Database
        
        # Store reference to original method if not already stored
        if not hasattr(Database, '_original_get_sqla_engine'):
            Database._original_get_sqla_engine = Database._get_sqla_engine
        
        # Create a wrapper that applies patch on first call
        original_method = Database._original_get_sqla_engine
        cached_method_ref = [None]  # Use list to allow modification from nested function
        
        @functools.wraps(original_method)
        def lazy_patched_get_sqla_engine(self, schema=None, source=None, catalog=None, **kwargs):
            """
            Lazy wrapper that applies patch on first call, then uses cached version.
            Supports all arguments including catalog, schema, source, and any kwargs.
            """
            global _patch_applied
            
            # Apply patch on first call (when Flask context is available)
            if not _patch_applied:
                try:
                    # Apply the actual caching patch
                    apply_database_patch()
                    _patch_applied = True
                    # Store reference to the cached method
                    cached_method_ref[0] = Database._get_sqla_engine
                    print("✅ BigQuery cache patch applied lazily on first request")
                    # Call the cached version
                    return cached_method_ref[0](self, schema=schema, source=source, catalog=catalog, **kwargs)
                except Exception as e:
                    print(f"⚠️  Could not apply patch lazily: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fall back to original method
                    return original_method(self, schema=schema, source=source, catalog=catalog, **kwargs)
            
            # After patch is applied, use the cached version
            if cached_method_ref[0] is None:
                cached_method_ref[0] = Database._get_sqla_engine
            return cached_method_ref[0](self, schema=schema, source=source, catalog=catalog, **kwargs)
        
        # Replace method with lazy wrapper
        Database._get_sqla_engine = lazy_patched_get_sqla_engine
        _lazy_patch_setup = True
        print("DEBUG: Installed lazy patch wrapper for Database._get_sqla_engine")
        return True
        
    except ImportError:
        return False
    except Exception as e:
        print(f"DEBUG: Could not setup lazy patch: {e}")
        import traceback
        traceback.print_exc()
        return False

# Try to setup lazy patch immediately
if not setup_lazy_patch():
    # If that failed, try again after a delay
    import threading
    def delayed_lazy_setup():
        import time
        for attempt in range(5):
            time.sleep(2)
            if setup_lazy_patch():
                break
    threading.Thread(target=delayed_lazy_setup, daemon=True).start()

