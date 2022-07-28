from pathlib import Path
import sys
from textwrap import dedent

import nox
from nox_poetry import Session, session

package = "strawberry_django_jwt"
python_versions = ["3.10", "3.9", "3.8", "3.7"]
django_versions = ["4.0", "3.2"]
invalid_sessions = [
    ("3.7", "4.0"),
    ("3.10", "3.1"),
]
pyjwt_versions = ["1.7.1", "latest"]
strawberry_graphql_versions = ["latest"]
nox.needs_version = ">= 2021.6.6"
nox.options.sessions = ("tests",)
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
        if not (Path("A") == Path("a") and bindir.lower() in text.lower() or bindir in text):
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


def install(session_: Session, package_, version):
    if version == "latest":
        nox.Session.install(session_, package, "-U")
    else:
        nox.Session.install(session_, f"{package_}=={version}")


# noinspection PyUnresolvedReferences,PyProtectedMember
def export_requirements_without_extras(session_: Session) -> Path:
    """Ugly workaround to install only certain dev dependencies without extras"""
    extras = session_.poetry.poetry.config._config.get("extras", {})  # type: ignore
    session_.poetry.poetry.config._config["extras"] = {}  # type: ignore
    requirements = session_.poetry.export_requirements()
    session_.poetry.poetry.config._config["extras"] = extras  # type: ignore
    return requirements  # noqa: R504


@session(name="pre-commit", python="3.9")
def pre_commit(session_: Session) -> None:
    """Lint using pre-commit."""
    args = session_.posargs or ["run", "--all-files", "--show-diff-on-failure"]
    session_.install(
        "darglint",
        "black",
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
    requirements = session_.poetry.export_requirements()
    session_.install("safety")
    session_.run("safety", "check", "--full-report", f"--file={requirements}")


@session(python="3.9")
def mypy(session_: Session) -> None:
    """Type-check using mypy."""
    args = session_.posargs or ["strawberry_django_jwt", "tests"]
    requirements = export_requirements_without_extras(session_)
    session_.install("-r", str(requirements))
    session_.run("mypy", *args)
    if not session_.posargs:
        session_.run("mypy", f"--python-executable={sys.executable}", "noxfile.py")


@session(name="tests", python=python_versions)
@nox.parametrize("django", django_versions)
def tests(session_: Session, django: str) -> None:
    """Run the test suite."""
    if (session_.python, django) in invalid_sessions:
        session_.skip()
    session_.install(".")
    requirements = export_requirements_without_extras(session_)
    session_.install("-r", str(requirements))
    install(session_, "django", django)

    try:
        session_.run("coverage", "run", "--parallel", "-m", "pytest", *session_.posargs)
    finally:
        if session_.interactive:
            session_.notify("coverage")


@session(python="3.9")
@nox.parametrize("pyjwt", pyjwt_versions)
def tests_pyjwt(session_: Session, pyjwt: str) -> None:
    session_.install(".")
    requirements = export_requirements_without_extras(session_)
    session_.install("-r", str(requirements))
    install(session_, "pyjwt", pyjwt)

    try:
        session_.run("coverage", "run", "--parallel", "-m", "pytest", *session_.posargs)
    finally:
        if session_.interactive:
            session_.notify("coverage")


@session(python="3.9")
@nox.parametrize("strawberry", strawberry_graphql_versions)
def tests_strawberry_graphql(session_: Session, strawberry: str) -> None:
    session_.install(".")
    requirements = export_requirements_without_extras(session_)
    session_.install("-r", str(requirements))
    install(session_, "strawberry-graphql", strawberry)
    if strawberry == "0.69.0":
        install(session_, "graphql-core", "3.1.7")

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
