from http import HTTPStatus
from logging import Logger
from pathlib import Path

from flask.wrappers import Request, Response
from flask import send_file
from flask.json import jsonify
import os
from pbench.server import JSON, JSONOBJECT, PbenchServerConfig
from pbench.server.api.resources import (
    APIAbort,
    API_OPERATION,
    ApiBase,
    ParamType,
    Parameter,
    Schema,
)
from pbench.server.database.models.datasets import (
    Dataset,
    DatasetError,
    Metadata,
    MetadataError,
)

from pbench.server.filetree import FileTree,DatasetNotFound

class DatasetsAccess(ApiBase):
    """
    API class to retrieve and mutate Dataset metadata.
    """

    GET_SCHEMA = Schema(
        Parameter(
            "metadata",
            ParamType.LIST,
            element_type=ParamType.KEYWORD,
            keywords=ApiBase.METADATA,
            string_list=",",
        ),
    )

    def __init__(self, config: PbenchServerConfig, logger: Logger):
        super().__init__(
            config,
            logger,
            Schema(
                Parameter("dataset", ParamType.STRING, required=True),
            ),
            role=API_OPERATION.READ,
        )

        self.config= config

    def _get(self, json_data: JSON, request: Request) -> Response:
        """
        Get the values of client-accessible dataset metadata keys.

        Args:
            json_data: Flask's URI parameter dictionary with dataset name
            request: The original Request object containing query parameters

        GET /api/v1/datasets/metadata?name=dname&metadata=dashboard.seen,server.deletion
        """

        name = json_data.get("dataset")
        path = json_data.get("path")

        try:
            dataset = Dataset.query(name=name)
        except DatasetError:
            raise APIAbort(HTTPStatus.BAD_REQUEST, f"Dataset {name!r} not found")

        # Validate the authenticated user's authorization for the combination
        # of "owner" and "access".
        self._check_authorization(
            str(dataset.owner_id), dataset.access, check_role=API_OPERATION.READ
        )
        try:

            file_tree = FileTree(self.config, self.logger)
            tarball = file_tree.find_dataset(dataset.name)
            # access_path = file_tree.access_dataset(dataset.name)
            endd_path = os.path.join(file_tree.incoming_root,tarball.controller_name,dataset.name)
            temp_out= Path(path)
            res_file = os.path.join(endd_path, temp_out)
            # res_file_acess = os.path.join(access_path, temp_out)
            res_file1 = Path(res_file)

            if res_file1.is_file():
            # if os.path.isfile(res_file):
                return send_file(res_file)
            #     return {"status":"OK","message": "File found","path": res_file}

            else:
                return {"status":"OK","message": "file not found","path": res_file}
        except DatasetNotFound as e:
            raise APIAbort(HTTPStatus.NOT_FOUND, str(e))
        # return jsonify({"status":"OK","name":tarball.name, "controller":tarball.controller_name,"path":path})
        # return jsonify({"status":"OK","data":new_data})