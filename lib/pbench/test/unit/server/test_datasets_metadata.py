from http import HTTPStatus

import pytest
import requests

from pbench.server import JSON, OperationCode
from pbench.server.database.models.audit import Audit, AuditStatus, AuditType
from pbench.server.database.models.datasets import Dataset, DatasetNotFound, Metadata


class TestDatasetsMetadataGet:
    @pytest.fixture()
    def query_get_as(
        self, client, server_config, more_datasets, provide_metadata, get_token_func
    ):
        """
        Helper fixture to perform the API query and validate an expected
        return status.

        Args:
            client: Flask test API client fixture
            server_config: Pbench config fixture
            more_datasets: Dataset construction fixture
            provide_metadata: Dataset metadata fixture
            get_token_func: Pbench token fixture
        """

        def query_api(
            ds_name: str, payload: JSON, username: str, expected_status: HTTPStatus
        ) -> requests.Response:
            headers = None
            try:
                dataset = Dataset.query(name=ds_name).resource_id
            except DatasetNotFound:
                dataset = ds_name  # Allow passing deliberately bad value
            if username:
                token = get_token_func(username)
                headers = {"authorization": f"bearer {token}"}
            response = client.get(
                f"{server_config.rest_uri}/datasets/{dataset}/metadata",
                headers=headers,
                query_string=payload,
            )
            assert (
                response.status_code == expected_status
            ), f"Unexpected status {response.status_code}, {response.data}"

            # We need to log out to avoid "duplicate auth token" errors on the
            # "put" test which does a PUT followed by two GETs.
            if username:
                client.post(
                    f"{server_config.rest_uri}/logout",
                    headers={"authorization": f"bearer {token}"},
                )
            return response

        return query_api

    def test_get_no_dataset(self, query_get_as):
        response = query_get_as(
            "foobar",
            {"metadata": ["global.seen", "global.saved"]},
            "drb",
            HTTPStatus.NOT_FOUND,
        )
        assert response.json == {"message": "Dataset 'foobar' not found"}

    def test_get_bad_keys(self, query_get_as):
        response = query_get_as(
            "drb",
            {"metadata": ["xyzzy", "plugh", "dataset.owner", "dataset.access"]},
            "drb",
            HTTPStatus.BAD_REQUEST,
        )
        assert response.json == {
            "message": "Unrecognized list values ['plugh', 'xyzzy'] given for parameter metadata; expected ['dataset', 'global', 'server', 'user']"
        }

    def test_get1(self, query_get_as):
        response = query_get_as(
            "drb",
            {
                "metadata": ["global.seen", "server", "dataset.access"],
            },
            "drb",
            HTTPStatus.OK,
        )
        assert response.json == {
            "global.seen": None,
            "server": {
                "deletion": "2022-12-26",
                "index-map": {
                    "unit-test.v6.run-data.2020-08": ["random_md5_string1"],
                    "unit-test.v5.result-data-sample.2020-08": ["random_document_uuid"],
                    "unit-test.v6.run-toc.2020-05": ["random_md5_string1"],
                },
            },
            "dataset.access": "private",
        }

    def test_get2(self, query_get_as):
        response = query_get_as(
            "drb",
            {
                "metadata": "global.seen,server.deletion,dataset",
            },
            "drb",
            HTTPStatus.OK,
        )
        assert response.json == {
            "global.seen": None,
            "server.deletion": "2022-12-26",
            "dataset": {
                "access": "private",
                "name": "drb",
                "owner": "drb",
                "uploaded": "2022-01-01T00:00:00+00:00",
                "metalog": {
                    "pbench": {
                        "config": "test1",
                        "date": "2020-02-15T00:00:00",
                        "name": "drb",
                        "script": "unit-test",
                    },
                    "run": {"controller": "node1.example.com"},
                },
                "operations": {},
            },
        }

    def test_get3(self, query_get_as):
        response = query_get_as(
            "drb",
            {
                "metadata": [
                    "global.seen",
                    "server.deletion,dataset.access",
                    "user.favorite",
                ],
            },
            "drb",
            HTTPStatus.OK,
        )
        assert response.json == {
            "global.seen": None,
            "server.deletion": "2022-12-26",
            "dataset.access": "private",
            "user.favorite": None,
        }

    def test_get_private_noauth(self, query_get_as):
        response = query_get_as(
            "drb",
            {
                "metadata": [
                    "global.seen",
                    "server.deletion,dataset.access",
                    "user",
                ]
            },
            "test",
            HTTPStatus.FORBIDDEN,
        )
        assert (
            response.json["message"]
            == "User test is not authorized to READ a resource owned by drb with private access"
        )

    def test_get_unauth(self, query_get_as):
        response = query_get_as(
            "drb",
            {
                "metadata": [
                    "global.seen",
                    "server.deletion,dataset.access",
                    "user",
                ],
            },
            None,
            HTTPStatus.UNAUTHORIZED,
        )
        assert (
            response.json["message"]
            == "Unauthenticated client is not authorized to READ a resource owned by drb with private access"
        )

    def test_get_bad_query(self, query_get_as):
        response = query_get_as(
            "drb",
            {
                "controller": "foobar",
                "metadata": "global.seen,server.deletion,dataset.access",
            },
            "drb",
            HTTPStatus.BAD_REQUEST,
        )
        assert response.json == {"message": "Unknown URL query keys: controller"}

    def test_get_bad_query_2(self, query_get_as):
        response = query_get_as(
            "drb",
            {
                "controller": "foobar",
                "plugh": "xyzzy",
                "metadata": ["global.seen", "server.deletion", "dataset.access"],
            },
            "drb",
            HTTPStatus.BAD_REQUEST,
        )
        assert response.json == {"message": "Unknown URL query keys: controller,plugh"}

    def test_get_funky_metalog_key(self, query_get_as):
        """Test funky metadata.log key

        Normally we constrain metadata keys to lowercase alphanumeric strings.
        Traditional Pbench Agent `metadata.log` files contain keys constructed
        from benchmark iteration values that can contain mixed case and symbol
        characters. We allow these keys to be filtered and retrieved, but not
        created, so test that we can filter on a funky key value and return
        the key.

        Args:
            query_get_as: Query helper fixture
        """
        fio_1 = Dataset.query(name="fio_1")
        Metadata.create(
            dataset=fio_1,
            key=Metadata.METALOG,
            value={
                "pbench": {
                    "date": "2020-02-15T00:00:00",
                    "config": "test1",
                    "script": "unit-test",
                    "name": "fio_1",
                },
                "iterations/fooBar=10-what_else@weird": {
                    "iteration_name": "fooBar=10-what_else@weird"
                },
                "run": {"controller": "node1.example.com"},
            },
        )
        response = query_get_as(
            "fio_1",
            {
                "metadata": ["dataset.metalog.iterations/fooBar=10-what_else@weird"],
            },
            "drb",
            HTTPStatus.OK,
        )
        assert response.json == {
            "dataset.metalog.iterations/fooBar=10-what_else@weird": {
                "iteration_name": "fooBar=10-what_else@weird"
            }
        }


