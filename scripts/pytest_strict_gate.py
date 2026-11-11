"""pytest plugin: fail the run on skipped or expected-failure tests that are not justified.

A skip or xfail is allowed only when its reason starts with ``JUSTIFIED:``.
"""

import pytest

JUSTIFIED_PREFIX = "JUSTIFIED:"
_SKIP_PREFIX = "Skipped: "

_offenders = pytest.StashKey[list[tuple[str, str]]]()


def _reason(report: pytest.TestReport | pytest.CollectReport) -> str:
    wasxfail = getattr(report, "wasxfail", None)
    if isinstance(wasxfail, str):
        return wasxfail
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2]).removeprefix(_SKIP_PREFIX)
    return ""


def _record(config: pytest.Config, report: pytest.TestReport | pytest.CollectReport) -> None:
    if not report.skipped:
        return
    reason = _reason(report)
    if not reason.startswith(JUSTIFIED_PREFIX):
        config.stash[_offenders].append((report.nodeid, reason))


def pytest_configure(config: pytest.Config) -> None:
    config.stash[_offenders] = []


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):  # type: ignore[no-untyped-def]
    report: pytest.TestReport = yield
    _record(item.config, report)
    return report


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector: pytest.Collector):  # type: ignore[no-untyped-def]
    report: pytest.CollectReport = yield
    _record(collector.config, report)
    return report


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    # A run that would otherwise count as clean (or merely empty) is not clean.
    clean = (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED)
    if session.config.stash[_offenders] and exitstatus in clean:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    offenders = terminalreporter.config.stash[_offenders]
    if not offenders:
        return
    terminalreporter.section("unjustified skips and expected failures", red=True)
    terminalreporter.line(f"Every skip or xfail reason must start with {JUSTIFIED_PREFIX!r}.")
    for nodeid, reason in offenders:
        terminalreporter.line(f"{nodeid}: {reason or '(no reason given)'}")
