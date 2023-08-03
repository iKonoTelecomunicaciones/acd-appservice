from __future__ import annotations

import asyncio
import logging

import aiohttp_cors
from aiohttp import web
from aiohttp_swagger3 import SwaggerDocs, SwaggerInfo, SwaggerUiSettings
from mautrix.util.logging import TraceLogger

from ..commands.resolve import BulkResolve
from ..config import Config
from ..version import version
from . import api
from .base import routes, set_config


class ProvisioningAPI:
    """Provisioning API base class"""

    log: TraceLogger = logging.getLogger("acd.provisioning")
    app: web.Application

    def __init__(
        self, config: Config, loop: asyncio.AbstractEventLoop, bulk_resolve: BulkResolve
    ) -> None:
        self.app = web.Application()
        self.loop = loop
        set_config(config=config, bulk_resolve=bulk_resolve)

        swagger = SwaggerDocs(
            self.app,
            info=SwaggerInfo(
                title="ACD AppService API",
                description=(
                    "Documentation for the ACD application service of [iKonoChat](https://ikono.co/ikono-chat) "
                    "project by **iKono Telecomunicaciones S.A.S.**"
                ),
                version=f"v{version}",
            ),
            components="components.yaml",
            swagger_ui_settings=SwaggerUiSettings(
                path="/docs",
                layout="BaseLayout",
            ),
        )

        swagger.add_routes(routes)

        cors = aiohttp_cors.setup(
            self.app,
            defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                )
            },
        )

        for route in list(self.app.router.routes()):
            cors.add(route)
            if route.method in ["post", "POST"]:
                swagger.add_options(path=route.get_info()["path"], handler=self.options)

    @property
    def _acao_headers(self) -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }

    @property
    def _headers(self) -> dict[str, str]:
        return {
            **self._acao_headers,
            "Content-Type": "application/json",
        }

    async def options(self, _: web.Request):
        return web.Response(status=200, headers=self._headers)
