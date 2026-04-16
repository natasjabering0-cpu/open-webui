import base64
import os
import random
from pathlib import Path
from typing import Annotated

import uvicorn

try:
    import typer
except ImportError:  # pragma: no cover - depends on optional CLI dependency availability
    typer = None

app = typer.Typer() if typer is not None else None

KEY_FILE = Path.cwd() / '.webui_secret_key'


def version_callback(value: bool) -> None:
    if value:
        from open_webui.env import VERSION

        if typer is None:
            print(f'Open WebUI version: {VERSION}')
            raise SystemExit(0)

        typer.echo(f'Open WebUI version: {VERSION}')
        raise typer.Exit()

def serve(
    host: str = '0.0.0.0',
    port: int = 8080,
):
    os.environ['FROM_INIT_PY'] = 'true'
    if os.getenv('WEBUI_SECRET_KEY') is None:
        if typer is None:
            print('Loading WEBUI_SECRET_KEY from file, not provided as an environment variable.')
        else:
            typer.echo('Loading WEBUI_SECRET_KEY from file, not provided as an environment variable.')
        if not KEY_FILE.exists():
            if typer is None:
                print(f'Generating a new secret key and saving it to {KEY_FILE}')
            else:
                typer.echo(f'Generating a new secret key and saving it to {KEY_FILE}')
            KEY_FILE.write_bytes(base64.b64encode(random.randbytes(12)))
        if typer is None:
            print(f'Loading WEBUI_SECRET_KEY from {KEY_FILE}')
        else:
            typer.echo(f'Loading WEBUI_SECRET_KEY from {KEY_FILE}')
        os.environ['WEBUI_SECRET_KEY'] = KEY_FILE.read_text()

    if os.getenv('USE_CUDA_DOCKER', 'false') == 'true':
        if typer is None:
            print('CUDA is enabled, appending LD_LIBRARY_PATH to include torch/cudnn & cublas libraries.')
        else:
            typer.echo('CUDA is enabled, appending LD_LIBRARY_PATH to include torch/cudnn & cublas libraries.')
        LD_LIBRARY_PATH = os.getenv('LD_LIBRARY_PATH', '').split(':')
        os.environ['LD_LIBRARY_PATH'] = ':'.join(
            LD_LIBRARY_PATH
            + [
                '/usr/local/lib/python3.11/site-packages/torch/lib',
                '/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib',
            ]
        )
        try:
            import torch

            assert torch.cuda.is_available(), 'CUDA not available'
            if typer is None:
                print('CUDA seems to be working')
            else:
                typer.echo('CUDA seems to be working')
        except Exception as e:
            message = (
                'Error when testing CUDA but USE_CUDA_DOCKER is true. '
                'Resetting USE_CUDA_DOCKER to false and removing '
                f'LD_LIBRARY_PATH modifications: {e}'
            )
            if typer is None:
                print(message)
            else:
                typer.echo(message)
            os.environ['USE_CUDA_DOCKER'] = 'false'
            os.environ['LD_LIBRARY_PATH'] = ':'.join(LD_LIBRARY_PATH)

    import open_webui.main  # noqa: F401
    from open_webui.env import UVICORN_WORKERS  # Import the workers setting

    uvicorn.run(
        'open_webui.main:app',
        host=host,
        port=port,
        forwarded_allow_ips='*',
        workers=UVICORN_WORKERS,
    )


def dev(
    host: str = '0.0.0.0',
    port: int = 8080,
    reload: bool = True,
):
    uvicorn.run(
        'open_webui.main:app',
        host=host,
        port=port,
        reload=reload,
        forwarded_allow_ips='*',
    )


if app is not None:

    @app.command()
    def main(
        version: Annotated[bool | None, typer.Option('--version', callback=version_callback)] = None,
    ):
        pass

    app.command()(serve)
    app.command()(dev)


if __name__ == '__main__':
    if app is None:
        raise SystemExit('The optional CLI dependency "typer" is required to run the open_webui CLI entrypoint.')
    app()
