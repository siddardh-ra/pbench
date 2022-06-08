from http import HTTPStatus

import pytest
import requests

from pbench.server import JSON, PbenchServerConfig


class TestDatasetsAccess:

    @pytest.fixture()
    def query_get_as(self, client, server_config, more_datasets, provide_metadata):
        """
        Helper fixture to perform the API query and validate an expected
        return status.

        Args:
            client: Flask test API client fixture
            server_config: Pbench config fixture
            more_datasets: Dataset construction fixture
            provide_metadata: Dataset metadata fixture
        """

        def query_api(
            dataset: str,  username: str, expected_status: HTTPStatus ,path :str
        ) -> requests.Response:
            headers = None
            if username:
                token = self.token(client, server_config, username)
                headers = {"authorization": f"bearer {token}"}
            response = client.get(
                f"{server_config.rest_uri}/inventory/{dataset}/{path}",
                headers=headers,
            )
            assert response.status_code == expected_status

            # We need to log out to avoid "duplicate auth token" errors on the
            # "put" test which does a PUT followed by two GETs.
            if username:
                client.post(
                    f"{server_config.rest_uri}/logout",
                    headers={"authorization": f"bearer {token}"},
                )
            return response

        return query_api

    def token(self, client, config: PbenchServerConfig, user: str) -> str:
        response = client.post(
            f"{config.rest_uri}/login",
            json={"username": user, "password": "12345"},
        )
        assert response.status_code == HTTPStatus.OK
        data = response.json
        assert data["auth_token"]
        return data["auth_token"]

    def test_get_no_dataset(self, query_get_as):
        response = query_get_as(
            "foobar",
            "drb",
            HTTPStatus.BAD_REQUEST,
            "metadata.log"
        )
        assert response.json == {"message": "Dataset 'foobar' not found"}

    def test_dataset_not_present(self, query_get_as):
        response = query_get_as(
            "fio_2",
            "test",
            HTTPStatus.NOT_FOUND,
            "metadata.log"
        )
        assert response.json == {"message": "The dataset named 'fio_2' is not present in the file tree"}


    # def test_dataset_in_given_path(self, query_get_as):
    #     response = query_get_as(
    #         "fio_1",
    #         "drb",
    #         HTTPStatus.NOT_FOUND,
    #         "1-default/default.csv"
    #     )
    #     print(response)
    #     assert response.status_code == HTTPStatus.OK