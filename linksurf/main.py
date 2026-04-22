from linksurf.tasks import celery

if __name__ == "__main__":
    celery.worker_main(argv=["worker", "--concurrency=10", "--loglevel=info"])
