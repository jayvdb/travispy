from ._entity import Entity

from travispy._helpers import get_archived_log


class Log(Entity):
    '''
    :ivar int job_id:
        Jod ID.

    :ivar str type:
    '''

    __slots__ = [
        'job_id',
        '_body',
        'type',
    ]

    def __init__(self, session):
        super(Log, self).__init__(session)
        self._body = None

    @property
    def body(self):
        '''
        :rtype: str
        :returns:
            The raw log text fetched on demand.
        '''
        if self._body is None:
            self._body = get_archived_log(self._session, self.job_id)

        return self._body

    @property
    def job(self):
        '''
        :rtype: :class:`.Job`
        :returns:
            A :class:`.Job` object with information related to current ``job_id``.
        '''
        from .job import Job
        return self._load_one_lazy_information(Job)
