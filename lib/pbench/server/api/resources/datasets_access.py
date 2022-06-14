from http import HTTPStatus
from logging import Logger
from pathlib import Path

from flask.wrappers import Request, Response
from flask import send_file

import os
from pbench.server import JSON, JSONOBJECT, PbenchServerConfig
from pbench.server.api.resources import (
    APIAbort,
    API_AUTHORIZATION,
    API_METHOD,
    API_OPERATION,
    ApiBase,
    ApiParams,
    ApiSchema,
    ParamType,
    Parameter,
    Schema,
)

from pbench.server.filetree import FileTree, DatasetNotFound

from pbench.server.database.models.datasets import Dataset, Metadata, MetadataError


class DatasetsAccess(ApiBase):
    """
    API class to retrieve and mutate Dataset metadata.
    """

    def __init__(self, config: PbenchServerConfig, logger: Logger):
        super().__init__(
            config,
            logger,
            ApiSchema(
                API_METHOD.GET,
                API_OPERATION.READ,
                uri_schema=Schema(
                    Parameter("dataset", ParamType.DATASET, required=True)
                ),
                query_schema=Schema(
                    Parameter(
                        "metadata",
                        ParamType.LIST,
                        element_type=ParamType.KEYWORD,
                        keywords=Metadata.METADATA_KEYS,
                        key_path=True,
                        string_list=",",
                    )
                ),
                authorization=API_AUTHORIZATION.DATASET,
            ),
        )

    def return_send_file(self, file_path):
        return send_file(file_path)

    def return_send_file(self, file_path):
        return send_file(file_path)

    def _get(self, params: ApiParams, request: Request) -> Response:
        """
        Get the values of client-accessible dataset metadata keys.

        Args:
            json_data: Flask's URI parameter dictionary with dataset name
            request: The original Request object containing query parameters

        GET /api/v1/datasets/metadata?name=dname&metadata=dashboard.seen,server.deletion
        """

        dataset = params.uri["dataset"]
        path = params.uri["path"]

        # Validate the authenticated user's authorization for the combination
        # of "owner" and "access".

        self._check_authorization(
            str(dataset.owner_id), dataset.access, API_OPERATION.READ
        )
        try:
            file_tree = FileTree(self.config, self.logger)
            dataset_location = file_tree.access_dataset(dataset.name)
            file_path = Path(os.path.join(dataset_location, Path(path)))
            if file_path.is_file():
                return self.return_send_file(file_path)
            else:
                raise APIAbort(
                    HTTPStatus.NOT_FOUND, "File is not present in the given path"
                )

        except DatasetNotFound as e:
            raise APIAbort(HTTPStatus.NOT_FOUND, str(e))
