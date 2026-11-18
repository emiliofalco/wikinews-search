import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _es_available() -> bool:
    try:
        from search import Searcher
        s = Searcher()
        return bool(s.es.ping()) and s.es.indices.exists(index=s.index)
    except Exception:
        return False


ES_UP = _es_available()
needs_es = pytest.mark.skipif(not ES_UP, reason="Elasticsearch / index 'wikinews' not available")


@pytest.fixture(scope="session")
def searcher():
    from search import Searcher
    return Searcher()
