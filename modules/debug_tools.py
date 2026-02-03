# modules/debug_tools.py (yeni dosya)
import time, json, logging
from contextlib import contextmanager

LOG = logging.getLogger("ChatbotAPI")

def jd(obj):
    try:    return json.dumps(obj, ensure_ascii=False, default=str)
    except: return str(obj)

def dbg(tag, **kw):
    LOG.info("[DBG] %s %s", tag, jd(kw))

@contextmanager
def span(name, **meta):
    t0 = time.time()
    LOG.info("[SPAN] start %s %s", name, jd(meta))
    try:
        yield
    finally:
        LOG.info("[SPAN] end   %s %s", name, jd({**meta, "ms": int((time.time()-t0)*1000)}))
