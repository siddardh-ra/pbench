from http import HTTPStatus

import pytest

from pbench.server.api.resources import ApiMethod
from pbench.server.api.resources.query_apis.datasets.datasets_contents import (
    DatasetsContents,
)
from pbench.server.database.models.datasets import Dataset
from pbench.test.unit.server.query_apis.commons import Commons


class TestDatasetsContents(Commons):
    """
    Unit testing for DatasetsContents class.
    In a web service context, we access class functions mostly via the
    Flask test client rather than trying to directly invoke the class
    constructor and `get` service.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client):
        super()._setup(
            cls_obj=DatasetsContents(client.config),
            pbench_endpoint="/datasets/random_md5_string1/contents/1-default",
            elastic_endpoint="/_search",
            index_from_metadata="run-toc",
        )

    api_method = ApiMethod.GET

    def test_with_no_uri_args(self, client, server_config):
        """
        Check the DatasetsContents API when no dataset or path is provided
        """
        # remove the last two components of the pbench_endpoint
        incorrect_endpoint = "/datasets/contents/"
        response = client.get(f"{server_config.rest_uri}{incorrect_endpoint}/")
        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_with_incorrect_path(self, client, server_config, pbench_drb_token):
        """
        Check the Contents API when an incorrect path is provided.
        """
        incorrect_endpoint = (
            "/".join(self.pbench_endpoint.split("/")[:-1]) + "/random_md5_string2"
        )
        response = client.get(
            f"{server_config.rest_uri}{incorrect_endpoint}",
            headers={"Authorization": "Bearer " + pbench_drb_token},
        )
        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_query(
        self,
        server_config,
        query_api,
        pbench_drb_token,
        build_auth_header,
        find_template,
        provide_metadata,
    ):
        """
        Check behaviour of Contents API when both sub-directories and
        the list of files are present in the given payload.
        """
        response_payload = {
            "took": 6,
            "timed_out": False,
            "_shards": {"total": 3, "successful": 3, "skipped": 0, "failed": 0},
            "hits": {
                "total": {"value": 2, "relation": "eq"},
                "max_score": 0.0,
                "hits": [
                    {
                        "_index": "riya-pbench.v6.run-toc.2021-05",
                        "_type": "_doc",
                        "_id": "d4a8cc7c4ecef7vshg4tjhrew174828d",
                        "_score": 0.0,
                        "_source": {
                            "parent": "/",
                            "directory": "/1-default",
                            "mtime": "2021-05-01T24:00:00",
                            "mode": "0o755",
                            "name": "1-default",
                            "files": [
                                {
                                    "name": "reference-result",
                                    "mtime": "2021-05-01T24:00:00",
                                    "size": 0,
                                    "mode": "0o777",
                                    "type": "sym",
                                    "linkpath": "sample1",
                                }
                            ],
                            "run_data_parent": "ece030bdgfkjasdkf7435e6a7a6be804",
                            "authorization": {"owner": "1", "access": "private"},
                            "@timestamp": "2021-05-01T24:00:00",
                        },
                    },
                    {
                        "_index": "riya-pbench.v6.run-toc.2021-05",
                        "_type": "_doc",
                        "_id": "3bba25b62fhdgfajgsfdty6797ed06a",
                        "_score": 0.0,
                        "_source": {
                            "parent": "/1-default",
                            "directory": "/1-default/sample1",
                            "mtime": "2021-05-01T24:00:00",
                            "mode": "0o755",
                            "name": "sample1",
                            "ancestor_path_elements": ["1-default"],
                            "files": [
                                {
                                    "name": "result.txt",
                                    "mtime": "2021-05-01T24:00:00",
                                    "size": 0,
                                    "mode": "0o644",
                                    "type": "reg",
                                },
                                {
                                    "name": "user-benchmark.cmd",
                                    "mtime": "2021-05-01T24:00:00",
                                    "size": 114,
                                    "mode": "0o755",
                                    "type": "reg",
                                },
                            ],
                            "run_data_parent": "ece030bdgfkjasdkf7435e6a7a6be804",
                            "authorization": {"owner": "1", "access": "private"},
                            "@timestamp": "2021-05-01T24:00:00",
                        },
                    },
                ],
            },
        }
        index = self.build_index_from_metadata()

        # get_expected_status() expects to read username and access from the
        # JSON client payload, however this API acquires that information
        # from the Dataset. Construct a fake payload corresponding to the
        # attach_dataset fixture.
        auth_json = {"user": "drb", "access": "private"}
        expected_status = self.get_expected_status(
            auth_json, build_auth_header["header_param"]
        )

        response = query_api(
            self.pbench_endpoint,
            self.elastic_endpoint,
            payload=None,
            expected_index=index,
            expected_status=expected_status,
            json=response_payload,
            status=HTTPStatus.OK,
            headers=build_auth_header["header"],
            request_method=self.api_method,
        )
        if expected_status == HTTPStatus.OK:
            res_json = response.json
            expected_result = {
                "directories": ["sample1"],
                "files": [
                    {
                        "name": "reference-result",
                        "mtime": "2021-05-01T24:00:00",
                        "size": 0,
                        "mode": "0o777",
                        "type": "sym",
                        "linkpath": "sample1",
                    }
                ],
            }
            assert expected_result == res_json

    def test_subdirectory_query(
        self,
        server_config,
        query_api,
        pbench_drb_token,
        build_auth_header,
        find_template,
        provide_metadata,
    ):
        """
        Check the API when only sub-directories are present in the
        payload and NO files list.
        """
        response_payload = {
            "took": 7,
            "timed_out": False,
            "_shards": {"total": 3, "successful": 3, "skipped": 0, "failed": 0},
            "hits": {
                "total": {"value": 2, "relation": "eq"},
                "max_score": 0.0,
                "hits": [
                    {
                        "_index": "riya-pbench.v6.run-toc.2021-05",
                        "_type": "_doc",
                        "_id": "d4a8cc7c4ecef7vshg4tjhrew174828d",
                        "_score": 0.0,
                        "_source": {
                            "parent": "/",
                            "directory": "/1-default",
                            "mtime": "2021-05-01T24:00:00",
                            "mode": "0o755",
                            "name": "1-default",
                            "run_data_parent": "ece030bdgfkjasdkf7435e6a7a6be804",
                            "authorization": {"owner": "1", "access": "private"},
                            "@timestamp": "2021-05-01T24:00:00",
                        },
                    },
                    {
                        "_index": "riya-pbench.v6.run-toc.2021-05",
                        "_type": "_doc",
                        "_id": "3bba25b62fhdgfajgsfdty6797ed06a",
                        "_score": 0.0,
                        "_source": {
                            "parent": "/1-default",
                            "directory": "/1-default/sample1",
                            "mtime": "2021-05-01T24:00:00",
                            "mode": "0o755",
                            "name": "sample1",
                            "ancestor_path_elements": ["1-default"],
                            "files": [
                                {
                                    "name": "result.txt",
                                    "mtime": "2021-05-01T24:00:00",
                                    "size": 0,
                                    "mode": "0o644",
                                    "type": "reg",
                                },
                                {
                                    "name": "user-benchmark.cmd",
                                    "mtime": "2021-05-01T24:00:00",
                                    "size": 114,
                                    "mode": "0o755",
                                    "type": "reg",
                                },
                            ],
                            "run_data_parent": "ece030bdgfkjasdkf7435e6a7a6be804",
                            "authorization": {"owner": "1", "access": "private"},
                            "@timestamp": "2021-05-01T24:00:00",
                        },
                    },
                ],
            },
        }
        index = self.build_index_from_metadata()

        # get_expected_status() expects to read username and access from the
        # JSON client payload, however this API acquires that information
        # from the Dataset. Construct a fake payload corresponding to the
        # attach_dataset fixture.
        auth_json = {"user": "drb", "access": "private"}
        expected_status = self.get_expected_status(
            auth_json, build_auth_header["header_param"]
        )

        response = query_api(
            self.pbench_endpoint,
            self.elastic_endpoint,
            payload=None,
            expected_index=index,
            expected_status=expected_status,
            json=response_payload,
            status=HTTPStatus.OK,
            headers=build_auth_header["header"],
            request_method=self.api_method,
        )
        if expected_status == HTTPStatus.OK:
            res_json = response.json
            expected_result = {"directories": ["sample1"], "files": []}
            assert expected_result == res_json

    def test_files_query(
        self,
        server_config,
        query_api,
        pbench_drb_token,
        build_auth_header,
        find_template,
        provide_metadata,
    ):
        """
        Checks the API when only list of files are present in a directory.
        """
        response_payload = {
            "took": 7,
            "timed_out": False,
            "_shards": {"total": 3, "successful": 3, "skipped": 0, "failed": 0},
            "hits": {
                "total": {"value": 1, "relation": "eq"},
                "max_score": 0.0,
                "hits": [
                    {
                        "_index": "riya-pbench.v6.run-toc.2021-05",
                        "_type": "_doc",
                        "_id": "9e95ccb385b7a7a2d70ededa07c391da",
                        "_score": 0.0,
                        "_source": {
                            "parent": "/",
                            "directory": "/1-default",
                            "mtime": "2021-05-01T24:00:00",
                            "mode": "0o755",
                            "files": [
                                {
                                    "name": "default.csv",
                                    "mtime": "2021-05-01T24:00:00",
                                    "size": 122,
                                    "mode": "0o644",
                                    "type": "reg",
                                }
                            ],
                            "run_data_parent": "ece030bdgfkjasdkf7435e6a7a6be804",
                            "authorization": {"owner": "1", "access": "private"},
                            "@timestamp": "2021-05-01T24:00:00",
                        },
                    }
                ],
            },
        }
        index = self.build_index_from_metadata()

        # get_expected_status() expects to read username and access from the
        # JSON client payload, however this API acquires that information
        # from the Dataset. Construct a fake payload corresponding to the
        # attach_dataset fixture.
        auth_json = {"user": "drb", "access": "private"}
        expected_status = self.get_expected_status(
            auth_json, build_auth_header["header_param"]
        )

        response = query_api(
            self.pbench_endpoint,
            self.elastic_endpoint,
            payload=None,
            expected_index=index,
            expected_status=expected_status,
            json=response_payload,
            status=HTTPStatus.OK,
            headers=build_auth_header["header"],
            request_method=self.api_method,
        )
        if expected_status == HTTPStatus.OK:
            res_json = response.json
            expected_result = {
                "directories": [],
                "files": [
                    {
                        "name": "default.csv",
                        "mtime": "2021-05-01T24:00:00",
                        "size": 122,
                        "mode": "0o644",
                        "type": "reg",
                    }
                ],
            }
            assert expected_result == res_json

    def test_no_subdirectory_no_files_query(
        self,
        server_config,
        query_api,
        pbench_drb_token,
        build_auth_header,
        find_template,
        provide_metadata,
    ):
        """
        Check the API when no subdirectory or files are present.
        """
        response_payload = {
            "took": 7,
            "timed_out": False,
            "_shards": {"total": 3, "successful": 3, "skipped": 0, "failed": 0},
            "hits": {
                "total": {"value": 1, "relation": "eq"},
                "max_score": 0.0,
                "hits": [
                    {
                        "_index": "riya-pbench.v6.run-toc.2021-05",
                        "_type": "_doc",
                        "_id": "9e95ccb385b7a7a2d70ededa07c391da",
                        "_score": 0.0,
                        "_source": {
                            "parent": "/",
                            "directory": "/1-default",
                            "mtime": "2021-05-01T24:00:00",
                            "mode": "0o755",
                            "run_data_parent": "ece030bdgfkjasdkf7435e6a7a6be804",
                            "authorization": {"owner": "1", "access": "private"},
                            "@timestamp": "2021-05-01T24:00:00",
                        },
                    }
                ],
            },
        }
        index = self.build_index_from_metadata()

        # get_expected_status() expects to read username and access from the
        # JSON client payload, however this API acquires that information
        # from the Dataset. Construct a fake payload corresponding to the
        # attach_dataset fixture.
        auth_json = {"user": "drb", "access": "private"}
        expected_status = self.get_expected_status(
            auth_json, build_auth_header["header_param"]
        )

        response = query_api(
            self.pbench_endpoint,
            self.elastic_endpoint,
            payload=None,
            expected_index=index,
            expected_status=expected_status,
            json=response_payload,
            status=HTTPStatus.OK,
            headers=build_auth_header["header"],
            request_method=self.api_method,
        )
        if expected_status == HTTPStatus.OK:
            res_json = response.json
            expected_result = {"directories": [], "files": []}
            assert expected_result == res_json

    def test_empty_query(
        self,
        server_config,
        query_api,
        pbench_drb_token,
        build_auth_header,
        find_template,
        provide_metadata,
    ):
        """
        Check the API when a directory is empty.
        """
        response_payload = {
            "took": 55,
            "timed_out": False,
            "_shards": {"total": 3, "successful": 3, "skipped": 0, "failed": 0},
            "hits": {
                "total": {"value": 0, "relation": "eq"},
                "max_score": None,
                "hits": [],
            },
        }
        index = self.build_index_from_metadata()

        # get_expected_status() expects to read username and access from the
        # JSON client payload, however this API acquires that information
        # from the Dataset. Construct a fake payload corresponding to the
        # attach_dataset fixture.
        auth_json = {"user": "drb", "access": "private"}
        expected_status = self.get_expected_status(
            auth_json, build_auth_header["header_param"]
        )

        response = query_api(
            self.pbench_endpoint,
            self.elastic_endpoint,
            payload=None,
            expected_index=index,
            expected_status=expected_status
            if expected_status != HTTPStatus.OK
            else HTTPStatus.NOT_FOUND,
            json=response_payload,
            status=HTTPStatus.OK,
            headers=build_auth_header["header"],
            request_method=self.api_method,
        )
        if expected_status == HTTPStatus.NOT_FOUND:
            res_json = response.json
            expected_result = {
                "message": "No directory '/1-default' in 'drb' contents."
            }
            assert expected_result == res_json

    def test_get_index(self, attach_dataset, provide_metadata):
        drb = Dataset.query(name="drb")
        indices = self.cls_obj.get_index(drb, self.index_from_metadata)
        assert indices == "unit-test.v6.run-toc.2020-05"

    @pytest.mark.parametrize("name", ("wrong", ""))
    def test_missing_name(self, client, server_config, pbench_drb_token, name):
        expected_status = HTTPStatus.NOT_FOUND
        incorrect_endpoint = self.pbench_endpoint.rsplit("/", 1)[0] + "/" + name
        response = client.get(
            incorrect_endpoint,
            headers={"Authorization": "Bearer " + pbench_drb_token},
        )
        assert response.status_code == expected_status
