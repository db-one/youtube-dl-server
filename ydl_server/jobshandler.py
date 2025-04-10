from queue import Queue, Empty
from threading import Thread
from ydl_server.db import JobsDB, Actions


class JobsHandler:
    def __init__(self, app_config):
        self.queue = Queue()
        self.thread = None
        self.done = False
        self.app_config = app_config

    def start(self, dl_queue):
        self.thread = Thread(target=self.worker, args=(dl_queue,))
        self.thread.start()

    def stop(self):
        self.done = True

    def put(self, obj):
        self.queue.put(obj)

    def finish(self):
        self.done = True

    def worker(self, dl_queue):
        db = JobsDB(readonly=False)
        while not self.done:
            try:
                action, job = self.queue.get(timeout=1)
            except Empty:
                continue
            if action == Actions.PURGE_LOGS:
                if db.purge_jobs():
                    db.vacuum()
            elif action == Actions.INSERT:
                if db.clean_old_jobs(
                        self.app_config["ydl_server"].get("max_log_entries", 100) - 1
                    ):
                    db.vacuum()
                db.insert_job(job)
                dl_queue.put(job)
            elif action == Actions.UPDATE:
                db.update_job(job)
            elif action == Actions.RESUME:
                db.update_job(job)
                dl_queue.put(job)
            elif action == Actions.SET_NAME:
                job_id, name = job
                db.set_job_name(job_id, name)
            elif action == Actions.SET_LOG:
                job_id, log = job
                db.set_job_log(job_id, log)
            elif action == Actions.SET_STATUS:
                job_id, status = job
                db.set_job_status(job_id, status)
            elif action == Actions.SET_PID:
                job_id, pid = job
                db.set_job_pid(job_id, pid)
            elif action == Actions.CLEAN_LOGS:
                if db.clean_old_jobs():
                    db.vacuum()
            elif action == Actions.DELETE_LOG_SAFE:
                if db.delete_job_safe(job["id"]):
                    db.vacuum()
            elif action == Actions.DELETE_LOG:
                if db.delete_job(job["id"]):
                    db.vacuum()
            self.queue.task_done()

    def join(self):
        if self.thread is not None:
            return self.thread.join()
