class AquaSequrityError(Exception):
    """
    A base exceptions for all system defined exceptions
    """

    pass


class NotActiveUserException(AquaSequrityError):
    pass


class DeactivatedUserException(AquaSequrityError):
    pass
