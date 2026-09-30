"""Background job runner: `python -m app.worker`."""

import logging
import time

from app.db.session import SessionLocal
from app.services.jobs import claim_next, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(levelname)s %(message)s")
log = logging.getLogger("worker")
IDLE_SLEEP = 1.0


def main() -> None:
    log.info("worker started")
    while True:
        with SessionLocal() as db:
            job = claim_next(db)
            if job is None:
                time.sleep(IDLE_SLEEP)
                continue
            log.info("running %s %s", job.kind, job.payload)
            run(db, job)
            log.info("finished %s -> %s", job.kind, job.status)


if __name__ == "__main__":
    main()
