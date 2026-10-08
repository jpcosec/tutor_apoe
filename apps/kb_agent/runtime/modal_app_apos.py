from __future__ import annotations

import modal

APP_NAME = 'tutor-apoe-kb-agent-apos'
ADC_PATH = '/root/.config/gcloud/application_default_credentials.json'
LOCAL_ADC = '/tmp/adc.json'

image = (
    modal.Image.debian_slim(python_version='3.11')
    .pip_install(
        'fastapi>=0.110.0',
        'uvicorn[standard]>=0.29.0',
        'python-dotenv>=1.0.0',
        'google-genai>=1.30.0',
        'pydantic>=2.8.0',
    )
    .add_local_dir('apps/kb_agent', remote_path='/root/apps/kb_agent', copy=True)
    .add_local_file(LOCAL_ADC, remote_path=ADC_PATH, copy=True)
    .env({
        'GOOGLE_APPLICATION_CREDENTIALS': ADC_PATH,
        'GOOGLE_GENAI_USE_VERTEXAI': 'true',
        'GOOGLE_CLOUD_PROJECT': 'geminitests1313',
        'GOOGLE_CLOUD_LOCATION': 'us-central1',
    })
)

app = modal.App(APP_NAME)
data_volume = modal.Volume.from_name('tutor-apoe-kb-agent-apos-data', create_if_missing=True)


@app.function(
    image=image,
    volumes={'/data': data_volume},
    min_containers=1,
)
@modal.asgi_app()
def serve():
    import os
    import sys

    os.environ.setdefault('KB_PACK', 'apos')
    os.environ.setdefault('KB_DB_PATH', '/data/kb_agent.db')

    app_dir = '/root/apps/kb_agent'
    os.chdir(app_dir)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    from runtime.main import app as fastapi_app

    return fastapi_app