class TestDatasetsMetadataPut(TestDatasetsMetadataGet):
    @pytest.fixture()
    def query_put_as(
        self, client, server_config, more_datasets, provide_metadata, get_token_func
    ):
        """
        Helper fixture to perform the API query and validate an expected
        return status.

        Args:
            client: Flask test API client fixture
            server_config: Pbench config fixture
            more_datasets: Dataset construction fixture
            provide_metadata: Dataset metadata fixture
            get_token_func: Pbench token fixture
        """

        def query_api(
            ds_name: str, payload: JSON, username: str, expected_status: HTTPStatus
        ) -> requests.Response:
            headers = None
            try:
                dataset = Dataset.query(name=ds_name).resource_id
            except DatasetNotFound:
                dataset = ds_name  # Allow passing deliberately bad value
            if username:
                token = get_token_func(username)
                headers = {"authorization": f"bearer {token}"}
            response = client.put(
                f"{server_config.rest_uri}/datasets/{dataset}/metadata",
                headers=headers,
                json=payload,
            )
            assert response.status_code == expected_status

            # We need to log out to avoid "duplicate auth token" errors on the
            # test case which does a PUT followed by two GETs.
            if username:
                client.post(
                    f"{server_config.rest_uri}/logout",
                    headers={"authorization": f"bearer {token}"},
                )
            return response

        return query_api

    def test_put_missing_uri_param(self, client, server_config, pbench_drb_token):
        """
        Test behavior when no dataset name is given on the URI. (NOTE that
        Flask automatically handles this with a NOT_FOUND response.)
        """
        response = client.put(f"{server_config.rest_uri}/datasets/metadata/")
        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_put_missing_key(self, client, server_config, pbench_drb_token):
        """
        Test behavior when JSON payload does not contain all required keys.

        Note that Pbench will silently ignore any additional keys that are
        specified but not required.
        """
        response = client.put(
            f"{server_config.rest_uri}/datasets/drb/metadata", json={}
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json.get("message") == "Missing required parameters: metadata"

    def test_put_no_dataset(self, client, server_config, attach_dataset):
        response = client.put(
            f"{server_config.rest_uri}/datasets/foobar/metadata",
            json={"metadata": {"global.seen": True, "global.saved": False}},
        )
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert response.json == {"message": "Dataset 'foobar' not found"}

    @pytest.mark.parametrize(
        "keys,keyerr",
        (
            (
                {"xyzzy": "private", "what": "sup", "global.saved": True},
                "'what', 'xyzzy'",
            ),
            ({"global": {"Ab.foo": True}}, "'Ab.foo'"),
            ({"global": {"ab@": True}}, "'ab@'"),
            ({"global": {"abc": {"#$": "bad key"}}}, "'#$'"),
            (
                {
                    "global": {
                        "a": {
                            "#bad": {"still@bad": "ok", "good": True},
                            ".no": {"Yes": 0, "no?": 1},
                        }
                    }
                },
                "'#bad', '.no', 'Yes', 'no?', 'still@bad'",
            ),
            ({"global.AbC@foo=y": True}, "'global.AbC@foo=y'"),
            ({"global..foo": True}, "'global..foo'"),
        ),
    )
    def test_put_bad_keys(self, client, server_config, attach_dataset, keys, keyerr):
        response = client.put(
            f"{server_config.rest_uri}/datasets/drb/metadata",
            json={"metadata": keys},
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST, response.json["message"]
        msg = response.json["message"]
        assert "Unrecognized JSON key" in msg and keyerr in msg

    def test_put_reserved_metadata(self, client, server_config, attach_dataset):
        response = client.put(
            f"{server_config.rest_uri}/datasets/drb/metadata",
            json={"metadata": {"dataset.access": "private"}},
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json == {
            "message": "Unrecognized JSON key ['dataset.access'] for parameter metadata."
        }

    def test_put_nowrite(self, query_get_as, query_put_as):
        response = query_put_as(
            "fio_1",
            {"metadata": {"global.seen": False, "global.saved": True}},
            "test",
            HTTPStatus.FORBIDDEN,
        )
        assert (
            response.json["message"]
            == "User test is not authorized to UPDATE a resource owned by drb with public access"
        )

    def test_put_noauth(self, query_get_as, query_put_as):
        response = query_put_as(
            "fio_1",
            {"metadata": {"global.seen": False, "global.saved": True}},
            None,
            HTTPStatus.UNAUTHORIZED,
        )
        assert (
            response.json["message"]
            == "Unauthenticated client is not authorized to UPDATE a resource owned by drb with public access"
        )

    def test_put_invalid_name(self, query_get_as, query_put_as):
        """
        Test that invalid special values for dataset.name are detected before
        any metadata is changed and that we fail with BAD_REQUEST rather than
        with an internal error.
        """
        put = query_put_as(
            "drb",
            {
                "metadata": {
                    "global.dashboard.c": 1,
                    "dataset.name": 1,
                    "global.dashboard.test": "A",
                }
            },
            "drb",
            HTTPStatus.BAD_REQUEST,
        )
        json = put.json
        assert json["message"] == "at least one specified metadata key is invalid"
        assert json["errors"] == [
            "Metadata key 'dataset.name' value 1 for dataset (drb)|drb must be a UTF-8 string of 1 to 1024 characters"
        ]

        # verify that the values didn't change
        get = query_get_as(
            "drb",
            {"metadata": "global.dashboard.c,dataset.name,global.dashboard.test"},
            "drb",
            HTTPStatus.OK,
        )
        assert get.json == {
            "dataset.name": "drb",
            "global.dashboard.test": None,
            "global.dashboard.c": None,
        }

    def test_put_invalid_deletion(self, query_get_as, query_put_as):
        """
        Test that invalid special values for server.deletion are detected
        before any metadata is changed and that we fail with BAD_REQUEST rather
        than with an internal error.
        """
        put = query_put_as(
            "drb",
            {
                "metadata": {
                    "user.one": 2,
                    "server.deletion": "1800-25-55",
                    "user.dashboard.test": "B",
                }
            },
            "drb",
            HTTPStatus.BAD_REQUEST,
        )
        json = put.json
        assert json["message"] == "at least one specified metadata key is invalid"
        assert json["errors"] == [
            "Metadata key 'server.deletion' value '1800-25-55' for dataset (drb)|drb must be a date/time"
        ]

        # verify that the values didn't change
        get = query_get_as(
            "drb",
            {"metadata": "server.deletion,user.dashboard.test,user.one"},
            "drb",
            HTTPStatus.OK,
        )
        assert get.json == {
            "server.deletion": "2022-12-26",
            "user.dashboard.test": None,
            "user.one": None,
        }

    def test_put_set_errors(self, capinternal, monkeypatch, query_get_as, query_put_as):
        """Test a partial success. We set a scalar value on a key and then try
        to set a nested value: i.e., with "global.dashboard.nested = False", we
        attempt to set "global.dashboard.nested.dummy". We expect this to fail,
        but we expect other values to succeed: this should return a success, but
        with accumulated error information in the response payload.
        """
        query_put_as(
            "drb",
            {"metadata": {"global.dashboard.nested": False}},
            "drb",
            HTTPStatus.OK,
        )
        response = query_put_as(
            "drb",
            {
                "metadata": {
                    "global.dashboard.seen": False,
                    "global.dashboard.nested.dummy": True,
                    "user.test": 1,
                }
            },
            "drb",
            HTTPStatus.OK,
        )
        assert response.json == {
            "errors": {
                "global.dashboard.nested.dummy": "Key 'nested' value for "
                "'global.dashboard.nested.dummy' "
                "in (drb)|drb is not a JSON object"
            },
            "metadata": {
                "global.dashboard.nested.dummy": None,
                "global.dashboard.seen": False,
                "user.test": 1,
            },
        }
        response = query_get_as(
            "drb", {"metadata": "global,user"}, "drb", HTTPStatus.OK
        )
        assert response.json == {
            "global": {
                "contact": "me@example.com",
                "dashboard": {"seen": False, "nested": False},
            },
            "user": {"test": 1},
        }

    def test_put(self, query_get_as, query_put_as):
        response = query_put_as(
            "drb",
            {"metadata": {"global.seen": False, "global.under-score_hyphen": True}},
            "drb",
            HTTPStatus.OK,
        )
        assert response.json == {
            "metadata": {"global.under-score_hyphen": True, "global.seen": False},
            "errors": {},
        }
        response = query_get_as(
            "drb", {"metadata": "global,dataset.access"}, "drb", HTTPStatus.OK
        )
        assert response.json == {
            "global": {
                "contact": "me@example.com",
                "under-score_hyphen": True,
                "seen": False,
            },
            "dataset.access": "private",
        }

        # Try a second GET, returning "global" fields separately:
        response = query_get_as(
            "drb",
            {
                "metadata": [
                    "global.seen",
                    "global.under-score_hyphen",
                    "dataset.access",
                ]
            },
            "drb",
            HTTPStatus.OK,
        )
        assert response.json == {
            "global.under-score_hyphen": True,
            "global.seen": False,
            "dataset.access": "private",
        }
        audit = Audit.query()
        assert len(audit) == 2
        assert audit[0].id == 1
        assert audit[0].root_id is None
        assert audit[0].operation == OperationCode.UPDATE
        assert audit[0].status == AuditStatus.BEGIN
        assert audit[0].name == "metadata"
        assert audit[0].object_type == AuditType.DATASET
        assert audit[0].object_id == "random_md5_string1"
        assert audit[0].object_name == "drb"
        assert audit[0].user_id == "3"
        assert audit[0].user_name == "drb"
        assert audit[0].reason is None
        assert audit[0].attributes is None
        assert audit[1].id == 2
        assert audit[1].root_id == 1
        assert audit[1].operation == OperationCode.UPDATE
        assert audit[1].status == AuditStatus.SUCCESS
        assert audit[1].name == "metadata"
        assert audit[1].object_type == AuditType.DATASET
        assert audit[1].object_id == "random_md5_string1"
        assert audit[1].object_name == "drb"
        assert audit[1].user_id == "3"
        assert audit[1].user_name == "drb"
        assert audit[1].reason is None
        assert audit[1].attributes == {
            "updated": {"global.seen": False, "global.under-score_hyphen": True}
        }

    def test_put_user(self, query_get_as, query_put_as):
        response = query_put_as(
            "fio_1",
            {"metadata": {"user.favorite": True, "user.tag": "AWS"}},
            "drb",
            HTTPStatus.OK,
        )
        assert response.json == {
            "metadata": {"user.favorite": True, "user.tag": "AWS"},
            "errors": {},
        }
        audit = Audit.query()
        assert len(audit) == 2
        assert audit[0].id == 1
        assert audit[0].root_id is None
        assert audit[0].operation == OperationCode.UPDATE
        assert audit[0].status == AuditStatus.BEGIN
        assert audit[0].name == "metadata"
        assert audit[0].object_type == AuditType.DATASET
        assert audit[0].object_id == "random_md5_string3"
        assert audit[0].object_name == "fio_1"
        assert audit[0].user_id == "3"
        assert audit[0].user_name == "drb"
        assert audit[0].reason is None
        assert audit[0].attributes is None
        assert audit[1].id == 2
        assert audit[1].root_id == 1
        assert audit[1].operation == OperationCode.UPDATE
        assert audit[1].status == AuditStatus.SUCCESS
        assert audit[1].name == "metadata"
        assert audit[1].object_type == AuditType.DATASET
        assert audit[1].object_id == "random_md5_string3"
        assert audit[1].object_name == "fio_1"
        assert audit[1].user_id == "3"
        assert audit[1].user_name == "drb"
        assert audit[1].reason is None
        assert audit[1].attributes == {
            "updated": {"user.favorite": True, "user.tag": "AWS"}
        }

        response = query_put_as(
            "fio_1",
            {"metadata": {"user.favorite": False, "user.tag": "RHEL"}},
            "test",
            HTTPStatus.OK,
        )
        assert response.json == {
            "metadata": {"user.favorite": False, "user.tag": "RHEL"},
            "errors": {},
        }
        response = query_put_as(
            "fio_1",
            {"metadata": {"user.favorite": False, "user.tag": "BAD"}},
            None,
            HTTPStatus.UNAUTHORIZED,
        )

        response = query_get_as("fio_1", {"metadata": "user"}, "drb", HTTPStatus.OK)
        assert response.json == {"user": {"favorite": True, "tag": "AWS"}}
        response = query_get_as("fio_1", {"metadata": "user"}, "test", HTTPStatus.OK)
        assert response.json == {"user": {"favorite": False, "tag": "RHEL"}}
        response = query_get_as("fio_1", {"metadata": "user"}, None, HTTPStatus.OK)
        assert response.json == {"user": None}
