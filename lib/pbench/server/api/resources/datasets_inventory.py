from http import HTTPStatus
from urllib.request import Request

from flask import current_app, send_file
from flask.wrappers import Response

from pbench.server import OperationCode, PbenchServerConfig
from pbench.server.api.resources import (
    APIAbort,
    ApiAuthorizationType,
    ApiBase,
    ApiContext,
    ApiMethod,
    ApiParams,
    ApiSchema,
    Parameter,
    ParamType,
    Schema,
)
from pbench.server.cache_manager import CacheManager, CacheType, TarballNotFound


class DatasetsInventory(ApiBase):
    """
    API class to retrieve inventory files from a dataset
    """

    def __init__(self, config: PbenchServerConfig):
        super().__init__(
            config,
            ApiSchema(
                ApiMethod.GET,
                OperationCode.READ,
                uri_schema=Schema(
                    Parameter("dataset", ParamType.DATASET, required=True),
                    Parameter("target", ParamType.STRING, required=False),
                ),
                authorization=ApiAuthorizationType.DATASET,
            ),
        )

    def _get(
        self, params: ApiParams, request: Request, context: ApiContext
    ) -> Response:
        """
        This function returns the contents of the requested file as a byte stream.

        Args:
            params: includes the uri parameters, which provide the dataset and target.
            request: Original incoming Request object
            context: API context dictionary

        Raises:
            APIAbort, reporting either "NOT_FOUND" or "UNSUPPORTED_MEDIA_TYPE"


        GET /api/v1/datasets/{dataset}/inventory/{target}
        """
        dataset = params.uri["dataset"]
        target = params.uri.get("target")

        cache_m = CacheManager(self.config, current_app.logger)
        try:
            file_info = cache_m.filestream(dataset, target)
        except TarballNotFound as e:
            raise APIAbort(HTTPStatus.NOT_FOUND, str(e))

        if file_info["type"] == CacheType.FILE:
            # Tell send_file to set `Content-Disposition` to "attachment" if
            # targeting the large binary tarball. Otherwise we'll recommend the
            # default "inline": only `is_file()` paths are allowed here, and
            # most are likely "displayable". While `send_file` will guess the
            # download_name from the path, setting it explicitly does no harm
            # and supports a unit test mock with no real file.
            #
            # NOTE: we could choose to be "smarter" based on file size, file
            # type codes (e.g., .csv, .json), and so forth.
            resp = send_file(
                file_info["stream"],
                as_attachment=target is None,
                download_name=file_info["name"],
            )
            file_info["stream"].close()
            return resp
        else:
            raise APIAbort(
                HTTPStatus.BAD_REQUEST,
                "The specified path does not refer to a regular file",
            )
