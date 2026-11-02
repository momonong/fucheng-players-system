"""Download exactly two public, immutable tool artifacts from a trusted directory."""
import hashlib
import os
import re
import stat

from fastapi import HTTPException, Response

MAX_TOOL_BYTES = 2 * 1024 * 1024


def install_host_tool_routes(app, settings):
    @app.get('/api/deployment-tools/{digest}/{filename}')
    def download(digest: str, filename: str):
        if filename not in {'bootstrap.ps1','tools.zip'} or not re.fullmatch('[0-9a-f]{64}',digest):
            raise HTTPException(404,'找不到工具')
        try:
            fd=os.open(settings.host_tools_dir / filename,os.O_RDONLY | os.O_NONBLOCK | getattr(os,'O_NOFOLLOW',0))
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size>MAX_TOOL_BYTES:
                    raise ValueError('invalid artifact')
                content=stream.read(MAX_TOOL_BYTES+1)
            if len(content)>MAX_TOOL_BYTES or hashlib.sha256(content).hexdigest()!=digest:
                raise ValueError('artifact mismatch')
        except (OSError,ValueError):
            raise HTTPException(404,'找不到工具') from None
        return Response(content,media_type='application/zip' if filename=='tools.zip' else 'application/octet-stream',
            headers={'Content-Disposition':f'attachment; filename="{filename}"','X-Content-Type-Options':'nosniff',
                'X-Fucheng-Tool-SHA256':digest})
