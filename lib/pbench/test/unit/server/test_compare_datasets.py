from http import HTTPStatus
from pathlib import Path

from pquisby.lib.post_processing import QuisbyProcessing
import pytest
import requests

from pbench.server import JSON
from pbench.server.api.resources import ApiBase
from pbench.server.cache_manager import CacheManager, Tarball
from pbench.server.database.models.datasets import Dataset, DatasetNotFound


class TestCompareDatasets:
    @pytest.fixture()
    def query_get_as(self, client, server_config, more_datasets, get_token_func):
        """
        Helper fixture to perform the API query and validate an expected
        return status.

        Args:
            client: Flask test API client fixture
            server_config: Pbench config fixture
            more_datasets: Dataset construction fixture
            get_token_func: Pbench token fixture
        """

        def query_api(
            datasets: list, user, expected_status: HTTPStatus
        ) -> requests.Response:
            ds_list = []
            for dataset in datasets:
                try:
                    dataset_id = Dataset.query(name=dataset).resource_id
                    ds_list.append(dataset_id)
                except DatasetNotFound:
                    ds_list.append(dataset)  # Allow passing deliberately bad value

            headers = {"authorization": f"bearer {get_token_func(user)}"}
            response = client.get(
                f"{server_config.rest_uri}/compare",
                query_string={"datasets": ds_list},
                headers=headers,
            )
            assert response.status_code == expected_status
            return response

        return query_api

    def mock_find_dataset(self, _dataset: str) -> Tarball:
        class Tarball(object):
            tarball_path = Path("/dataset/tarball.tar.xz")

            def extract(_tarball_path: Path, _path: str) -> str:
                return "CSV_file_as_a_byte_stream"

        return Tarball

    def mock_get_dataset_metadata(self, _dataset, _key) -> JSON:
        return {"dataset.metalog.pbench.script": "uperf"}

    def test_get_no_dataset(self, query_get_as):
        response = query_get_as(
            ["nonexistent-dataset", "uperf_1"], "drb", HTTPStatus.NOT_FOUND
        )
        assert response.json == {"message": "Dataset 'nonexistent-dataset' not found"}

    def test_dataset_not_present(self, query_get_as):
        response = query_get_as(["fio_2"], "drb", HTTPStatus.NOT_FOUND)
        assert response.json == {
            "message": "No dataset with ID 'random_md5_string4' found"
        }

    def test_unauthorized_access(self, query_get_as):
        response = query_get_as(["uperf_1", "uperf_2"], "drb", HTTPStatus.FORBIDDEN)
        assert response.json == {
            "message": "User drb is not authorized to READ a resource owned by test with private access"
        }

    def test_unsupported_benchmark(self, query_get_as, monkeypatch):
        extract_data_called = False

        def mock_compare_csv_to_json(*args, **kwargs):
            nonlocal extract_data_called
            extract_data_called = True

        def mock_get_metadata(self, dataset, key) -> JSON:
            return {"dataset.metalog.pbench.script": "hammerDB"}

        monkeypatch.setattr(CacheManager, "find_dataset", self.mock_find_dataset)
        monkeypatch.setattr(ApiBase, "_get_dataset_metadata", mock_get_metadata)
        monkeypatch.setattr(
            QuisbyProcessing, "compare_csv_to_json", mock_compare_csv_to_json
        )
        response = query_get_as(
            ["uperf_1", "uperf_2"], "test", HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        )
        assert response.json["message"] == "Unsupported Benchmark: HAMMERDB"
        assert not extract_data_called

    def test_successful_get(self, query_get_as, monkeypatch):
        def mock_compare_csv_to_json(
            self, benchmark_name, input_type, data_stream
        ) -> JSON:
            return {"status": "success", "json_data": "quisby_data"}

        monkeypatch.setattr(CacheManager, "find_dataset", self.mock_find_dataset)
        monkeypatch.setattr(
            ApiBase, "_get_dataset_metadata", self.mock_get_dataset_metadata
        )
        monkeypatch.setattr(
            QuisbyProcessing, "compare_csv_to_json", mock_compare_csv_to_json
        )

        response = query_get_as(["uperf_1", "uperf_2"], "test", HTTPStatus.OK)
        assert response.json["status"] == "success"
        assert response.json["json_data"] == "quisby_data"

    def test_unsuccessful_get_with_incorrect_data(self, query_get_as, monkeypatch):
        def mock_find_dataset_with_incorrect_data(self, dataset) -> Tarball:
            class Tarball(object):
                tarball_path = Path("/dataset/tarball.tar.xz")

                def extract(tarball_path, path) -> str:
                    return "IncorrectData"

            return Tarball

        def mock_compare_csv_to_json(
            self, benchmark_name, input_type, data_stream
        ) -> JSON:
            return {"status": "failed", "exception": "Unsupported Media Type"}

        monkeypatch.setattr(
            CacheManager, "find_dataset", mock_find_dataset_with_incorrect_data
        )
        monkeypatch.setattr(
            ApiBase, "_get_dataset_metadata", self.mock_get_dataset_metadata
        )
        monkeypatch.setattr(QuisbyProcessing, "extract_data", mock_compare_csv_to_json)
        response = query_get_as(
            ["uperf_1", "uperf_2"], "test", HTTPStatus.INTERNAL_SERVER_ERROR
        )
        assert response.json["message"].startswith(
            "Internal Pbench Server Error: log reference "
        )
