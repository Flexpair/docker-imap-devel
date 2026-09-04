#!/usr/bin/env python3
"""Smoke tests for the Dockerized IMAP/SMTP development image."""

from __future__ import annotations

import imaplib
import os
import re
import shutil
import smtplib
import ssl
import subprocess
import time
import unittest
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("IMAGE", "docker-imap-devel:test")
CONTAINER = os.environ.get("CONTAINER", f"docker-imap-devel-test-{os.getpid()}")
MAILNAME = "localdomain.test"
TEST_ADDRESS = f"test@{MAILNAME}"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a Docker command and return its completed process."""
    return subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def published_port(container_port: int) -> int:
    """Return the host port published for a container TCP port."""
    result = docker("port", CONTAINER, f"{container_port}/tcp")
    match = re.search(r":(\d+)\s*$", result.stdout.splitlines()[0])
    if match is None:
        raise AssertionError(f"Could not determine published port: {result.stdout}")
    return int(match.group(1))


class RepositoryPolicyTest(unittest.TestCase):
    """Prevent regressions in the static fixes covered by SonarCloud."""

    def test_workflow_actions_use_full_commit_shas(self) -> None:
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        references = re.findall(r"^\s*- uses:\s*([^\s#]+)", workflow, re.MULTILINE)

        self.assertGreater(len(references), 0)
        self.assertTrue(
            all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference) for reference in references),
            references,
        )

    def test_dockerfile_uses_current_directives(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text()

        self.assertNotRegex(dockerfile, r"(?m)^\s*MAINTAINER\b")
        self.assertNotRegex(dockerfile, r"(?m)^\s*ADD\b")
        self.assertRegex(dockerfile, r"(?m)^\s*LABEL\s+org\.opencontainers\.image\.authors=")
        self.assertRegex(dockerfile, r"(?m)^\s*COPY\s+postfix\s+/etc/postfix\s*$")


class DockerImageSmokeTest(unittest.TestCase):
    """Exercise the image's actual SMTP, IMAP, and service startup paths."""

    image_was_built = False
    smtp_port = 0
    imap_port = 0

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("docker") is None:
            raise unittest.SkipTest("Docker is required for the image smoke tests")

        docker("rm", "--force", "--volumes", CONTAINER, check=False)
        image_exists = docker("image", "inspect", IMAGE, check=False).returncode == 0
        if not image_exists:
            docker("build", "--tag", IMAGE, ".")
            cls.image_was_built = True

        docker(
            "run",
            "--detach",
            "--name",
            CONTAINER,
            "--publish",
            "0:25",
            "--publish",
            "0:993",
            "--env",
            f"MAILNAME={MAILNAME}",
            "--env",
            f"MAIL_ADDRESS={TEST_ADDRESS}",
            "--env",
            "MAIL_PASS=test-password",
            IMAGE,
        )
        cls.smtp_port = published_port(25)
        cls.imap_port = published_port(993)
        cls._wait_for_services()

    @classmethod
    def tearDownClass(cls) -> None:
        docker("rm", "--force", "--volumes", CONTAINER, check=False)
        if cls.image_was_built:
            docker("image", "rm", IMAGE, check=False)

    @classmethod
    def _wait_for_services(cls) -> None:
        last_output = ""
        for _ in range(30):
            result = docker(
                "exec",
                CONTAINER,
                "sh",
                "-c",
                "postfix check && doveconf -n >/dev/null",
                check=False,
            )
            last_output = result.stdout
            if result.returncode == 0:
                return
            time.sleep(1)
        logs = docker("logs", CONTAINER, check=False).stdout
        raise AssertionError(f"Services did not become ready.\n{last_output}\n{logs}")

    def _exec(self, *args: str) -> subprocess.CompletedProcess[str]:
        return docker("exec", CONTAINER, *args)

    def test_container_is_running_with_configured_accounts(self) -> None:
        state = docker("inspect", "--format", "{{.State.Status}}", CONTAINER).stdout.strip()
        self.assertEqual(state, "running")

        for account in (f"debug@{MAILNAME}", TEST_ADDRESS):
            self._exec("grep", "-Fq", account, "/etc/dovecot/userdb")
            self._exec("grep", "-Fq", account, "/etc/postfix/vmailbox")

        self._exec("grep", "-Fq", f"/.+@.+/ debug@{MAILNAME}", "/etc/postfix/virtual_regexp")

    def test_debug_account_accepts_imap_login(self) -> None:
        context = ssl._create_unverified_context()
        last_error: Exception | None = None
        for _ in range(30):
            try:
                connection = imaplib.IMAP4_SSL(
                    "127.0.0.1",
                    self.imap_port,
                    ssl_context=context,
                )
                try:
                    status, _ = connection.login(f"debug@{MAILNAME}", "debug")
                    self.assertEqual(status, "OK")
                finally:
                    connection.logout()
                return
            except (OSError, imaplib.IMAP4.error) as error:
                last_error = error
                time.sleep(1)
        raise AssertionError(f"IMAP login did not become ready: {last_error}")

    def test_smtp_catchall_delivers_to_debug_mailbox(self) -> None:
        subject = f"docker-imap-devel-smoke-{time.time_ns()}"
        message = EmailMessage()
        message["From"] = f"sender@{MAILNAME}"
        message["To"] = f"recipient@{MAILNAME}"
        message["Subject"] = subject
        message.set_content("Docker image smoke test")

        with smtplib.SMTP("127.0.0.1", self.smtp_port, timeout=10) as client:
            client.send_message(message)

        delivered_file = ""
        for _ in range(30):
            result = self._exec(
                "sh",
                "-c",
                "find /var/mail/localdomain.test/debug/new -type f -print -quit",
            )
            delivered_file = result.stdout.strip()
            if delivered_file:
                break
            time.sleep(1)

        self.assertTrue(delivered_file, "SMTP message was not delivered to debug mailbox")
        self._exec("grep", "-Fq", subject, delivered_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)
