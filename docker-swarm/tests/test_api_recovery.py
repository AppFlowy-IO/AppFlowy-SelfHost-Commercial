import unittest
from unittest.mock import Mock, patch

from api_recovery import ApplicationResponseError, verify_account


class AuthenticatedRecoveryTests(unittest.TestCase):
    def test_existing_user_recovers_after_transient_dependency_errors(self):
        expected = {'user_id': 'same-existing-user'}
        verify = Mock(side_effect=[ApplicationResponseError(1017, 'unavailable'),
                                   ApplicationResponseError(1017, 'unavailable'), expected])
        retry = Mock()
        with patch('api_recovery.time.sleep') as sleep:
            self.assertIs(verify_account(verify, after_replacement=True, on_retry=retry), expected)
        self.assertEqual(verify.call_count, 3)
        self.assertEqual(retry.call_count, 2)
        self.assertEqual(sleep.call_count, 2)

    def test_initial_account_provisioning_is_never_retried(self):
        error = ApplicationResponseError(1017, 'unavailable')
        verify = Mock(side_effect=error)
        with patch('api_recovery.time.sleep') as sleep:
            with self.assertRaises(ApplicationResponseError) as raised:
                verify_account(verify)
        self.assertIs(raised.exception, error)
        verify.assert_called_once()
        sleep.assert_not_called()

    def test_authorization_and_other_failures_are_not_treated_as_readiness(self):
        for code in (1012, 1018, 401, 403, 404):
            error = ApplicationResponseError(code, 'rejected')
            verify = Mock(side_effect=error)
            with self.subTest(code=code), patch('api_recovery.time.sleep') as sleep:
                with self.assertRaises(ApplicationResponseError) as raised:
                    verify_account(verify, after_replacement=True)
                self.assertIs(raised.exception, error)
                verify.assert_called_once()
                sleep.assert_not_called()

    def test_repeated_internal_failure_still_fails_at_the_deadline(self):
        error = ApplicationResponseError(1017, 'still unavailable')
        verify = Mock(side_effect=error)
        elapsed = [0]

        def sleep(seconds):
            elapsed[0] += seconds

        with patch('api_recovery.time.monotonic', side_effect=lambda: elapsed[0]), \
             patch('api_recovery.time.sleep', side_effect=sleep):
            with self.assertRaises(ApplicationResponseError) as raised:
                verify_account(verify, after_replacement=True, timeout=3)
        self.assertIs(raised.exception, error)
        self.assertEqual(elapsed[0], 3)
        self.assertEqual(verify.call_count, 4)

    def test_unexpected_transport_or_programming_errors_are_not_retried(self):
        verify = Mock(side_effect=RuntimeError('unexpected response'))
        with patch('api_recovery.time.sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'unexpected response'):
                verify_account(verify, after_replacement=True)
        verify.assert_called_once()
        sleep.assert_not_called()
