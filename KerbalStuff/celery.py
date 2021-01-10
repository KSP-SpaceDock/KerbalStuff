from datetime import datetime
from types import FrameType
from typing import List, Iterable, Any

from celery import Celery

from .common import with_session
from .config import _cfg, _cfgi, _cfgb, site_logger
from .objects import Game, Mod
from .search import get_mod_score
from .ckan import import_ksp_versions_from_ckan

app = Celery("tasks", broker=_cfg("redis-connection"))


def chunks(l: List[str], n: int) -> Iterable[List[str]]:
    """ Yield successive n-sized chunks from l.
    """
    for i in range(0, len(l), n):
        yield l[i:i + n]


@app.task
def send_mail(sender: str, recipients: List[str], subject: str, message: str, important: bool = False) -> None:
    host = _cfg('smtp-host')
    if not host:
        return
    import smtplib
    from email.mime.text import MIMEText
    from email.utils import format_datetime
    smtp = smtplib.SMTP(host=host, port=_cfgi("smtp-port"))
    if _cfgb("smtp-tls"):
        smtp.starttls()
    user = _cfg('smtp-user')
    passwd = _cfg('smtp-password')
    if user and passwd:
        # If there's a user and no password, let the connection attempt fail hard so that it logs the message.
        smtp.login(user, passwd)
    msg = MIMEText(message)
    if important:
        msg['X-MC-Important'] = "true"
    msg['X-MC-PreserveRecipients'] = "false"
    msg['Subject'] = subject
    msg['Date'] = format_datetime(datetime.utcnow())
    msg['From'] = sender
    if len(recipients) > 1:
        msg['Precedence'] = 'bulk'
    for group in chunks(recipients, 100):
        if len(group) > 1:
            msg['To'] = "undisclosed-recipients:;"
        else:
            msg['To'] = ";".join(group)
        site_logger.info("Sending email from %s to %s recipients", sender, len(group))
        smtp.sendmail(sender, group, msg.as_string())
    smtp.quit()


@app.task
def update_from_github(working_directory: str, branch: str, restart_command: str) -> None:
    site_logger.info('Updating the site from github at: %s', working_directory)
    try:
        # pull new sources from git
        from git import Repo, GitError
        try:
            repo = Repo(working_directory)
            if repo.bare:
                raise GitError()
        except GitError:
            site_logger.warning('No git repository at: %s', working_directory)
            return
        if repo.is_dirty():
            site_logger.warning('Repository is dirty, cannot pull changes')
            return
        origin = repo.remote('origin')
        if not origin.exists():
            site_logger.error('No "origin" remote in the repository')
            return
        old_hash = repo.head.object.hexsha
        origin.pull(branch)
        if old_hash == repo.head.object.hexsha:
            site_logger.info('Working tree is already up to date')
            if not _cfg('hook_update_same_version'):
                return
        else:
            site_logger.info('Pulled latest changes from origin/%s', branch)
        # run restart command in a subprocess to daemonize it from there
        # and avoid its killing by restart process
        from billiard import Process
        p = Process(target=_restart_subprocess,
                    args=(working_directory, restart_command))
        p.start()
        p.join()
    except Exception:
        site_logger.exception('Unable to update from github')


@app.on_after_configure.connect
def setup_periodic_tasks(sender: Any, **kwargs: int) -> None:
    sender.add_periodic_task(86400, calculate_mod_scores.s(), name='calculate mod scores')
    sender.add_periodic_task(3600, ckan_version_import.s(), name='import ksp versions from ckan')


@app.task
@with_session
def calculate_mod_scores() -> None:
    for mod in Mod.query.all():
        mod.score = get_mod_score(mod)


@app.task
@with_session
def ckan_version_import() -> None:
    game = Game.query.filter(Game.ckan_enabled == True).first()
    if game:
        import_ksp_versions_from_ckan(game.id)

# to debug this:
# * add PTRACE capability to celery container via docker-compose.yaml
#   celery:
#     image: spacedock_celery
#     build:
#       context: ./
#       target: celery
#     user: spacedock
#     cap_add:
#       - SYS_PTRACE
# * install strace to corresponding container in Dockerfile:
#     FROM backend-dev as celery
#     ADD requirements-celery.txt ./
#     RUN pip3 install -r requirements-celery.txt
#     RUN apt-get update && apt-get install strace
# * when the service is running, enter this container:
#     > docker exec -u root -it $(docker ps -q -f "name=spacedock_celery") bash
# * run strace as follows:
#     > strace -tt -f -p $(pgrep celery | head -n 2 | tail -n 1) -s 10000 -o celery/strace.log -e trace='!close,read,mmap,munmap'
# * explore the logs outside of the container in <SpaceDock>/celery/strace.log

def _restart_subprocess(working_directory: str, restart_command: str) -> None:
    """
    Run restart_command in a daemonized subprocess to avoid killing it
    by systemd when the restart process begin.

    In a docker container there's no init, so no one will reap
    the two processes that entering DaemonContext will spawn.
    They become zombies. So this code is strictly specific to the
    live production systems on which alpha/beta/prod are running.
    """
    import daemon
    import signal
    import syslog
    import sys
    import os
    # have to set std streams to devnull, because in celery they're replaced
    # with the LoggingProxy that doesn't have fileno method
    sys.stdin = sys.stdout = sys.stderr = open(os.devnull, 'w')
    try:
        def _signal_handler(sig: int, _frame: FrameType) -> None:
            syslog.syslog(syslog.LOG_INFO, f'[celery._restart_subprocess] ignoring signal: {sig}')

        with daemon.DaemonContext(working_directory=working_directory,
                                  detach_process=True,
                                  umask=0o002,
                                  signal_map={signal.SIGQUIT: _signal_handler,
                                              signal.SIGTERM: _signal_handler,
                                              signal.SIGHUP: _signal_handler,
                                              signal.SIGABRT: _signal_handler}
                                  ):
            import logging
            from logging.config import fileConfig
            # recreate handlers to reopen corresponding output streams
            fileConfig('logging.ini')
            logger = logging.getLogger('system')
            try:
                logger.info('Starting: %s', restart_command)
                from subprocess import check_call
                check_call(restart_command.split())
                logger.info('Command has finished: %s', restart_command)
            except Exception:
                logger.exception('Error while running: %s', restart_command)
    except Exception:
        site_logger.exception('Unable to start detached process to run: %s', restart_command)
