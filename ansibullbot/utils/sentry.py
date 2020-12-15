from .. import constants
import sentry_sdk


def initialize_sentry():
    sentry_sdk.init(
        dsn=constants.DEFAULT_SENTRY_DSN,
        environment=constants.DEFAULT_SENTRY_ENV,
        server_name=constants.DEFAULT_SENTRY_SERVER_NAME,
        attach_stacktrace=constants.DEFAULT_SENTRY_TRACE,
        release=constants.ANSIBULLBOT_VERSION,
    )
