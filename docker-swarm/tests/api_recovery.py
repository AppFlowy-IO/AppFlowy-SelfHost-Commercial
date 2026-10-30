"""Authenticated readiness after deliberately replacing a deployment dependency."""
import time


class ApplicationResponseError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def verify_account(verify, *, after_replacement=False, timeout=15, on_retry=None):
    # New-account provisioning is not a recovery probe and must never be retried here.
    if not after_replacement:
        return verify()
    deadline = time.monotonic() + timeout
    retries = 0
    while True:
        try:
            return verify()
        except ApplicationResponseError as error:
            # A stale Redis manager connection fails closed on its first read and
            # reconnects in the background. Authentication/permission failures,
            # other API errors, and failures past this recovery window still fail.
            remaining = deadline - time.monotonic()
            if error.code != 1017 or remaining <= 0:
                raise
            retries += 1
            if on_retry:
                on_retry(retries)
            time.sleep(min(1, remaining))
