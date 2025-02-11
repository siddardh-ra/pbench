from http import HTTPStatus
from urllib.request import Request

from flask import current_app, jsonify
from flask.wrappers import Response
from pquisby.lib.post_processing import BenchmarkName, InputType, QuisbyProcessing

from pbench.server import OperationCode, PbenchServerConfig
from pbench.server.api.resources import (
    APIAbort,
    ApiAuthorizationType,
    ApiBase,
    ApiContext,
    APIInternalError,
    ApiMethod,
    ApiParams,
    ApiSchema,
    Parameter,
    ParamType,
    Schema,
)
from pbench.server.cache_manager import (
    CacheManager,
    TarballNotFound,
    TarballUnpackError,
)
from pbench.server.database import Dataset


class DatasetsVisualize(ApiBase):
    """
    This class implements the Server API used to retrieve data for visualization.
    """

    def __init__(self, config: PbenchServerConfig):
        super().__init__(
            config,
            ApiSchema(
                ApiMethod.GET,
                OperationCode.READ,
                uri_schema=Schema(
                    Parameter("dataset", ParamType.DATASET, required=True),
                ),
                authorization=ApiAuthorizationType.DATASET,
            ),
        )

    def _get(
        self, params: ApiParams, request: Request, context: ApiContext
    ) -> Response:
        """
        This function is using Quisby to process results into a form that supports visualization

        Args:
            params: includes the uri parameters, which provide the dataset.
            request: Original incoming Request object
            context: API context dictionary

        Raises:
            APIAbort, reporting "NOT_FOUND" and "INTERNAL_SERVER_ERROR"

        GET /api/v1/visualize/{dataset}
        """

        dataset = params.uri["dataset"]
        cache_m = CacheManager(self.config, current_app.logger)

        try:
            tarball = cache_m.find_dataset(dataset.resource_id)
        except TarballNotFound as e:
            raise APIAbort(
                HTTPStatus.NOT_FOUND, f"No dataset with ID '{e.tarball}' found"
            ) from e

        metadata = self._get_dataset_metadata(
            dataset, ["dataset.metalog.pbench.script"]
        )
        benchmark = metadata["dataset.metalog.pbench.script"].upper()
        benchmark_type = BenchmarkName.__members__.get(benchmark)
        if not benchmark_type:
            raise APIAbort(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE, f"Unsupported Benchmark: {benchmark}"
            )

        name = Dataset.stem(tarball.tarball_path)
        try:
            file = tarball.extract(tarball.tarball_path, f"{name}/result.csv")
        except TarballUnpackError as e:
            raise APIInternalError(str(e)) from e

        get_quisby_data = QuisbyProcessing().extract_data(
            benchmark_type, dataset.name, InputType.STREAM, file
        )

        if get_quisby_data["status"] != "success":
            raise APIInternalError(
                f"Quisby processing failure. Exception: {get_quisby_data['exception']}"
            )
        return jsonify(get_quisby_data)
