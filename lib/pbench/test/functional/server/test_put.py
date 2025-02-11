from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
import os.path
from pathlib import Path
import re
import time

import dateutil.parser
import pytest
from requests.exceptions import HTTPError

from pbench.client import API, PbenchServerClient
from pbench.client.types import Dataset

TARBALL_DIR = Path("lib/pbench/test/functional/server/tarballs")
SPECIAL_DIR = TARBALL_DIR / "special"
SHORT_EXPIRATION_DAYS = 10


def utc_from_str(date: str) -> datetime:
    return dateutil.parser.parse(date).replace(tzinfo=timezone.utc)


@dataclass
class Tarball:
    """Record the tarball path and the uploaded access value"""

    path: Path
    access: str


class TestPut:
    """Test success and failure cases of PUT dataset upload"""

    @pytest.mark.dependency(name="upload", scope="session")
    def test_upload_all(self, server_client: PbenchServerClient, login_user):
        """Upload each of the pregenerated tarballs, and perform some basic
        sanity checks on the resulting server state.
        """
        print(" ... uploading tarballs ...")

        tarballs: dict[str, Tarball] = {}
        access = ["private", "public"]
        cur_access = 0

        # We're going to make some datasets expire "soon" (much sooner than the
        # default) so we can test filtering typed metadata.
        expire_soon = datetime.now(timezone.utc) + timedelta(days=SHORT_EXPIRATION_DAYS)

        for t in TARBALL_DIR.glob("*.tar.xz"):
            a = access[cur_access]
            if a == "public":
                metadata = (
                    "server.origin:test,user.pbench.access:public,server.archiveonly:n",
                    f"server.deletion:{expire_soon:%Y-%m-%d %H:%M%z}",
                )
            else:
                metadata = None

            cur_access = 0 if cur_access else 1
            tarballs[Dataset.stem(t)] = Tarball(t, a)
            response = server_client.upload(t, access=a, metadata=metadata)
            assert (
                response.status_code == HTTPStatus.CREATED
            ), f"upload returned unexpected status {response.status_code}, {response.text} ({t})"
            print(f"\t... uploaded {t.name}: {a}")

        datasets = server_client.get_list(
            metadata=["dataset.access", "server.tarball-path", "dataset.operations"]
        )
        found = frozenset({d.name for d in datasets})
        expected = frozenset(tarballs.keys())
        assert expected.issubset(found), f"expected {expected!r}, found {found!r}"
        try:
            for dataset in datasets:
                if dataset.name not in expected:
                    continue
                t = tarballs[dataset.name]
                assert dataset.name in dataset.metadata["server.tarball-path"]
                assert dataset.metadata["dataset.operations"]["UPLOAD"]["state"] == "OK"
                assert t.access == dataset.metadata["dataset.access"]
        except HTTPError as exc:
            pytest.fail(
                f"Unexpected HTTP error, url = {exc.response.url}, status"
                f" code = {exc.response.status_code}, text = {exc.response.text!r}"
            )

    @pytest.mark.dependency(depends=["upload"], scope="session")
    def test_upload_again(self, server_client: PbenchServerClient, login_user):
        """Try to upload a dataset we've already uploaded. This should succeed
        but with an OK (200) response instead of CREATED (201)
        """
        duplicate = next(iter(TARBALL_DIR.glob("*.tar.xz")))
        response = server_client.upload(duplicate)
        assert (
            response.status_code == HTTPStatus.OK
        ), f"upload returned unexpected status {response.status_code}, {response.text}"

    @staticmethod
    def test_bad_md5(server_client: PbenchServerClient, login_user):
        """Try to upload a new dataset with a bad MD5 value. This should fail."""
        duplicate = next(iter(TARBALL_DIR.glob("*.tar.xz")))
        response = server_client.upload(
            duplicate, md5="this isn't the md5 you're looking for"
        )
        assert (
            response.status_code == HTTPStatus.BAD_REQUEST
        ), f"upload returned unexpected status {response.status_code}, {response.text}"
        assert re.match(
            r"MD5 checksum \w+ does not match expected", response.json()["message"]
        )

    @staticmethod
    def test_bad_name(server_client: PbenchServerClient, login_user):
        """Try to upload a new dataset with a bad filename. This should fail."""
        duplicate = next(iter(TARBALL_DIR.glob("*.tar.xz")))
        response = server_client.upload(duplicate, filename="notme")
        assert (
            response.status_code == HTTPStatus.BAD_REQUEST
        ), f"upload returned unexpected status {response.status_code}, {response.text}"
        assert (
            response.json()["message"]
            == "File extension not supported, must be .tar.xz"
        )

    @staticmethod
    def test_archive_only(server_client: PbenchServerClient, login_user):
        """Test `server.archiveonly`

        Try to upload a new dataset with the archiveonly option set, and
        validate that it doesn't get enabled for unpacking or indexing.
        """
        tarball = SPECIAL_DIR / "fio_mock_2020.01.19T00.18.06.tar.xz"
        md5 = Dataset.md5(tarball)
        response = server_client.upload(tarball, metadata={"server.archiveonly:y"})
        assert (
            response.status_code == HTTPStatus.CREATED
        ), f"upload {Dataset.stem(tarball)} returned unexpected status {response.status_code}, {response.text}"
        metadata = server_client.get_metadata(
            md5, ["dataset.operations", "server.archiveonly"]
        )
        assert metadata["server.archiveonly"] is True

        # NOTE: we could wait here; however, the UNPACK operation is only
        # enabled by upload, and INDEX is only enabled by UNPACK: so if they're
        # not here immediately after upload, they'll never be here.
        operations = metadata["dataset.operations"]
        assert operations["UPLOAD"]["state"] == "OK"
        assert "INDEX" not in operations

        # Delete it so we can run the test case again without manual cleanup
        response = server_client.remove(md5)
        assert (
            response.ok
        ), f"delete failed with {response.status_code}, {response.text}"

    @staticmethod
    def test_no_metadata(server_client: PbenchServerClient, login_user):
        """Test handling for a tarball without a metadata.log.

        Try to upload a new tarball with no `metadata.log` file, and
        validate that it doesn't get enabled for unpacking or indexing.
        """
        tarball = SPECIAL_DIR / "nometadata.tar.xz"
        md5 = Dataset.md5(tarball)
        response = server_client.upload(tarball)
        assert (
            response.status_code == HTTPStatus.CREATED
        ), f"upload {Dataset.stem(tarball)} returned unexpected status {response.status_code}, {response.text}"
        metadata = server_client.get_metadata(
            md5, ["dataset.operations", "dataset.metalog", "server.archiveonly"]
        )
        assert metadata["dataset.metalog"] == {"pbench": {"script": "Foreign"}}
        assert metadata["server.archiveonly"] is True

        # NOTE: we could wait here; however, the UNPACK operation is only
        # enabled by upload, and INDEX is only enabled by UNPACK: so if they're
        # not here immediately after upload, they'll never be here.
        operations = metadata["dataset.operations"]
        assert operations["UPLOAD"]["state"] == "OK"
        assert "INDEX" not in operations

        # Delete it so we can run the test case again without manual cleanup
        response = server_client.remove(md5)
        assert (
            response.ok
        ), f"delete failed with {response.status_code}, {response.text}"

    @staticmethod
    def check_indexed(server_client: PbenchServerClient, datasets):
        indexed = []
        not_indexed = []
        try:
            for dataset in datasets:
                print(f"\t... on {dataset.name}")
                metadata = server_client.get_metadata(
                    dataset.resource_id, ["dataset.operations"]
                )
                operations = metadata["dataset.operations"]
                if "INDEX" in operations and operations["INDEX"]["state"] in (
                    "FAILED",
                    "OK",
                ):
                    assert operations["INDEX"]["state"] == "OK"
                    indexed.append(dataset)
                else:
                    done = ",".join(
                        name for name, op in operations.items() if op["state"] == "OK"
                    )
                    undone = []
                    for name, op in operations.items():
                        if op["state"] != "OK":
                            undone.append(f"{name}={op['state']}(msg={op['message']})")
                    status = ",".join(undone)
                    print(f"\t\tfinished {done!r}, awaiting {status!r}")
                    not_indexed.append(dataset)
        except HTTPError as exc:
            pytest.fail(
                f"Unexpected HTTP error, url = {exc.response.url}, status code"
                f" = {exc.response.status_code}, text = {exc.response.text!r}"
            )
        return not_indexed, indexed

    @pytest.mark.dependency(name="index", depends=["upload"], scope="session")
    def test_index_all(self, server_client: PbenchServerClient, login_user):
        """Wait for datasets to reach the "Indexed" state, and ensure that the
        state and metadata look good.
        """
        tarball_names = frozenset(t.name for t in TARBALL_DIR.glob("*.tar.xz"))
        print(" ... reporting dataset status ...")

        # Test get_list pagination: to avoid forcing a list, we'll count the
        # iterations separately. (Note that this is really an implicit test
        # of the paginated datasets/list API and the get_list generator, which
        # one could argue belong in a separate test case; I'll likely refactor
        # this later when I add GET tests.)
        count = 0
        not_indexed_raw = server_client.get_list(
            limit=5,
            metadata=[
                "server.tarball-path",
                "dataset.access",
                "server.archiveonly",
                "server.origin",
                "server.deletion",
                "user.pbench.access",
            ],
        )
        not_indexed = []
        try:
            for dataset in not_indexed_raw:
                tp = dataset.metadata["server.tarball-path"]
                if os.path.basename(tp) not in tarball_names:
                    continue
                not_indexed.append(dataset)
                if dataset.metadata["user.pbench.access"] == "public":
                    assert dataset.metadata["server.origin"] == "test"
                    assert dataset.metadata["dataset.access"] == "public"
                    assert dataset.metadata["server.archiveonly"] is False
                else:
                    assert dataset.metadata["dataset.access"] == "private"
                    assert dataset.metadata["server.origin"] is None
                    assert dataset.metadata["server.archiveonly"] is None
                    assert dataset.metadata["user.pbench.access"] is None
        except HTTPError as exc:
            pytest.fail(
                f"Unexpected HTTP error, url = {exc.response.url}, status code"
                f" = {exc.response.status_code}, text = {exc.response.text!r}"
            )

        # For each dataset we find, poll the state until it has been indexed,
        # or until we time out. The indexer runs once a minute slightly after
        # the minute, so we make our 1st check 45 seconds into the next minute,
        # and then check at 45 seconds past the minute until we reach 5 minutes
        # past the original start time.
        oneminute = timedelta(minutes=1)
        now = start = datetime.utcnow()
        timeout = start + timedelta(minutes=5)
        target_int = (
            datetime(now.year, now.month, now.day, now.hour, now.minute)
            + oneminute
            + timedelta(seconds=45)
        )

        while not_indexed:
            print(f"[{(now - start).total_seconds():0.2f}] Checking ...")
            not_indexed, indexed = TestPut.check_indexed(server_client, not_indexed)
            for dataset in indexed:
                tp = dataset.metadata["server.tarball-path"]
                if os.path.basename(tp) not in tarball_names:
                    continue
                count += 1
                print(f"\t... indexed {dataset.name}")
            now = datetime.utcnow()
            if not not_indexed or now >= timeout:
                break
            time.sleep((target_int - now).total_seconds())
            target_int += oneminute
            now = datetime.utcnow()
        assert not not_indexed, (
            f"Timed out after {(now - start).total_seconds()} seconds; unindexed datasets: "
            + ", ".join(d.name for d in not_indexed)
        )
        assert (
            len(tarball_names) == count
        ), f"Didn't find all expected datasets, found {count} of {len(tarball_names)}"


