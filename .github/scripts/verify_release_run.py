#!/usr/bin/env python3
"""Fail-closed verification for the exact GitHub Actions runs used by a release."""

import argparse
import json
import sys


class VerificationError(ValueError):
    """The supplied Actions evidence does not satisfy the release contract."""


def _positive_id(item, kind):
    value = item.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise VerificationError("{} has an invalid id".format(kind))
    return value


def select_successful_run(payload, release_tag, tag_commit, event, workflow_path):
    """Return the newest successful run matching every immutable release field."""
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise VerificationError("workflow run response is malformed")
    matches = []
    for run in runs:
        if not isinstance(run, dict):
            raise VerificationError("workflow run response contains a malformed item")
        if (
            run.get("head_sha") == tag_commit
            and run.get("head_branch") == release_tag
            and run.get("event") == event
            and run.get("path") == workflow_path
        ):
            _positive_id(run, "workflow run")
            matches.append(run)
    if not matches:
        raise VerificationError("missing exact release workflow run")
    latest = max(matches, key=lambda run: _positive_id(run, "workflow run"))
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise VerificationError("latest exact release workflow run is not successful")
    return latest["id"]


def verify_required_jobs(payload, required_names):
    """Require the newest instance of every named job to be completed successfully."""
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise VerificationError("workflow jobs response is malformed")
    required = tuple(required_names)
    if not required or len(required) != len(set(required)):
        raise VerificationError("required job names must be nonempty and unique")
    latest = {}
    for job in jobs:
        if not isinstance(job, dict):
            raise VerificationError("workflow jobs response contains a malformed item")
        name = job.get("name")
        if name not in required:
            continue
        job_id = _positive_id(job, "workflow job")
        if job_id > latest.get(name, {}).get("id", 0):
            latest[name] = job
    missing = sorted(set(required) - set(latest))
    failed = sorted(
        name
        for name, job in latest.items()
        if job.get("status") != "completed" or job.get("conclusion") != "success"
    )
    if missing or failed:
        raise VerificationError(
            "release workflow jobs invalid: missing={!r}, failed={!r}".format(
                missing, failed
            )
        )


def _parser():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select-run")
    select.add_argument("--release-tag", required=True)
    select.add_argument("--tag-commit", required=True)
    select.add_argument("--event", required=True)
    select.add_argument("--workflow-path", required=True)
    jobs = commands.add_parser("verify-jobs")
    jobs.add_argument("--required", action="append", required=True)
    return parser


def main():
    args = _parser().parse_args()
    try:
        payload = json.load(sys.stdin)
        if args.command == "select-run":
            print(
                select_successful_run(
                    payload,
                    args.release_tag,
                    args.tag_commit,
                    args.event,
                    args.workflow_path,
                )
            )
        else:
            verify_required_jobs(payload, args.required)
    except (VerificationError, json.JSONDecodeError) as exc:
        print("release evidence rejected: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
