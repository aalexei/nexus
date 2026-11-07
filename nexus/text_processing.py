"""Bounded, in-memory reuse of text parsing; stored HTML stays authoritative."""
from functools import lru_cache
from bs4 import BeautifulSoup

# Never retain very large node documents in an application-wide cache.
MAX_CACHED_SOURCE = 4096
CACHE_SIZE = 1024


def _source_summary(source):
    if '<' not in source and '&' not in source:
        # With no markup or entity introducers, BeautifulSoup returns this
        # exact text. Keep the same whitespace/first-line rules as before.
        text = source
        has_text = bool(source.strip())
    else:
        soup = BeautifulSoup(source, 'html.parser')
        # Preserve the old thumbnail decision, before stripping head/style.
        has_text = bool(soup.get_text(strip=True))
        for element in soup(['head', 'style', 'script']):
            element.decompose()
        for element in soup.find_all('br'):
            element.replace_with('\n')
        for element in soup.find_all(['p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            element.insert_after('\n')
        text = soup.get_text()
    for line in text.splitlines():
        title = ' '.join(line.split())
        if title:
            return title, has_text
    return '', has_text


_cached_summary = lru_cache(maxsize=CACHE_SIZE)(_source_summary)


def source_summary(source):
    """Return the first outline line and the existing has-text thumbnail flag."""
    return (_cached_summary(source) if len(source) <= MAX_CACHED_SOURCE
            else _source_summary(source))


def _normalize_html(source):
    # Identical to TextItem.getSrc's existing Qt HTML cleanup. Do not replace
    # it with raw stored HTML: that would change font/style inheritance.
    soup = BeautifulSoup(source, 'html.parser')
    body = soup.find('body')
    if body is None:
        body = soup
    for paragraph in body.find_all('p'):
        del paragraph['style']
    result = body.encode_contents().decode('utf-8').strip()
    return '' if result == '<p><br/></p>' else result


_cached_normalized = lru_cache(maxsize=CACHE_SIZE)(_normalize_html)


def normalize_html(source):
    """Reuse immutable cleanup results keyed by the complete current HTML."""
    return (_cached_normalized(source) if len(source) <= MAX_CACHED_SOURCE
            else _normalize_html(source))


def clear_caches():
    _cached_summary.cache_clear()
    _cached_normalized.cache_clear()