class TestIndexing:
    @pytest.mark.dependency(name="detail", depends=["index"], scope="session")
    def test_details(self, server_client: PbenchServerClient, login_user):
        """Check access to indexed data

        Perform a GET /datasets/details/{id} to be sure that basic run data
        has been indexed and is available.
        """
        print(" ... checking dataset RUN index ...")
        datasets = server_client.get_list(
            metadata=["dataset.metalog.pbench,server.archiveonly"], owner="tester"
        )
        for d in datasets:
            print(f"\t... checking run index for {d.name}")
            response = server_client.get(
                API.DATASETS_DETAIL, {"dataset": d.resource_id}
            )
            detail = response.json()
            indexed = not d.metadata["server.archiveonly"]
            if indexed:
                assert (
                    d.metadata["dataset.metalog.pbench"]["script"]
                    == detail["runMetadata"]["script"]
                )
            else:
                print(f"\t\t... {d.name} is archiveonly")


class TestList:
    @pytest.mark.dependency(name="list_none", depends=["upload"], scope="session")
    def test_list_anonymous(self, server_client: PbenchServerClient):
        """List all datasets without a login.

        We should see only published datasets. We don't care whether there are
        pre-existing datasets in this case: we'll simply confirm that every one
        we see is public. We do care that we don't get an empty list, since we
        uploaded datasets with access public.
        """
        datasets = server_client.get_list(metadata=["dataset.access"])
        count = 0

        for dataset in datasets:
            assert dataset.metadata["dataset.access"] == "public"
            count += 1

        assert count > 1

    @pytest.mark.dependency(name="list_api_key", depends=["upload"], scope="session")
    def test_list_api_key(self, server_client: PbenchServerClient, login_user):
        """List "my" datasets using an API key.

        We should see all datasets owned by the tester account, both private
        and public. That is, using the API key is the same as using the normal
        auth token.
        """
        server_client.create_api_key()
        assert server_client.api_key, "No API key was set on the session"
        datasets = server_client.get_list(mine="true")

        expected = [
            {"resource_id": Dataset.md5(f), "name": Dataset.stem(f), "metadata": {}}
            for f in TARBALL_DIR.glob("*.tar.xz")
        ]
        expected.sort(key=lambda e: e["resource_id"])
        actual = [d.json for d in datasets]
        assert expected == actual
        server_client.remove_api_key()
        assert not server_client.api_key, "API key was not removed as expected"

    @pytest.mark.dependency(name="list_or", depends=["upload"], scope="session")
    def test_list_filter_or(self, server_client: PbenchServerClient, login_user):
        """Check a simple OR filter list.

        Authorized as our "tester" user, we can see all the datasets we've
        uploaded. Try a filtered list choosing datasets run with the "fio"
        script OR the "linpack" script. Only those datasets should appear: we
        check the list against a glob of our upload source directory.
        """
        fio_names = {Dataset.stem(t) for t in TARBALL_DIR.glob("*fio*.tar.xz")}
        linpack_names = {Dataset.stem(t) for t in TARBALL_DIR.glob("*linpack*.tar.xz")}
        expected = fio_names | linpack_names
        datasets = server_client.get_list(
            metadata=["dataset.metalog.pbench.name"],
            owner="tester",
            filter=[
                "^dataset.metalog.pbench.script:fio",
                "^dataset.metalog.pbench.script:linpack",
            ],
        )

        actual = set(d.metadata["dataset.metalog.pbench.name"] for d in datasets)
        assert actual >= expected, f"Missing datasets: {expected - actual}"

    @pytest.mark.dependency(name="list_and", depends=["upload"], scope="session")
    def test_list_filter_and(self, server_client: PbenchServerClient, login_user):
        """Check a simple AND filter list.

        Authorized as our "tester" user, we can see all the datasets we've
        uploaded. Try a filtered list choosing datasets which are public AND
        were created in 2018.

        NOTE: the original "owner", "access", "start", "end", and "name"
        filters are supported and implicitly linked as AND; their matching is
        also more "friendly" in some cases, e.g., being case-insensitive. In
        this case we're using "dataset.access".
        """
        datasets = server_client.get_list(
            metadata=["dataset.metalog.pbench.date", "dataset.access"],
            owner="tester",
            filter=[
                "dataset.metalog.pbench.date:~2018",
                "dataset.access:public",
            ],
        )

        for dataset in datasets:
            date = dataset.metadata["dataset.metalog.pbench.date"]
            access = dataset.metadata["dataset.access"]
            assert access == "public", f"Dataset {dataset.name} access is {access}"
            assert "2018" in date, f"Dataset {dataset.name} date is {date}"

    @pytest.mark.dependency(name="list_all", depends=["upload"], scope="session")
    def test_list_filter_and_or(self, server_client: PbenchServerClient, login_user):
        """Check a simple AND-OR filter list.

        Authorized as our "tester" user, we can see all the datasets we've
        uploaded. Try a filtered list choosing datasets which are public AND
        created in either 2018 or 2019.
        """
        datasets = server_client.get_list(
            metadata=["dataset.metalog.pbench.date", "dataset.access"],
            owner="tester",
            filter=[
                "dataset.access:public",
                "^dataset.metalog.pbench.date:~2018",
                "^dataset.metalog.pbench.date:~2019",
            ],
        )

        for dataset in datasets:
            date = dataset.metadata["dataset.metalog.pbench.date"]
            access = dataset.metadata["dataset.access"]
            assert access == "public", f"Dataset {dataset.name} access is {access}"
            assert (
                "2018" in date or "2019" in date
            ), f"Dataset {dataset.name} date is {date}"

    @pytest.mark.dependency(name="list_type", depends=["upload"], scope="session")
    def test_list_filter_typed(self, server_client: PbenchServerClient, login_user):
        """Test filtering using typed matches.

        We set an early "server.deletion" time on alternating datasets as we
        uploaded them. Now prove that we can use a typed "date" filter to find
        them. We'll further validate that none of the other datasets we
        uploaded from TARBALL_DIR should have been returned.
        """
        test_sets = {}
        for t in TARBALL_DIR.glob("*.tar.xz"):
            r = Dataset.md5(t)
            m = server_client.get_metadata(
                r,
                ["dataset.name", "server.deletion"],
            )
            test_sets[r] = m
        soonish = datetime.now(timezone.utc) + timedelta(days=SHORT_EXPIRATION_DAYS * 2)

        datasets = server_client.get_list(
            metadata=["server.deletion"],
            owner="tester",
            # NOTE: using weird "US standard" date notation here minimizes
            # the risk of succeeding via a simple alphanumeric comparison.
            filter=[f"server.deletion:<'{soonish:%m/%d/%Y %H:%M%z}':date"],
        )

        # Confirm that the returned datasets match
        for dataset in datasets:
            deletion = utc_from_str(dataset.metadata["server.deletion"])
            assert (
                deletion < soonish
            ), f"Filter returned {dataset.name}, with expiration out of range ({deletion:%Y-%m-%d})"
            test_sets.pop(dataset.resource_id, None)

        # Confirm that the remaining TARBALL_DIR datasets don't match
        for r, m in test_sets.items():
            deletion = utc_from_str(m["server.deletion"])
            assert (
                deletion >= soonish
            ), f"Filter failed to return {m['dataset.name']}, with expiration in range ({deletion:%Y-%m-%d})"


