import sys
from pathlib import Path
from textwrap import dedent

import nox
from nox import Session
from nox import session

package = "strawberry_django_jwt"
python_versions = ["3.9", "3.8", "3.7"]
django_versions = ["3.0", "3.1", "3.2"]
pyjwt_versions = ["1.7.1", "2.1.0"]
strawberry_graphql_versions = ["0.69.0", "latest"]
nox.needs_version = ">= 2021.6.6"
nox.options.sessions = (
    "pre-commit",
    "safety",
    "mypy",
    "tests",
    "tests_pyjwt",
    "tests_strawberry_graphql",
    "coverage",
)
nox.options.reuse_existing_virtualenvs = True


def activate_virtualenv_in_precommit_hooks(session_: Session) -> None:
    """Activate virtualenv in hooks installed by pre-commit.
    This function patches git hooks installed by pre-commit to activate the
    session's virtual environment. This allows pre-commit to locate hooks in
    that environment when invoked from git.
    Args:
        session_: The Session object.
    """
    if session_.bin is None:
        return

    virtualenv = session_.env.get("VIRTUAL_ENV")
    if virtualenv is None:
        return

    hookdir = Path(".git") / "hooks"
    if not hookdir.is_dir():
        return

    for hook in hookdir.iterdir():
        if hook.name.endswith(".sample") or not hook.is_file():
            continue

        text = hook.read_text()
        bindir = repr(session_.bin)[1:-1]  # strip quotes
        if not (
            Path("A") == Path("a") and bindir.lower() in text.lower() or bindir in text
        ):
            continue

        lines = text.splitlines()
        if not (lines[0].startswith("#!") and "python" in lines[0].lower()):
            continue

        header = dedent(
            f"""\
            import os
            os.environ["VIRTUAL_ENV"] = {virtualenv!r}
            os.environ["PATH"] = os.pathsep.join((
                {session_.bin!r},
                os.environ.get("PATH", ""),
            ))
            """
        )

        lines.insert(1, header)
        hook.write_text("\n".join(lines))


@session(name="pre-commit", python="3.9")
def pre_commit(session_: Session) -> None:
    """Lint using pre-commit."""
    args = session_.posargs or ["run", "--all-files", "--show-diff-on-failure"]
    session_.install(
        "darglint",
        "autopep8",
        "pep8-naming",
        "pre-commit",
        "pre-commit-hooks",
    )
    session_.run("pre-commit", *args)
    if args and args[0] == "install":
        activate_virtualenv_in_precommit_hooks(session_)


@session(python="3.9")
def safety(session_: Session) -> None:
    """Scan dependencies for insecure packages."""
    requirements = Path("requirements.txt")
    session_.run(
        "poetry",
        "export",
        f"-o{requirements}",
        "--dev",
        "--without-hashes",
        external=True,
    )
    session_.install(f"-r{requirements}")
    session_.run("safety", "check", "--full-report", f"--file={requirements}")
    requirements.unlink()


@session(python="3.9")
def mypy(session_: Session) -> None:
    """Type-check using mypy."""
    args = session_.posargs or ["strawberry_django_jwt", "tests"]
    requirements = Path("requirements.txt")
    session_.run(
        "poetry",
        "export",
        f"-o{requirements}",
        "--dev",
        "--without-hashes",
        external=True,
    )
    session_.install(f"-r{requirements}")
    session_.run("mypy", *args)
    if not session_.posargs:
        session_.run("mypy", f"--python-executable={sys.executable}", "noxfile.py")


@session(name="tests", python=python_versions)
@nox.parametrize("django", django_versions)
def tests(session_: Session, django: str) -> None:
    """Run the test suite."""
    requirements = Path("requirements.txt")
    session_.run(
        "poetry",
        "export",
        f"-o{requirements}",
        "--dev",
        "--without-hashes",
        external=True,
    )
    session_.install(f"-r{requirements}")
    session_.install(f"django=={django}")
    session_.run("python", "-m", "pytest")
    requirements.unlink()

    try:
        session_.run("coverage", "run", "--parallel", "-m", "pytest", *session_.posargs)
    finally:
        if session_.interactive:
            session_.notify("coverage")


@session(python="3.9")
@nox.parametrize("pyjwt", pyjwt_versions)
def tests_pyjwt(session_: Session, pyjwt: str) -> None:
    requirements = Path("requirements.txt")
    session_.run(
        "poetry",
        "export",
        f"-o{requirements}",
        "--dev",
        "--without-hashes",
        external=True,
    )
    session_.install(f"-r{requirements}")
    session_.install(f"pyjwt=={pyjwt}")
    session_.run("python", "-m", "pytest")
    requirements.unlink()

    try:
        session_.run("coverage", "run", "--parallel", "-m", "pytest", *session_.posargs)
    finally:
        if session_.interactive:
            session_.notify("coverage")


@session(python="3.9")
@nox.parametrize("strawberry", strawberry_graphql_versions)
def tests_strawberry_graphql(session_: Session, strawberry: str) -> None:
    requirements = Path("requirements.txt")
    session_.run(
        "poetry",
        "export",
        f"-o{requirements}",
        "--dev",
        "--without-hashes",
        external=True,
    )
    session_.install(f"-r{requirements}")
    if strawberry == "latest":
        session_.install("strawberry-graphql", "-U")
    else:
        session_.install(f"strawberry-graphql=={strawberry}")
    session_.run("python", "-m", "pytest")
    requirements.unlink()

    try:
        session_.run("coverage", "run", "--parallel", "-m", "pytest", *session_.posargs)
    finally:
        if session_.interactive:
            session_.notify("coverage")


@session(python="3.9")
def coverage(session_: Session) -> None:
    """Produce the coverage report."""
    # Do not use session.posargs unless this is the only session.
    nsessions = len(session_._runner.manifest)
    has_args = session_.posargs and nsessions == 1
    args = session_.posargs if has_args else ["report", "-i"]

    session_.install("coverage[toml]")

    if not has_args and any(Path().glob(".coverage.*")):
        session_.run("coverage", "combine")

    session_.run("coverage", *args)
