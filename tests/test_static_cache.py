from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from fucheng.app import create_app

@pytest.mark.parametrize('prefix',['','/fucheng'])
def test_only_hashed_build_assets_are_cacheable(app,tmp_path,prefix):
    static=tmp_path/'static';(static/'assets').mkdir(parents=True)
    (static/'index.html').write_text('<base href="/"><meta name="fucheng-base-path" content="">')
    for name in ['index-ABcd1234.js','styles-ABcd1234.css','screen-ABcd1234.png','plain.js']:
        (static/'assets'/name).write_bytes(b'synthetic')
    application=create_app(replace(app.state.settings,static_dir=static,base_path=prefix))
    try:
        with TestClient(application) as client:
            for name in ['index-ABcd1234.js','styles-ABcd1234.css','screen-ABcd1234.png']:
                response=client.get(prefix+'/assets/'+name)
                assert response.status_code==200
                assert response.headers['cache-control']=='public, max-age=31536000, immutable'
                conditional=client.get(prefix+'/assets/'+name,headers={'If-None-Match':response.headers['etag']})
                assert conditional.status_code==304
                assert conditional.headers['cache-control']==response.headers['cache-control']
            for path in ['/','/help','/api/health','/api/public/members','/assets/plain.js','/assets/missing-ABcd1234.js','/api/missing-ABcd1234.js']:
                assert client.get(prefix+path).headers['cache-control']=='no-store'
    finally:application.state.engine.dispose()
