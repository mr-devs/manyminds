"""The strict gate fails a run that contains unjustified skips or expected failures.

Each test runs an inner pytest session with the gate loaded and checks its exit status.
"""

import pytest

GATE = ("-p", "pytest_strict_gate")
OK = pytest.ExitCode.OK
FAILED = pytest.ExitCode.TESTS_FAILED


def test_passing_run_is_unaffected(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_fine():
            assert True
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == OK
    result.assert_outcomes(passed=1)


def test_skip_without_justification_fails_the_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.skip(reason="flaky on my machine")
        def test_lazy():
            assert True
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == FAILED
    result.stdout.fnmatch_lines(["*unjustified*", "*test_lazy*flaky on my machine*"])


def test_skip_with_no_reason_fails_the_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.skip
        def test_silent():
            assert True
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == FAILED
    result.stdout.fnmatch_lines(["*test_silent*"])


def test_justified_skip_is_allowed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.skip(reason="JUSTIFIED: needs a Windows keychain")
        def test_windows_only():
            assert True
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == OK
    result.assert_outcomes(skipped=1)


def test_skip_raised_inside_a_test_fails_the_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        def test_bails_out():
            pytest.skip("could not be bothered")
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == FAILED
    result.stdout.fnmatch_lines(["*test_bails_out*could not be bothered*"])


def test_module_level_skip_fails_the_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        pytest.skip("whole file switched off", allow_module_level=True)

        def test_never_collected():
            assert True
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == FAILED
    result.stdout.fnmatch_lines(["*whole file switched off*"])


def test_expected_failure_without_justification_fails_the_run(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.xfail(reason="known bug")
        def test_broken():
            assert False
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == FAILED
    result.stdout.fnmatch_lines(["*test_broken*known bug*"])


def test_justified_expected_failure_is_allowed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.xfail(reason="JUSTIFIED: upstream bug 123, fixed in next release")
        def test_broken_upstream():
            assert False
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == OK
    result.assert_outcomes(xfailed=1)


def test_real_failures_still_fail(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_wrong():
            assert 1 == 2
        """
    )

    result = pytester.runpytest(*GATE)

    assert result.ret == FAILED
    result.assert_outcomes(failed=1)
