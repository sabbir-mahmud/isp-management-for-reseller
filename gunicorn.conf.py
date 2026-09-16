"""Gunicorn configuration.

Read from the environment so the same image runs on a 1-core VPS and a
larger box without a rebuild.
"""

import multiprocessing
import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Two per core plus one is the usual starting point for a sync worker pool
# that spends most of its time waiting on the database.
workers = int(os.getenv("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.getenv("GUNICORN_THREADS", 2))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")

timeout = int(os.getenv("GUNICORN_TIMEOUT", 60))
graceful_timeout = 30
# Slightly above a typical load balancer's 60s idle timeout, so the balancer
# closes connections rather than gunicorn cutting them mid-response.
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 65))

# Recycle workers to bound the damage from any slow leak.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 1000))
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms "%(f)s" "%(a)s"'


# The health check would otherwise dominate the access log.
def pre_request(worker, req):  # noqa: D103
    if req.path == "/healthz":
        req.__dict__["_skip_log"] = True
