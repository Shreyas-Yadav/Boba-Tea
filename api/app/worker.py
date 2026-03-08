from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import boto3

from .settings import get_settings
from .visualization_jobs import process_visualization_job, visualization_jobs_ready

logger = logging.getLogger("recraft.worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _handle_message(queue_url: str, receipt_handle: str, body: str) -> None:
    settings = get_settings()
    process_visualization_job(body, settings)
    boto3.client("sqs", region_name=settings.aws_region).delete_message(
        QueueUrl=queue_url,
        ReceiptHandle=receipt_handle,
    )


def main() -> int:
    settings = get_settings()
    if not visualization_jobs_ready(settings):
        logger.error("Visualization jobs are not configured. Set VISUALIZATION_JOBS_* before running the worker.")
        return 1

    sqs_client = boto3.client("sqs", region_name=settings.aws_region)
    queue_url = settings.visualization_jobs_queue_url
    logger.info(
        "Visualization worker started: queue=%s concurrency=%s wait_seconds=%s",
        queue_url,
        settings.visualization_worker_concurrency,
        settings.visualization_worker_wait_seconds,
    )

    while True:
        response = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=min(10, settings.visualization_worker_concurrency),
            WaitTimeSeconds=settings.visualization_worker_wait_seconds,
            VisibilityTimeout=max(60, settings.visualization_worker_wait_seconds * 12),
        )
        messages = response.get("Messages", [])
        if not messages:
            continue

        with ThreadPoolExecutor(max_workers=settings.visualization_worker_concurrency) as executor:
            futures = [
                executor.submit(
                    _handle_message,
                    queue_url,
                    message["ReceiptHandle"],
                    message["Body"],
                )
                for message in messages
            ]
            for future in futures:
                try:
                    future.result()
                except Exception:
                    logger.exception("Visualization worker message processing failed.")
        time.sleep(0.1)


if __name__ == "__main__":
    raise SystemExit(main())
