from http import HTTPStatus

import pytest

from pbench.server.api.resources.query_apis.datasets_search import DatasetsSearch
from pbench.test.unit.server.query_apis.commons import Commons


class TestDatasetSummary(Commons):
    """
    Unit testing for resources/IndexSearch class.

    In a web service context, we access class functions mostly via the
    Flask test client rather than trying to directly invoke the class
    constructor and `post` service.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client):
        super()._setup(
            cls_obj=DatasetsSearch(client.config),
            pbench_endpoint="/datasets/search",
            elastic_endpoint="/_search?ignore_unavailable=true",
            payload={
                "user": "drb",
                "access": "private",
                "start": "2020-08",
                "end": "2020-10",
                "search_term": "random_string",
            },
            empty_es_response_payload=self.EMPTY_ES_RESPONSE_PAYLOAD,
        )

    @pytest.mark.parametrize(
        "user",
        ("drb", "badwolf", "no_user"),
    )
    def test_query(
        self,
        client,
        server_config,
        query_api,
        find_template,
        build_auth_header,
        user,
    ):
        """
        Check the construction of Elasticsearch query URI and filtering of the response body.
        The test will run once with each parameter supplied from the local parameterization,
        and, for each of those, multiple times with different values of the build_auth_header fixture.
        """
        payload = {
            "user": user,
            "access": "private",
            "start": "2021-06",
            "end": "2021-08",
            "search_term": "random_string",
            "fields": [
                "@metadata.controller_dir",
                "@timestamp",
                "run.controller",
                "run.name",
            ],
        }
        if user == "no_user":
            del payload["user"]
        if user == "no_user" or user is None:
            payload["access"] = "public"

        response_payload = {
            "took": 11,
            "timed_out": "false",
            "_shards": {"total": 5, "successful": 5, "skipped": 2, "failed": 0},
            "hits": {
                "total": {"value": 3, "relation": "eq"},
                "max_score": "null",
                "hits": [
                    {
                        "_index": "npalaska-pbench.v6.run-data.2021-07",
                        "_type": "_doc",
                        "_id": "f3a37c9891a78886639e3bc00e3c5c4e",
                        "_score": "null",
                        "_source": {
                            "@timestamp": "2021-07-14T15:30:23.652778",
                            "run": {
                                "controller": "dhcp31-171.example.com",
                                "name": "uperf_npalaska-dhcp31-171_2021.07.14T15.30.22",
                            },
                            "@metadata": {"controller_dir": "dhcp31-171.example.com"},
                        },
                        "sort": [1626276623652],
                    },
                    {
                        "_index": "npalaska-pbench.v6.run-data.2021-07",
                        "_type": "_doc",
                        "_id": "1c25e9f5b5dfc1ffb732931bf3899878",
                        "_score": "null",
                        "_source": {
                            "@timestamp": "2021-07-12T22:44:19.562354",
                            "run": {
                                "controller": "dhcp31-171.example.com",
                                "name": "pbench-user-benchmark_npalaska-dhcp31-171_2021.07.12T22.44.19",
                            },
                            "@metadata": {"controller_dir": "dhcp31-171.example.com"},
                        },
                        "sort": [1626129859562],
                    },
                    {
                        "_index": "npalaska-pbench.v6.run-data.2021-07",
                        "_type": "_doc",
                        "_id": "6e9a82d1167ed1dc4053c3654fe8af13",
                        "_score": "null",
                        "_source": {
                            "@timestamp": "2021-07-12T14:08:46.563303",
                            "run": {
                                "controller": "dhcp31-171.example.com",
                                "name": "pbench-user-benchmark_npalaska-dhcp31-171_2021.07.12T14.08.46",
                            },
                            "@metadata": {"controller_dir": "dhcp31-171.example.com"},
                        },
                        "sort": [1626098926563],
                    },
                ],
            },
        }
        index = self.build_index(
            server_config, self.date_range(payload["start"], payload["end"])
        )
        expected_status = self.get_expected_status(
            payload, build_auth_header["header_param"]
        )
        response = query_api(
            self.pbench_endpoint,
            self.elastic_endpoint,
            payload,
            index,
            expected_status,
            headers=build_auth_header["header"],
            status=expected_status,
            json=response_payload,
        )
        assert response.status_code == expected_status
        if response.status_code == HTTPStatus.OK:
            res_json = response.json
            assert isinstance(res_json, list)
            assert len(res_json) == 3
            expected_result = {
                "id": "1c25e9f5b5dfc1ffb732931bf3899878",
                "@timestamp": "2021-07-12T22:44:19.562354",
                "run": {
                    "controller": "dhcp31-171.example.com",
                    "name": "pbench-user-benchmark_npalaska-dhcp31-171_2021.07.12T22.44.19",
                },
                "@metadata": {"controller_dir": "dhcp31-171.example.com"},
            }
            assert res_json[1] == expected_result
