"""Cache only immutable, bundled assets; never relax application-data privacy."""
import re

IMMUTABLE_ASSET_CACHE = 'public, max-age=31536000, immutable'
_ASSET = re.compile(r'^/assets/[A-Za-z0-9._-]+-[A-Za-z0-9_-]{8,}\.(js|css|png)$')
_TYPES = {'js': {'text/javascript','application/javascript'}, 'css': {'text/css'}, 'png': {'image/png'}}


def cache_policy(path: str, method: str, status: int, headers) -> str:
    match = _ASSET.fullmatch(path)
    media_type = headers.get('content-type','').split(';',1)[0].strip().lower()
    if (match and method in {'GET','HEAD'} and status in {200,304}
            and 'set-cookie' not in headers and headers.get('vary','').strip() != '*'
            and (status == 304 or media_type in _TYPES[match[1]])):
        return IMMUTABLE_ASSET_CACHE
    return 'no-store'