class TestUpdate:
    @pytest.mark.dependency(name="publish", depends=["index"], scope="session")
    @pytest.mark.parametrize("access", ("public", "private"))
    def test_publish(self, server_client: PbenchServerClient, login_user, access):
        expected = "public" if access == "private" else "private"
        datasets = server_client.get_list(access=access, mine="true")
        print(f" ... updating {access} datasets to {expected} ...")
        for dataset in datasets:
            server_client.update(dataset.resource_id, access=expected)
            print(f"\t ... updating {dataset.name} to {access!r}")
            meta = server_client.get_metadata(
                dataset.resource_id, metadata="dataset.access"
            )
            assert meta["dataset.access"] == expected


class TestDelete:
    @pytest.mark.dependency(
        depends=[
            "detail",
            "index",
            "list_all",
            "list_and",
            "list_none",
            "list_or",
            "list_type",
            "publish",
        ],
        scope="session",
    )
    def test_delete_all(self, server_client: PbenchServerClient, login_user):
        """Verify we can delete each previously uploaded dataset.

        Requires that test_upload_all has been run successfully.
        """
        if os.environ.get("KEEP_DATASETS"):
            pytest.skip(reason="Skipping dataset deletion on request")

        print(" ... reporting behaviors ...")

        datasets = server_client.get_list()
        datasets_hash = {}
        try:
            for dataset in datasets:
                datasets_hash[f"{dataset.name}.tar.xz"] = dataset.resource_id
        except HTTPError as exc:
            pytest.fail(
                f"Unexpected HTTP error, url = {exc.response.url}, status code"
                f" = {exc.response.status_code}, text = {exc.response.text!r}"
            )
        for t in TARBALL_DIR.glob("*.tar.xz"):
            resource_id = datasets_hash.get(t.name)
            assert resource_id, f"Expected to find tar ball {t.name} to delete"
            response = server_client.remove(resource_id)
            assert (
                response.ok
            ), f"delete failed with {response.status_code}, {response.text}"
            print(f"\t ... deleted {t.name}")
