from .errors import TravisError

import textwrap

import requests


def get_response_contents(response):
    '''
    :type response: :class:`requests.models.Response`
    :param response:
        Response returned from Travis API.

    :rtype: dict
    :returns:
        Content related the request related to the given ``response``.

    :raises TravisError: when return code is different than 200 or an unexpected error happens.
    '''
    status_code = response.status_code
    try:
        contents = response.json()
    except:
        error = response.text.strip()
        if not error:
            error = textwrap.dedent('''
                Unexpected error
                    Possible reasons are:
                     - Communication with Travis CI has failed.
                     - Insufficient permissions.
                     - Invalid contents returned.
                ''')[1:]
        contents = {
            'status_code': status_code,
            'error': error,
        }
        raise TravisError(contents)

    if status_code == 200:
        return contents
    else:
        contents['status_code'] = status_code
        raise TravisError(contents)


def get_archived_log(session, job_id):
    '''
    :type session: :class:`.Session`
    :param session:
        Session that must be used to search for result.

    :param int job_id:
        The ID of the job.

    :rtype: str
    :returns:
        Log of the job.
    '''
    headers = session.headers.copy()
    headers['Accept'] = 'text/plain; version=2'

    r = requests.get(session.uri + ('/jobs/%s/log' % job_id),
                     headers=headers)
    return r.content.decode('utf-8')
