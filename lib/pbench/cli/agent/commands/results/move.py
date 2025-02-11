import os
import shutil
import socket
import tempfile
from typing import List

import click

from pbench.agent.base import BaseCommand
from pbench.agent.results import CopyResult, MakeResultTb
from pbench.cli import CliContext, pass_cli_context, sort_click_command_parameters
from pbench.cli.agent.commands.results.results_options import results_common_options
from pbench.cli.agent.options import common_options
from pbench.common.exceptions import BadMDLogFormat
from pbench.common.utils import validate_hostname


class MoveResults(BaseCommand):
    """Command implementation for "pbench results move."

    This command replaces the previous (legacy) interface,
    `pbench-move-results`, and its sibling, `pbench-copy-results`, with no
    attempt to implement any backwards compatibility with that legacy
    interface.

    This command is responsible for finding all the existing pbench data
    directories on the local host (controller), packaging each of them up as a
    tar ball, and sending it to the remote pbench server.
    """

    def __init__(self, context: CliContext):
        super().__init__(context)

    def execute(self, single_threaded: bool, delete: bool = True) -> int:
        runs_copied = 0
        failures = 0
        no_of_tb = 0
        crt = CopyResult.cli_create(self.context, self.config, self.logger)

        with tempfile.TemporaryDirectory(
            dir=self.config.pbench_tmp, prefix="pbench-results-move."
        ) as temp_dir:
            for dirent in self.config.pbench_run.iterdir():
                if not dirent.is_dir():
                    continue
                if dirent.name.startswith("tools-") or dirent.name == "tmp":
                    continue

                no_of_tb += 1
                result_dir = dirent

                try:
                    mrt = MakeResultTb(
                        str(result_dir),
                        temp_dir,
                        self.context.controller,
                        self.config,
                        self.logger,
                    )
                except MakeResultTb.AlreadyCopied:
                    self.logger.info(f"Already copied {result_dir}")
                    continue
                except MakeResultTb.BenchmarkRunning:
                    self.logger.warning(
                        f"Skipping {result_dir}: the benchmark appears to be"
                        " running.  If that's incorrect, remove the"
                        f" {result_dir}/.running directory and try again"
                    )
                    continue
                except (NotADirectoryError, FileNotFoundError) as exc:
                    self.logger.error(str(exc))
                    failures += 1
                    continue

                try:
                    result_tb_name, _, result_tb_md5 = mrt.make_result_tb(
                        single_threaded=single_threaded
                    )
                except BadMDLogFormat as exc:
                    self.logger.warning(str(exc))
                    failures += 1
                    continue
                except FileNotFoundError as exc:
                    self.logger.error(str(exc))
                    failures += 1
                    continue
                except RuntimeError as exc:
                    self.logger.warning("Error encountered making tar ball, '%s'", exc)
                    failures += 1
                    continue
                except Exception as exc:
                    self.logger.error(
                        "Unexpected error occurred making tar ball for '%s', '%s'",
                        result_dir,
                        exc,
                    )
                    failures += 1
                    continue

                try:
                    res = crt.push(result_tb_name, result_tb_md5)
                    if not res.ok:
                        try:
                            msg = res.json()["message"]
                        except Exception:
                            msg = res.text if res.text else res.reason
                        raise CopyResult.FileUploadError(msg)
                    if self.context.relay:
                        click.echo(f"RELAY {result_tb_name.name}: {res.url}")
                except Exception as exc:
                    if isinstance(exc, (CopyResult.FileUploadError, RuntimeError)):
                        msg = "Error uploading file"
                    else:
                        msg = "Unexpected error occurred copying tar ball remotely"
                    self.logger.error("%s, '%s', %s", msg, result_tb_name, exc)
                    failures += 1
                    # We don't know why this operation failed; regardless,
                    # trying to copy another tar ball remotely does not have
                    # much chance of success.
                    break
                else:
                    runs_copied += 1
                finally:
                    try:
                        # We always remove the constructed tar ball, regardless of success
                        # or failure, since we keep the result directory below on failure.
                        os.remove(result_tb_name)
                    except OSError as exc:
                        self.logger.error(
                            "Failed to remove '%s', '%s'", result_tb_name, exc
                        )

                if delete:
                    try:
                        shutil.rmtree(result_dir)
                    except OSError:
                        self.logger.error(
                            "Failed to remove the %s directory hierarchy", result_dir
                        )
                        failures += 1
                        # If we can't hold up the contract of removing the
                        # local directory tree that was copied, we exit the
                        # loop that is processing result directories.  Not
                        # being able to remove the local directory tree will
                        # usually indicate a serious problem that needs to be
                        # resolved before doing anything else.
                        break
                else:
                    copied = result_dir.parent / f"{result_dir.name}.copied"
                    try:
                        copied.touch()
                    except OSError as exc:
                        self.logger.error(
                            "Failed to create '.copied' file marker for '%s', '%s'",
                            result_dir,
                            exc,
                        )
                        failures += 1
                        # If we can't hold up the contract of marking a
                        # directory as copied remotely, we exit the loop that
                        # is processing result directories.  If we can't
                        # create an empty file on the file system where the
                        # result directory lives, it likely indicates bigger
                        # problems.
                        break

        action = "moved" if delete else "copied"
        click.echo(
            f"Status: total # of result directories considered {no_of_tb:d},"
            f" successfully {action} {runs_copied:d}, encountered"
            f" {failures:d} failures"
        )

        return 0 if failures == 0 else 1


@sort_click_command_parameters
@click.command(name="pbench-results-move")
@common_options
@results_common_options
@click.option(
    "--controller",
    required=False,
    envvar="PBENCH_CONTROLLER",
    default="",
    prompt=False,
    help="Override the default controller name",
)
@click.option(
    "--delete/--no-delete",
    default=True,
    show_default=True,
    help="Remove local data after successful copy",
)
@click.option(
    "--xz-single-threaded",
    is_flag=True,
    help="Use single threaded compression with 'xz'",
)
@pass_cli_context
def main(
    context: CliContext,
    controller: str,
    access: str,
    token: str,
    delete: bool,
    metadata: List,
    xz_single_threaded: bool,
    server: str,
    relay: str,
):
    """Move result directories to the configured Pbench server."""
    clk_ctx = click.get_current_context()

    if controller:
        context.controller = controller
    else:
        controller = os.environ.get("_pbench_full_hostname", socket.getfqdn())
        if not controller:
            click.echo(
                "Unable to determine the controller name, could not fetch the"
                " FQDN of the host; to work around this problem consider"
                " explicitly providing a value for the --controller option",
                err=True,
            )
            clk_ctx.exit(1)

    if relay and server:
        click.echo("Cannot use both relay and Pbench Server destination.", err=True)
        clk_ctx.exit(2)

    if validate_hostname(controller) != 0:
        # We check once to avoid having to deal with a bad controller each
        # time we try to copy the results.
        click.echo(f"Controller, {controller!r}, is not a valid host name")
        clk_ctx.exit(1)

    context.controller = controller
    context.access = access
    context.token = token
    context.metadata = metadata
    context.server = server
    context.relay = relay

    try:
        rv = MoveResults(context).execute(xz_single_threaded, delete=delete)
    except Exception as exc:
        click.echo(exc, err=True)
        rv = 1

    clk_ctx.exit(rv)
